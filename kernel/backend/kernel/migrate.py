"""Upgrades that stop before a destructive migration (SPEC 10, decision 0049).

A revision whose file sets `destructive = True` drops or rewrites data. When
its branch is already in the database, an upgrade that would run it stops
before any step runs and names it, until the caller names it back:
`--confirm-destructive <revision>` on the command line, `confirm=` here. A
deploy's pre-deploy step (`python -m app.migrations upgrade`) fails there, the
database as it was, so nothing goes live until the site's owner has backed it
up and run the revision by hand. A name confirms only its own revision, so one
left in a command can't let a later one through.

A destructive revision whose branch has nothing in the database yet runs
unasked: a new site, or a module just added. The tables it could touch are
made in the same upgrade, so there's nothing yet to lose. (A module's
migrations touch only its own tables, SPEC 10.)

`command_line` is the harness's `python -m harness.migrations` and every
site's `python -m app.migrations`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Collection, Iterable, Sequence
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.runtime.migration import RevisionStep
from alembic.script import Script, ScriptDirectory

FLAG = "--confirm-destructive"
VERBS = ("upgrade", "downgrade", "heads", "history", "current")

#: Revision ids (a comma also separates them), or True: every destructive
#: revision, for a database that's thrown away after (tests).
Confirm = Collection[str] | bool


class DestructiveMigrationRefused(Exception):
    """An upgrade would run destructive revisions on data already there, and
    `scripts` were not named. Nothing ran."""

    def __init__(
        self,
        target: str,
        flagged: Sequence[Script],
        scripts: Sequence[Script],
        unknown: Sequence[str],
    ) -> None:
        self.target = target
        #: every destructive revision the upgrade would run on data already there
        self.flagged = tuple(flagged)
        #: those of them nobody named
        self.scripts = tuple(scripts)
        #: names given that are none of `flagged`
        self.unknown = tuple(unknown)
        names = ", ".join(script.revision for script in self.scripts)
        super().__init__(
            f"An upgrade to {target} would run unconfirmed destructive revisions: {names}"
        )


def is_destructive(script: Script) -> bool:
    """Its file marks it `destructive = True`. Any true value counts, so a
    mark other than False errs toward asking."""
    return bool(getattr(script.module, "destructive", False))


def _names(confirm: Confirm) -> set[str]:
    if isinstance(confirm, bool):
        return set()
    given: Iterable[str] = [confirm] if isinstance(confirm, str) else confirm
    return {name.strip() for item in given for name in item.split(",") if name.strip()}


def _below(script: Script) -> tuple[str, ...]:
    """The revisions just below it on its branch (not its `depends_on`)."""
    down = script.down_revision
    if down is None:
        return ()
    return (down,) if isinstance(down, str) else tuple(down)


def _on_data(script: Script, pending: set[str], scripts: ScriptDirectory) -> bool:
    """Some revision below it on its branch has already run: its tables hold data."""
    seen: set[str] = set()
    stack = list(_below(script))
    while stack:
        revision = stack.pop()
        if revision in seen:
            continue
        seen.add(revision)
        if revision not in pending:
            return True
        found = scripts.get_revision(revision)
        if found is not None:
            stack.extend(_below(found))
    return False


def upgrade(cfg: Config, target: str = "heads", *, confirm: Confirm = ()) -> None:
    """Alembic's `command.upgrade`, refusing an unconfirmed destructive revision.

    The check runs on the upgrade's own connection, after it reads the
    database's heads and before its first step, so what it checked is what
    runs. Raises DestructiveMigrationRefused, with nothing run."""
    scripts = ScriptDirectory.from_config(cfg)
    named = _names(confirm)

    def steps(heads: Any, _context: Any) -> list[RevisionStep]:
        # The steps exactly as `command.upgrade` makes them (Alembic is pinned).
        planned: list[RevisionStep] = scripts._upgrade_revs(target, heads)
        pending = {step.revision.revision for step in planned}
        flagged = [
            step.revision
            for step in planned
            if is_destructive(step.revision) and _on_data(step.revision, pending, scripts)
        ]
        unknown = sorted(named - {script.revision for script in flagged})
        if confirm is not True:
            missing = [script for script in flagged if script.revision not in named]
            if missing:
                raise DestructiveMigrationRefused(target, flagged, missing, unknown)
        for name in unknown:
            cfg.print_stdout(f"Named, but not a destructive migration this upgrade runs: {name}")
        for script in flagged:
            cfg.print_stdout(f"Running {script.revision}, marked destructive = True, as confirmed.")
        return planned

    with EnvironmentContext(
        cfg,
        scripts,
        fn=steps,
        as_sql=False,
        starting_rev=None,
        destination_rev=target,
        tag=None,
    ):
        scripts.run_env()


def _shown(path: str) -> str:
    """The file, from the current folder when it's in it."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path


def refusal(refused: DestructiveMigrationRefused, prog: str) -> str:
    """What the command prints: each revision, and the command that runs them."""
    count = len(refused.scripts)
    lines = [
        f"{prog}: refused. An upgrade to {refused.target} would run "
        f"{count} migration{'' if count == 1 else 's'} marked destructive = True "
        "on data already in the database (SPEC 10):",
        "",
    ]
    for script in refused.scripts:
        lines.append(f"  {script.revision}  {_shown(script.path)}")
        if script.doc:
            lines.append(f"      {script.doc}")
    if refused.unknown:
        lines += [
            "",
            "Named, but not a destructive migration this upgrade runs: "
            + ", ".join(refused.unknown),
        ]
    target = "" if refused.target == "heads" else f" {refused.target}"
    names = ",".join(script.revision for script in refused.flagged)
    lines += [
        "",
        "Nothing was migrated. Back the database up and read each one; then run, by hand:",
        "",
        f"  {prog} upgrade{target} {FLAG} {names}",
    ]
    return "\n".join(lines)


def command_line(argv: Sequence[str], config: Callable[[], Config], prog: str) -> int:
    """`upgrade [target] [--confirm-destructive REVISION]`, `downgrade [target]`,
    `heads`, `history` or `current`. 2 on a usage error or a refusal."""
    parser = argparse.ArgumentParser(prog=prog, description="Migrate the database.")
    parser.add_argument("verb", choices=VERBS)
    parser.add_argument("target", nargs="?")
    parser.add_argument(
        FLAG,
        dest="confirm",
        action="append",
        default=[],
        metavar="REVISION",
        help="run this destructive revision (repeat it, or separate names by commas)",
    )
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as stop:  # argparse has printed the usage
        return stop.code if isinstance(stop.code, int) else 2
    if args.confirm and args.verb != "upgrade":
        parser.print_usage(sys.stderr)
        print(f"{prog}: only upgrade takes {FLAG}", file=sys.stderr)
        return 2
    cfg = config()
    if args.verb == "upgrade":
        try:
            upgrade(cfg, args.target or "heads", confirm=args.confirm)
        except DestructiveMigrationRefused as refused:
            print(refusal(refused, prog), file=sys.stderr)
            return 2
    elif args.verb == "downgrade":
        command.downgrade(cfg, args.target or "-1")
    elif args.verb == "heads":
        command.heads(cfg, verbose=True)
    elif args.verb == "history":
        command.history(cfg, verbose=True)
    else:
        command.current(cfg, verbose=True)
    return 0

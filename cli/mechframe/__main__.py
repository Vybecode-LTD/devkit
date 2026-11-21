"""`python -m mechframe <command>` (K5 contract §2; cli/README.md).

Built: `new` (with `--recipe`, a recipe's modules too), `add`, `remove`,
`create-owner`, `seed`, `catalog` and `check`. `diff` and `upgrade` wait for a
module's second version (the owner, 2026-11-20).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mechframe import __version__, catalog, check, modules, new, owner, seed
from mechframe.source import ROOT


def _root(command: argparse.ArgumentParser) -> None:
    # The checkout to use. Always this one but in the CLI's own tests.
    command.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mechframe",
        description="Make MechFrame sites from this checkout and check them against it.",
    )
    parser.add_argument("--version", action="version", version=f"mechframe {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    started = commands.add_parser("new", help="make a site in an empty folder")
    started.add_argument("dir", type=Path, help="the site's folder: empty, or not there yet")
    started.add_argument("--name", help="the site's name (default: the folder's)")
    started.add_argument("--recipe", help="add a recipe's modules too (recipes/<id>.json)")
    started.add_argument(
        "--theme",
        help=f"its theme (default: the recipe's, else {new.DEFAULT_THEME})",
    )
    _root(started)

    adding = commands.add_parser("add", help="add a module to a site")
    adding.add_argument("id", help="the module's id")
    adding.add_argument("--site", type=Path, default=Path(), help="the site (default: here)")
    _root(adding)

    owning = commands.add_parser(
        "create-owner", help="make the site's owner: prints a one-time link to set its password"
    )
    owning.add_argument("email", help="the owner's email address")
    owning.add_argument("--site", type=Path, default=Path(), help="the site (default: here)")
    _root(owning)

    seeding = commands.add_parser(
        "seed", help="load the site's seed data: only with MECHFRAME_ALLOW_SEED=1, never live"
    )
    seeding.add_argument("--site", type=Path, default=Path(), help="the site (default: here)")
    _root(seeding)

    removing = commands.add_parser("remove", help="remove a module from a site, keeping its tables")
    removing.add_argument("id", help="the module's id")
    removing.add_argument("--site", type=Path, default=Path(), help="the site (default: here)")
    _root(removing)

    made = commands.add_parser("catalog", help="write catalog.json from every built module")
    made.add_argument("--check", action="store_true", help="only say whether it's current")
    _root(made)

    checked = commands.add_parser(
        "check", help="what a site edited, what is behind, and which advisories are open"
    )
    checked.add_argument("--site", type=Path, default=Path(), help="the site (default: here)")
    checked.add_argument("--json", action="store_true", help="answer in JSON")
    _root(checked)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "new":
        site = args.dir.resolve()
        try:
            name = site.name if args.name is None else args.name
            made = new.new(site, name=name, theme=args.theme, recipe=args.recipe, root=args.root)
        except (new.Refused, modules.Refused) as refusal:
            print(refusal, file=sys.stderr)
            return 2
        print("\n".join(new.next_steps(made)))
        return 0
    if args.command in ("create-owner", "seed"):
        try:
            if args.command == "seed":
                return seed.seed(args.site.resolve(), root=args.root)
            return owner.create_owner(args.site.resolve(), args.email, root=args.root)
        except owner.Refused as refusal:
            print(refusal, file=sys.stderr)
            return 2
    if args.command in ("add", "remove"):
        site = args.site.resolve()
        try:
            if args.command == "add":
                lines = modules.added_lines(modules.add(site, args.id, root=args.root))
            else:
                lines = modules.removed_lines(modules.remove(site, args.id, root=args.root))
        except modules.Refused as refusal:
            print(refusal, file=sys.stderr)
            return 2
        print("\n".join(lines))
        return 0
    if args.command == "catalog":
        if args.check:
            if catalog.stale(args.root):
                print(f"{catalog.NAME} is stale: run `python -m mechframe catalog`.")
                return 1
            print(f"{catalog.NAME} is current.")
            return 0
        path = catalog.write(args.root)
        print(f"Wrote {path.name}.")
        return 0

    report = check.check(args.site.resolve(), root=args.root)
    if args.json:
        print(json.dumps(report.as_json(), indent=2))
    else:
        print("\n".join(report.lines()))
    return report.exit_code()


if __name__ == "__main__":
    sys.exit(main())

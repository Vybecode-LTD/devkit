"""Alembic, set up in code: one environment, one branch per module.

The kernel's revisions carry the branch label `kernel`; each module's first
revision carries its id as a label and depends on the kernel's
(SPEC.md section 10). `version_locations` lists the kernel's folder and every
module's, so `upgrade("heads")` runs them all in order.

From a terminal, `python -m harness.migrations upgrade` does the same with the
database in DATABASE_URL. Either stops before a migration marked
`destructive = True` whose branch is already in the database, until it's named
with `--confirm-destructive` (`kernel.migrate`, decision 0049).
"""

from __future__ import annotations

import os
import sys

from alembic import command
from alembic.config import Config

from harness.layout import ROOT, migration_dirs
from kernel import migrate

SCRIPT_LOCATION = ROOT / "harness" / "alembic"


def config(database_url: str | None = None) -> Config:
    """An Alembic config for this repo. `database_url` overrides the app's."""
    cfg = Config(stdout=sys.stdout)  # read now: Alembic's default is bound at its import
    # Alembic's config is an ini file: a literal %, in a path as in the URL, is
    # written doubled (CodeRabbit on #92).
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION).replace("%", "%%"))
    cfg.set_main_option("path_separator", "os")
    locations = os.pathsep.join(str(p) for p in migration_dirs())
    cfg.set_main_option("version_locations", locations.replace("%", "%%"))
    if database_url is not None:
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade(
    database_url: str | None = None,
    target: str = "heads",
    *,
    confirm_destructive: migrate.Confirm = (),
) -> None:
    """Upgrade, refusing a destructive revision not named in
    `confirm_destructive` (True: all of them, for a throwaway database)."""
    migrate.upgrade(config(database_url), target, confirm=confirm_destructive)


def downgrade(database_url: str | None = None, target: str = "base") -> None:
    command.downgrade(config(database_url), target)


def main(argv: list[str]) -> int:
    """`upgrade [target] [--confirm-destructive REVISION]`, `downgrade [target]`,
    `heads`, `history` or `current`."""
    return migrate.command_line(argv, config, prog="python -m harness.migrations")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

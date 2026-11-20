"""Alembic, set up in code: one environment, one branch per module (SPEC.md section 10).

    python -m app.migrations upgrade            (with PYTHONPATH=backend)

The kernel's revisions carry the branch label `kernel`; each module's first
revision carries its id and depends on the kernel's. `version_locations` lists
`backend/migrations/kernel/` and each module's folder there, so
`upgrade("heads")` runs them all in order. Railway runs `upgrade` before each
deploy goes live (README.md, "Deploying"). It stops before a migration marked
`destructive = True` whose branch is already in the database, until the owner
names it with `--confirm-destructive` (`kernel.migrate`, decision 0049).
"""

from __future__ import annotations

import os
import sys

from alembic import command
from alembic.config import Config

from app import BACKEND
from kernel import migrate

MIGRATIONS = BACKEND / "migrations"
SCRIPT_LOCATION = BACKEND / "alembic"


def migration_dirs() -> list[str]:
    """The kernel's migrations, then each module's, in id order."""
    found = [MIGRATIONS / "kernel"]
    if MIGRATIONS.is_dir():
        found += sorted(
            path for path in MIGRATIONS.iterdir() if path.is_dir() and path.name != "kernel"
        )
    return [str(path) for path in found if path.is_dir()]


def _ini(value: str) -> str:
    return value.replace("%", "%%")


def app_database_url() -> str:
    """The database the app uses: DATABASE_URL from the environment, then
    from .env, as the app's KernelConfig reads it (Codex on #92)."""
    from kernel.config import KernelConfig

    return KernelConfig().database_url


def config(database_url: str | None = None) -> Config:
    """An Alembic config for this site, on `database_url`, else the app's."""
    url = database_url if database_url is not None else app_database_url()
    cfg = Config(stdout=sys.stdout)
    # Alembic's config is an ini file: a literal %, in a path as in the URL, is
    # written doubled (CodeRabbit on #92).
    cfg.set_main_option("script_location", _ini(str(SCRIPT_LOCATION)))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("version_locations", _ini(os.pathsep.join(migration_dirs())))
    cfg.set_main_option("sqlalchemy.url", _ini(url))
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
    return migrate.command_line(argv, config, prog="python -m app.migrations")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

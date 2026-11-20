"""Alembic, set up in code: one environment, one branch per module (SPEC.md section 10).

    python -m app.migrations upgrade            (with PYTHONPATH=backend)

The kernel's revisions carry the branch label `kernel`; each module's first
revision carries its id and depends on the kernel's. `version_locations` lists
`backend/migrations/kernel/` and each module's folder there, so
`upgrade("heads")` runs them all in order. Railway runs `upgrade` before each
deploy goes live (README.md, "Deploying").
"""

from __future__ import annotations

import os
import sys

from alembic import command
from alembic.config import Config

from app import BACKEND

MIGRATIONS = BACKEND / "migrations"
SCRIPT_LOCATION = BACKEND / "alembic"
VERBS = ("upgrade", "downgrade", "heads", "history", "current")


def migration_dirs() -> list[str]:
    """The kernel's migrations, then each module's, in id order."""
    found = [MIGRATIONS / "kernel"]
    if MIGRATIONS.is_dir():
        found += sorted(
            path for path in MIGRATIONS.iterdir() if path.is_dir() and path.name != "kernel"
        )
    return [str(path) for path in found if path.is_dir()]


def app_database_url() -> str:
    """The database the app uses: DATABASE_URL from the environment, then
    from .env, as the app's KernelConfig reads it (Codex on #92)."""
    from kernel.config import KernelConfig

    return KernelConfig().database_url


def config(database_url: str | None = None) -> Config:
    """An Alembic config for this site, on `database_url`, else the app's."""
    url = database_url if database_url is not None else app_database_url()
    cfg = Config(stdout=sys.stdout)
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("version_locations", os.pathsep.join(migration_dirs()))
    # Alembic's config is an ini file: a literal % must be doubled.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(database_url: str | None = None, target: str = "heads") -> None:
    command.upgrade(config(database_url), target)


def downgrade(database_url: str | None = None, target: str = "base") -> None:
    command.downgrade(config(database_url), target)


def main(argv: list[str]) -> int:
    """`upgrade [target]`, `downgrade [target]`, `heads`, `history` or `current`."""
    if not argv or argv[0] not in VERBS:
        print(f"usage: python -m app.migrations {'|'.join(VERBS)} [target]")
        return 2
    cfg = config()
    action, rest = argv[0], argv[1:]
    if action == "upgrade":
        command.upgrade(cfg, rest[0] if rest else "heads")
    elif action == "downgrade":
        command.downgrade(cfg, rest[0] if rest else "-1")
    elif action == "heads":
        command.heads(cfg, verbose=True)
    elif action == "history":
        command.history(cfg, verbose=True)
    else:
        command.current(cfg, verbose=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Alembic, set up in code: one environment, one branch per module.

The kernel's revisions carry the branch label `kernel`; each module's first
revision carries its id as a label and depends on the kernel's
(SPEC.md section 10). `version_locations` lists the kernel's folder and every
module's, so `upgrade("heads")` runs them all in order.

From a terminal, `python -m harness.migrations upgrade` does the same with the
database in DATABASE_URL.
"""

from __future__ import annotations

import os
import sys

from alembic import command
from alembic.config import Config

from harness.layout import ROOT, migration_dirs

SCRIPT_LOCATION = ROOT / "harness" / "alembic"


def config(database_url: str | None = None) -> Config:
    """An Alembic config for this repo. `database_url` overrides the app's."""
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("version_locations", os.pathsep.join(str(p) for p in migration_dirs()))
    if database_url is not None:
        # Alembic's config is an ini file: a literal % must be doubled.
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade(database_url: str | None = None, target: str = "heads") -> None:
    command.upgrade(config(database_url), target)


def downgrade(database_url: str | None = None, target: str = "base") -> None:
    command.downgrade(config(database_url), target)


def main(argv: list[str]) -> int:
    """`upgrade [target]`, `downgrade [target]`, `heads` or `history`."""
    if not argv or argv[0] not in {"upgrade", "downgrade", "heads", "history", "current"}:
        print(
            "usage: python -m harness.migrations upgrade|downgrade|heads|history|current [target]"
        )
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

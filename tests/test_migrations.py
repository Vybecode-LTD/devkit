"""Every migration round-trips, and the models match what the migrations make
(SPEC.md section 10; KICKOFF.md K0 step 7).

- Upgrade, downgrade, upgrade on an empty database leaves the same schema.
- After the upgrade, the models and the database agree (`alembic check`).
- The kernel's first revision is labelled `kernel`. Each module's first
  revision is labelled with its id and depends on the kernel.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from harness.layout import KERNEL, module_dirs
from harness.migrations import config, downgrade, upgrade
from harness.models import load_all
from kernel.db import Base, async_database_url


async def _sync(url: str, work: Any) -> Any:
    engine = create_async_engine(async_database_url(url))
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(work)
    finally:
        await engine.dispose()


def _schema(connection: Connection) -> dict[str, list[str]]:
    found = inspect(connection)
    return {
        table: sorted(column["name"] for column in found.get_columns(table))
        for table in sorted(found.get_table_names())
        if table != "alembic_version"
    }


def _drift(connection: Connection) -> list[Any]:
    load_all()
    return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))


async def test_upgrade_downgrade_upgrade(empty_database_url: str) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    first = await _sync(empty_database_url, _schema)
    await asyncio.to_thread(downgrade, empty_database_url)
    assert await _sync(empty_database_url, _schema) == {}
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await _sync(empty_database_url, _schema) == first


async def test_models_match_the_migrations(empty_database_url: str) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await _sync(empty_database_url, _drift) == []


def test_branches_are_labelled() -> None:
    script = ScriptDirectory.from_config(config())
    kernel_dir = (KERNEL / "migrations").resolve()
    module_by_dir = {(path / "migrations").resolve(): path.name for path in module_dirs()}
    for revision in script.walk_revisions():
        if revision.down_revision is not None:
            continue
        folder = Path(revision.path).resolve().parent
        if folder == kernel_dir:
            assert revision.branch_labels == {"kernel"}, revision.path
        else:
            module_id = module_by_dir[folder]
            assert revision.branch_labels == {module_id}, revision.path
            assert revision.dependencies, f"{revision.path} must depend on the kernel"

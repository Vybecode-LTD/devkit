"""Every branch upgrades, downgrades and upgrades again on an empty database
(SPEC.md section 10), so a deploy can always go forward and a module can come out."""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import pytest

from app import migrations


async def _tables(url: str) -> set[str]:
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        rows = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    finally:
        await connection.close()
    return {row["tablename"] for row in rows}


async def test_upgrade_downgrade_upgrade(empty_database_url: str) -> None:
    await asyncio.to_thread(migrations.upgrade, empty_database_url)
    made = await _tables(empty_database_url)
    assert {"auth_user", "kernel_setting"} <= made
    await asyncio.to_thread(migrations.downgrade, empty_database_url)
    assert await _tables(empty_database_url) <= {"alembic_version"}
    await asyncio.to_thread(migrations.upgrade, empty_database_url)
    assert await _tables(empty_database_url) == made


def test_the_database_comes_from_dotenv_as_the_apps_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """README.md keeps DATABASE_URL in .env: the migrations read it there, as
    the app's KernelConfig does (Codex on #92). A URL given still wins."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    url = "postgresql://dotenv:secret@db.test/from_dotenv"
    (tmp_path / ".env").write_text(f"DATABASE_URL={url}\n", "utf-8")
    assert migrations.config().get_main_option("sqlalchemy.url") == url
    given = "postgresql://u:p%40ss@db.test/given"
    assert migrations.config(given).get_main_option("sqlalchemy.url") == given


def test_the_command_says_how_to_use_it() -> None:
    assert migrations.main([]) == 2
    assert migrations.main(["sideways"]) == 2

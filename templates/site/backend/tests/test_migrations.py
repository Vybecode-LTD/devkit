"""Every branch upgrades, downgrades and upgrades again on an empty database
(SPEC.md section 10), so a deploy can always go forward and a module can come out."""

from __future__ import annotations

import asyncio

import asyncpg

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


def test_the_command_says_how_to_use_it() -> None:
    assert migrations.main([]) == 2
    assert migrations.main(["sideways"]) == 2

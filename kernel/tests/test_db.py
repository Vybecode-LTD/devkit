"""The database helpers: URLs, get_db and one-row tables."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import Integer, MetaData, String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kernel.db import NAMING, Database, async_database_url, for_saving, one_row_only


class _Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Brand(_Base):
    """A one-row table of the test's own, made and dropped here."""

    __tablename__ = "test_brand"
    __table_args__ = (one_row_only("test_brand"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), server_default="Untitled")


@pytest_asyncio.fixture(loop_scope="session")
async def brand_table(database: Database) -> AsyncIterator[Database]:
    async with database.engine.begin() as connection:
        await connection.run_sync(_Base.metadata.create_all)
    yield database
    async with database.engine.begin() as connection:
        await connection.run_sync(_Base.metadata.drop_all)


def test_async_urls() -> None:
    assert async_database_url("postgres://a@b/c") == "postgresql+asyncpg://a@b/c"
    assert async_database_url("postgresql://a@b/c") == "postgresql+asyncpg://a@b/c"
    assert async_database_url("postgresql+asyncpg://a@b/c") == "postgresql+asyncpg://a@b/c"


async def test_two_first_saves_make_one_row(brand_table: Database) -> None:
    async def save(name: str) -> None:
        async with brand_table.sessions() as session:
            row = await for_saving(session, Brand)
            row.name = name
            await session.commit()

    await asyncio.gather(save("One"), save("Two"))
    async with brand_table.sessions() as session:
        assert (await session.execute(select(func.count()).select_from(Brand))).scalar() == 1
        row = await for_saving(session, Brand, name="ignored once the row exists")
        assert row.name in {"One", "Two"}

"""The database layer: the declarative base, the engine and a session per request.

Lifted from VybeSite `core/database.py`, `models/base.py` and
`services/one_row.py`. One Postgres database per site (SPEC.md section 10).

- **Names.** Constraint names follow one convention, so Alembic's
  autogenerate names them the same on every machine and a migration can drop
  them by name.
- **The engine** is the app's (`create_app` makes one `Database` and closes it
  on shutdown), so tests build apps on their own databases. Bound values are
  never written into errors or logs (`hide_parameters`).
- **`get_db`** gives each request one session, closed after it. Routes and
  services commit themselves; nothing is committed for them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypeVar

from fastapi import Request
from sqlalchemy import Index, MetaData, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The base for every table in a site: the kernel's and each module's."""

    metadata = MetaData(naming_convention=NAMING)


def one_row_only(table: str) -> Index:
    """A unique index on a constant, so the table holds one row at most.

    For tables that hold one set of values. Rows are made with
    `for_saving`, never `db.add`, so two first saves at once write the one
    row instead of failing on this index.
    """
    return Index(f"uq_{table}_one_row", text("(true)"), unique=True)


def async_database_url(url: str) -> str:
    """The URL with asyncpg as its driver. Railway and most hosts hand out
    `postgres://` or `postgresql://`; SQLAlchemy's async engine needs
    `postgresql+asyncpg://`."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


class Database:
    """One site's engine and its session factory."""

    def __init__(
        self, url: str, *, pool_size: int = 5, max_overflow: int = 10, echo: bool = False
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            async_database_url(url),
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            hide_parameters=True,
        )
        self.sessions = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session for this request, closed after it."""
    database: Database = request.app.state.database
    async with database.sessions() as session:
        yield session


Row = TypeVar("Row", bound=Base)


async def _first[Row](db: AsyncSession, model: type[Row]) -> Row | None:
    statement = select(model).limit(1).execution_options(populate_existing=True)
    return (await db.execute(statement)).scalars().first()


async def for_saving[Row](db: AsyncSession, model: type[Row], **values: Any) -> Row:
    """A one-row table's row, made now if there is none, for the caller to
    fill in and commit.

    Made by INSERT … ON CONFLICT DO NOTHING against the one-row index, then
    read back: a save that loses the race to another finds that row rather
    than adding a second. `values` fill the row only when it is made here.
    """
    row = await _first(db, model)
    if row is None:
        await db.execute(insert(model).values(**values).on_conflict_do_nothing())
        row = await _first(db, model)
    if row is None:  # the insert or a concurrent one made it; never seen otherwise
        raise RuntimeError(f"{model.__name__} has no row even after making one.")
    return row

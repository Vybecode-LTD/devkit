"""The database layer: the declarative base every kernel and module model uses.

Lifted from VybeSite `models/base.py`. Constraint names follow one convention,
so Alembic's autogenerate names them the same on every machine and a
migration can drop them by name.
"""

from __future__ import annotations

from sqlalchemy import Index, MetaData, text
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

    For tables that hold one set of values, such as a settings section. Rows
    are made with `one_row.for_saving`, never `db.add`, so two first saves at
    once write the one row instead of failing on this index.
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

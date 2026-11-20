"""Alembic's environment for this site: every branch, one async engine.

The URL is `sqlalchemy.url` when the caller set one (the tests), else the
app's DATABASE_URL. Migrations run in one transaction per revision. The
kernel's models and each module's are imported, so `Base.metadata` holds
every table the migrations make.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app import package  # puts backend/modules on sys.path
from app.modules import MODULE_IDS
from kernel.db import Base, async_database_url

config = context.config


def load_models() -> None:
    """The kernel's models and each module's `models.py`, where it has one."""
    importlib.import_module("kernel.models")
    for module_id in MODULE_IDS:
        name = f"{package(module_id)}.models"
        if importlib.util.find_spec(name) is not None:
            importlib.import_module(name)


load_models()
target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("No database to migrate: set DATABASE_URL.")
    return async_database_url(url)


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_online())

"""This site's test setup: made-up secrets and a throwaway Postgres.

**Secrets of its own.** The kernel refuses to start outside DEBUG on a
placeholder secret, and tests start it. These are made up here, never used
anywhere else, and override a local .env's, so no test signs or decrypts with
a real key, mails anyone or reaches a real bucket. DEBUG is off, as live.

**A throwaway Postgres.** A test that needs a database asks for a fixture
below. The server is compose.yaml's (`docker compose up -d db`) or
TEST_DATABASE_URL's, an admin URL whose role may create databases. Each run
makes its own database and drops it after; a migration test gets an empty one
of its own. With no server those tests are skipped with a note, unless
MECHFRAME_REQUIRE_DB=1 (CI), which fails them instead.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet

os.environ.update(
    {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": Fernet.generate_key().decode(),
        "DEBUG": "false",
        "SITE_NAME": "Test Site",
        "SITE_URL": "https://site.test",  # .test is reserved (RFC 2606), never live
        "WEB_DIST": "",
        "SENTRY_DSN": "",
        "MODULES": "*",
        "CLIENT_IP_HEADER": "",
        "HSTS_MAX_AGE": "0",
        "CORS_ORIGINS": "",
        "JOBS_IN_WEB": "false",
        "STORAGE_ENDPOINT_URL": "",
        "STORAGE_ACCESS_KEY_ID": "",
        "STORAGE_SECRET_ACCESS_KEY": "",
        "STORAGE_BUCKET": "",
        "STORAGE_PUBLIC_BUCKET": "",
        "STORAGE_PUBLIC_URL": "",
        "MAIL_FROM": "",
        "SMTP_HOST": "",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "RESEND_API_KEY": "",
    }
)

import asyncpg  # after the environment, which the kernel reads
import pytest
import pytest_asyncio

ADMIN_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://site:site@localhost:5432/postgres")
REQUIRE_DB = os.environ.get("MECHFRAME_REQUIRE_DB") == "1"
DB_FIXTURES = {"server_url", "migrated_url", "empty_database_url"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that uses a database fixture `db`, so `-m "not db"`
    runs the rest without a server."""
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.db)


def _with_database(url: str, name: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


def _plain(url: str) -> str:
    """asyncpg takes postgresql:// only."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _admin() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(_plain(ADMIN_URL), timeout=3)
    except (OSError, asyncpg.PostgresError, TimeoutError) as error:
        where = urlsplit(ADMIN_URL)
        message = (
            f"No test Postgres at {where.hostname}:{where.port} ({type(error).__name__}). "
            "Start it with `docker compose up -d db`, or set TEST_DATABASE_URL."
        )
        if REQUIRE_DB:
            pytest.fail(message)
        pytest.skip(message)


async def _create(name: str) -> None:
    admin = await _admin()
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()


async def _drop(name: str) -> None:
    """Drop a throwaway database, its sessions first. A role without
    superuser can't end autovacuum's, so FORCE may be refused: then end the
    role's own sessions and drop it plainly."""
    admin = await _admin()
    try:
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        except asyncpg.InsufficientPrivilegeError:
            await admin.execute(
                "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity"
                " WHERE datname = $1 AND usename = current_user AND pid <> pg_backend_pid()",
                name,
            )
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await admin.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def server_url() -> str:
    """The test server's admin URL, after checking it answers."""
    admin = await _admin()
    await admin.close()
    return ADMIN_URL


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def migrated_url(server_url: str) -> AsyncIterator[str]:
    """A database for this run with every migration applied, dropped after."""
    name = f"site_test_{uuid.uuid4().hex[:12]}"
    await _create(name)
    url = _with_database(server_url, name)
    from app.migrations import upgrade

    await asyncio.to_thread(upgrade, url)
    yield url
    await _drop(name)


@pytest_asyncio.fixture(loop_scope="session")
async def empty_database_url(server_url: str) -> AsyncIterator[str]:
    """An empty database of this test's own, dropped after."""
    name = f"site_empty_{uuid.uuid4().hex[:12]}"
    await _create(name)
    yield _with_database(server_url, name)
    await _drop(name)

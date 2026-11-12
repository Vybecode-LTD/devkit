"""The test run's setup, for the kernel's tests, every module's and the repo's.

**Secrets of its own.** The kernel refuses to start outside DEBUG on a
placeholder secret (kernel/config.py), and tests start it. The values are
made up here and never used anywhere else, and they override a local .env's,
so no test signs or decrypts with a real key. DEBUG is off, as in production.

**A throwaway Postgres.** Tests that need a database ask for a fixture below.
The server is the one in compose.yaml (`docker compose up -d db`), or
TEST_DATABASE_URL's. Each run makes its own database and drops it after; a
migration test gets an empty one of its own. When no server answers, those
tests are skipped with a note, unless DEVKIT_REQUIRE_DB=1 (CI), which fails
them instead.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet

os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["ENCRYPTION_KEYS"] = Fernet.generate_key().decode()
os.environ["DEBUG"] = "false"
os.environ["SITE_URL"] = "https://devkit.test"  # .test is reserved (RFC 2606), never live
os.environ["SENTRY_DSN"] = ""
os.environ["MODULES"] = "*"
os.environ["CLIENT_IP_HEADER"] = ""
os.environ["HSTS_MAX_AGE"] = "0"
os.environ["ROBOTS_NOINDEX"] = "false"
os.environ["CORS_ORIGINS"] = ""
os.environ.setdefault("LOG_FORMAT", "text")

import asyncpg  # after the environment, which the kernel reads
import pytest
import pytest_asyncio

import harness  # noqa: F401  (puts the kernel and modules on sys.path)

# The real kernel package, imported before pytest collects kernel/tests/: with
# --import-mode=importlib pytest names those files kernel.tests.*, and would
# otherwise put a stand-in `kernel` module in sys.modules for their parent.
import kernel  # noqa: F401

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://devkit:devkit@localhost:5432/postgres"
)
REQUIRE_DB = os.environ.get("DEVKIT_REQUIRE_DB") == "1"
DB_FIXTURES = {"server_url", "database_url", "empty_database_url", "migrated_url", "db", "engine"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that uses a database fixture `db`, so `-m "not db"`
    runs the rest without a server."""
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.db)


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _plain(url: str) -> str:
    """asyncpg takes postgresql:// only."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _admin() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(_plain(ADMIN_URL), timeout=3)
    except (OSError, asyncpg.PostgresError, TimeoutError) as error:
        message = (
            f"No test Postgres at {urlsplit(ADMIN_URL).hostname}:{urlsplit(ADMIN_URL).port} "
            f"({type(error).__name__}). Start it with `docker compose up -d db`."
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
    admin = await _admin()
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
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
    name = f"devkit_test_{uuid.uuid4().hex[:12]}"
    await _create(name)
    url = _with_database(server_url, name)
    from harness.migrations import upgrade

    await asyncio.to_thread(upgrade, url)
    yield url
    await _drop(name)


@pytest_asyncio.fixture(loop_scope="session")
async def empty_database_url(server_url: str) -> AsyncIterator[str]:
    """An empty database of this test's own, dropped after."""
    name = f"devkit_empty_{uuid.uuid4().hex[:12]}"
    await _create(name)
    yield _with_database(server_url, name)
    await _drop(name)

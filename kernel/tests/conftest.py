"""Fixtures for the kernel's tests: configs, apps built on the test database,
an HTTP client that runs the app's lifespan, and a session."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.config import KernelConfig
from kernel.db import Database
from kernel.modules import InstalledModule, Manifest

SITE = "https://devkit.test"


def make_config(**overrides: Any) -> KernelConfig:
    """A config from the test environment (conftest.py's secrets), with overrides."""
    return KernelConfig(**overrides)


@pytest.fixture
def config_factory() -> Callable[..., KernelConfig]:
    return make_config


def manifest(module_id: str, *, requires: dict[str, str] | None = None) -> Manifest:
    return Manifest.from_dict(
        {
            "id": module_id,
            "name": module_id.replace("-", " ").title(),
            "version": "0.1.0",
            "requires": {"kernel": "^0.1", "modules": requires or {}},
        }
    )


def unique_id(prefix: str = "mod") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture(loop_scope="session")
async def database(migrated_url: str) -> AsyncIterator[Database]:
    db = Database(migrated_url, pool_size=2, max_overflow=2)
    yield db
    await db.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.sessions() as session:
        yield session


AppFactory = Callable[..., FastAPI]


@pytest.fixture
def app_factory(migrated_url: str) -> AppFactory:
    from kernel.app import create_app

    def build(installed: list[InstalledModule] | None = None, **overrides: Any) -> FastAPI:
        config = make_config(**{"database_url": migrated_url, **overrides})
        return create_app(modules=installed or [], config=config)

    return build


class Client:
    """An HTTP client on an app, with its lifespan run."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        self._client = httpx.AsyncClient(transport=transport, base_url=SITE)
        return self._client

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()
        await self._lifespan.__aexit__(None, None, None)

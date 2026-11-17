"""Fixtures for the kernel's tests: configs, apps built on the test database,
an HTTP client that runs the app's lifespan, a session, and a listener that
hears the kernel's events."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import events, jobs, server_copy
from kernel.config import KernelConfig
from kernel.db import Database
from kernel.email import LogMailer
from kernel.modules import InstalledModule, Manifest, ModuleRegistry
from kernel.worker import Worker

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


class Draining(httpx.ASGITransport):
    """An app's transport that runs the app's due jobs after each answer, as
    a site's worker would a moment later (kernel.jobs): what a request queued,
    such as its mail, is there for the test to check, and a check that
    nothing was sent proves something."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        worker = getattr(getattr(self.app, "state", None), "worker", None)
        if worker is not None:
            await worker.run_due(wait=0)
        return response


class Client:
    """An HTTP client on an app, with its lifespan run. It runs the app's due
    jobs after each answer (`Draining`) unless `drain` is False: for a test
    that counts the app's queries, or whose app has no database."""

    def __init__(self, app: FastAPI, *, drain: bool = True) -> None:
        self.app = app
        self.drain = drain

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        kind = Draining if self.drain else httpx.ASGITransport
        transport = kind(app=self.app, raise_app_exceptions=False)
        self._client = httpx.AsyncClient(transport=transport, base_url=SITE)
        return self._client

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()
        await self._lifespan.__aexit__(None, None, None)


@dataclass
class Heard:
    """A module listening to every kernel event, and a worker delivering to it."""

    worker: Worker
    seen: list[events.Event]

    async def drain(self) -> list[tuple[str, dict[str, Any]]]:
        """Delivers what's due, then every event heard so far, by name and payload."""
        await self.worker.run_due(wait=0)
        return [(event.name, event.payload) for event in self.seen]


def kernel_events_only() -> None:
    """Installs the kernel's events, heard by no one, as before any app."""
    events.install(events.build([("kernel", events.KERNEL_PAYLOADS, (), None)], allowed=()))


@pytest_asyncio.fixture(loop_scope="session")
async def heard(migrated_url: str) -> AsyncIterator[Heard]:
    """Hears the kernel's events emitted during the test. List it after the
    fixture that builds the test's app: building an app installs that app's
    events in its place."""
    ear = unique_id("ear")
    names = sorted(
        found[0] for found in map(events.declaration, events.KERNEL_PAYLOADS) if found is not None
    )
    seen: list[events.Event] = []

    async def record(ctx: jobs.Context, event: events.Event) -> None:
        seen.append(event)

    listeners = tuple(
        events.on(name, f"{ear}.heard_{number}")(record) for number, name in enumerate(names)
    )
    listed = {"emits": [], "listens": names}
    module = InstalledModule(
        Manifest.from_dict({**manifest(ear).raw, "events": listed}), listeners=listeners
    )
    events.install(
        events.build(
            [("kernel", events.KERNEL_PAYLOADS, (), None), (ear, (), listeners, listed)],
            allowed=[ear],
        )
    )
    database = Database(migrated_url, pool_size=2, max_overflow=2)
    worker = Worker(
        [listener.job for listener in listeners],
        registry=ModuleRegistry([module], [ear], ttl=0),
        database=database,
        mailer=LogMailer(),
    )
    try:
        yield Heard(worker, seen)
    finally:
        kernel_events_only()
        await database.dispose()


# --- public pages (kernel.server_copy) ------------------------------------------------


class FakePages(server_copy.Pages):
    """A module's pages for the tests: `answers` by path, `entries` for its
    sitemap, and `error`, raised by every read when set. It records what it
    was asked."""

    def __init__(
        self,
        answers: dict[str, server_copy.Page | server_copy.Moved | None] | None = None,
        entries: list[server_copy.Entry] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.answers = answers or {}
        self.entries = entries or []
        self.error = error
        self.asked: list[tuple[str, dict[str, str]]] = []

    async def page(
        self, db: AsyncSession, path: str, params: Mapping[str, str]
    ) -> server_copy.Page | server_copy.Moved | None:
        self.asked.append((path, dict(params)))
        if self.error is not None:
            raise self.error
        return self.answers.get(path)

    async def sitemap(self, db: AsyncSession) -> list[server_copy.Entry]:
        if self.error is not None:
            raise self.error
        return self.entries


def public_module(
    module_id: str,
    *,
    public: list[str] | None = None,
    member: list[str] | None = None,
    pages: server_copy.Pages | None = None,
    name: str | None = None,
) -> InstalledModule:
    """A module with public and member pages in its manifest's routes."""
    raw = {
        **manifest(module_id).raw,
        "name": name or manifest(module_id).name,
        "routes": {
            "api": f"/api/{module_id}",
            "public": public or [],
            "member": member or [],
            "admin": [],
        },
    }
    return InstalledModule(Manifest.from_dict(raw), pages=pages)

"""The test-support routes are mounted only on request, never by harness.main."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts

from harness import testing


def test_refused_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_TEST_SUPPORT", raising=False)
    with pytest.raises(RuntimeError, match="HARNESS_TEST_SUPPORT=1"):
        testing.build_test_app()


def _paths(app: FastAPI) -> set[str]:
    """Every route's full path. FastAPI keeps included routers whole, so
    `app.routes` alone shows only `_IncludedRouter`s with an empty path."""
    return {context.path or "" for context in iter_route_contexts(app.routes)}


def test_the_check_sees_test_routes_where_they_are(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    """The positive control: the same check finds them on the test app."""
    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    app = testing.build_test_app(migrated_url)
    assert "/api/_test/reset" in _paths(app)


def test_the_plain_harness_has_no_test_routes(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    import importlib

    from kernel.config import reset_config

    monkeypatch.setenv("DATABASE_URL", migrated_url)
    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")  # even with the flag set
    reset_config()
    try:
        main = importlib.reload(importlib.import_module("harness.main"))
        paths = _paths(main.app)
        assert "/api/kernel/health" in paths
        assert not any(path.startswith("/api/_test") for path in paths)
    finally:
        reset_config()


async def test_reset_with_accounts_forgets_every_account(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    """The contract suite's precondition for "the last owner stays"."""
    import uuid

    import httpx
    from sqlalchemy import func, select

    from kernel.auth.models import User
    from kernel.db import Database

    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    app = testing.build_test_app(migrated_url)
    database = Database(migrated_url, pool_size=1, max_overflow=0)
    try:
        async with database.sessions() as session:
            email = f"{uuid.uuid4().hex}@site.test"
            session.add(User(email=email, email_normal=email))
            await session.commit()
        transport = httpx.ASGITransport(app=app)
        headers = {"Origin": "https://devkit.test", "Sec-Fetch-Site": "same-origin"}
        async with httpx.AsyncClient(
            transport=transport, base_url="https://devkit.test", headers=headers
        ) as client:
            assert (await client.post("/api/_test/reset")).status_code == 204
            async with database.sessions() as session:
                assert (await session.scalar(select(func.count()).select_from(User))) >= 1
            kept = await client.post("/api/_test/reset", json={"accounts": True})
            assert kept.status_code == 204, kept.text
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(User)) == 0
    finally:
        await app.state.database.dispose()  # the reset's own pool: no lifespan ran to close it
        await database.dispose()

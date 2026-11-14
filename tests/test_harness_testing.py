"""The test-support routes are mounted only on request, never by harness.main."""

from __future__ import annotations

import httpx
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


def _client(app: FastAPI) -> httpx.AsyncClient:
    headers = {"Origin": "https://devkit.test", "Sec-Fetch-Site": "same-origin"}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://devkit.test", headers=headers
    )


async def test_mail_is_read_by_address_and_forgotten_on_reset(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    """`GET /api/_test/mail?to=`: to, subject and text, oldest first."""
    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    app = testing.build_test_app(migrated_url)
    try:
        await app.state.mailer.send("Quill@site.test", "Confirm", "Open /auth/verify?t=1", "<p>")
        await app.state.mailer.send("bob@site.test", "Other", "someone else's")
        await app.state.mailer.send("quill@site.test", "Again", "second")
        async with _client(app) as client:
            got = await client.get("/api/_test/mail", params={"to": "QUILL@site.test"})
            assert got.status_code == 200, got.text
            assert got.json() == {
                "messages": [
                    {
                        "to": "Quill@site.test",
                        "subject": "Confirm",
                        "text": "Open /auth/verify?t=1",
                    },
                    {"to": "quill@site.test", "subject": "Again", "text": "second"},
                ]
            }
            assert (await client.post("/api/_test/reset")).status_code == 204
            after = await client.get("/api/_test/mail", params={"to": "quill@site.test"})
            assert after.json() == {"messages": []}
    finally:
        await app.state.database.dispose()


async def test_the_harness_mail_sits_behind_the_checks(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    app = testing.build_test_app(migrated_url)
    try:
        with pytest.raises(ValueError, match="subject"):
            await app.state.mailer.send("quill@site.test", "Hi\r\nBcc: eve@evil.test", "text")
        async with _client(app) as client:
            got = await client.get("/api/_test/mail", params={"to": "quill@site.test"})
            assert got.json() == {"messages": []}
    finally:
        await app.state.database.dispose()


async def test_users_makes_an_account_without_judging_its_password(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    """`POST /api/_test/users`: roles, a verified address and a confirmed TOTP,
    and a password no rule would let a person choose."""
    import uuid

    from sqlalchemy import select

    from kernel import crypto
    from kernel.auth.models import Totp, User, UserRole

    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    app = testing.build_test_app(migrated_url)
    email = f"Quill.{uuid.uuid4().hex[:8]}@Site.test"
    try:
        async with _client(app) as client:
            made = await client.post(
                "/api/_test/users",
                json={
                    "email": email,
                    "password": "password1234",
                    "roles": ["admin"],
                    "verified": True,
                    "totp": True,
                },
            )
        assert made.status_code == 201, made.text
        body = made.json()
        assert set(body) == {"id", "totp_secret"}
        async with app.state.database.sessions() as db:
            user = await db.get(User, uuid.UUID(body["id"]))
            assert user is not None
            assert (user.email, user.email_normal) == (email, email.lower())
            assert user.email_verified_at is not None
            assert await app.state.passwords.check("password1234", user.password_hash)
            roles = await db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id))
            assert set(roles) == {"admin"}
            totp = await db.get(Totp, user.id)
            assert totp is not None
            assert totp.confirmed_at is not None
            assert crypto.open(totp.secret_sealed) == body["totp_secret"]
    finally:
        await app.state.database.dispose()


async def test_users_defaults_to_an_unverified_member_with_nothing_else(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    import uuid

    from sqlalchemy import select

    from kernel.auth.models import Totp, User, UserRole

    monkeypatch.setenv("HARNESS_TEST_SUPPORT", "1")
    app = testing.build_test_app(migrated_url)
    try:
        async with _client(app) as client:
            made = await client.post(
                "/api/_test/users", json={"email": f"{uuid.uuid4().hex[:8]}@site.test"}
            )
            refused = await client.post(
                "/api/_test/users", json={"email": "wizard@site.test", "roles": ["wizard"]}
            )
        assert set(made.json()) == {"id"}
        assert (refused.status_code, refused.json()["code"]) == (422, "harness.unknown_role")
        async with app.state.database.sessions() as db:
            user = await db.get(User, uuid.UUID(made.json()["id"]))
            assert user is not None
            assert (user.password_hash, user.email_verified_at) == (None, None)
            roles = await db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id))
            assert set(roles) == {"member"}
            assert await db.get(Totp, user.id) is None
            assert await db.scalar(select(User).where(User.email == "wizard@site.test")) is None
    finally:
        await app.state.database.dispose()

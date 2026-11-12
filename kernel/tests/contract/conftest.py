"""The auth contract suite's client (SPEC.md 14.13; docs/contracts/auth-api.md).

These tests speak HTTP only and import nothing of the kernel, so the same
suite can test a TypeScript port (SPEC.md section 19):

- with CONTRACT_BASE_URL set, against that running server (its harness with
  HARNESS_TEST_SUPPORT=1);
- otherwise against the Python harness in this process, on the test database.

Each test starts from `POST /api/_test/reset`: no rate-limit counts, no mail,
the real clock.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import pytest_asyncio

SITE = "https://devkit.test"
PASSWORD = "correct horse battery staple"


@pytest_asyncio.fixture(loop_scope="session")
async def server(
    migrated_url: str, monkeypatch_session: Any
) -> AsyncIterator[httpx.AsyncBaseTransport]:
    base = os.environ.get("CONTRACT_BASE_URL")
    if base:
        yield httpx.AsyncHTTPTransport()
        return
    monkeypatch_session.setenv("HARNESS_TEST_SUPPORT", "1")
    from harness.testing import build_test_app  # the harness, not the kernel

    app = build_test_app(migrated_url)
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app, raise_app_exceptions=False)


@pytest.fixture(scope="session")
def monkeypatch_session() -> Any:
    patch = pytest.MonkeyPatch()
    yield patch
    patch.undo()


def _base() -> str:
    return os.environ.get("CONTRACT_BASE_URL", SITE)


@pytest_asyncio.fixture(loop_scope="session")
async def api(server: httpx.AsyncBaseTransport) -> AsyncIterator[Api]:
    async with Api(server) as client:
        reset = await client.http.post("/api/_test/reset")
        assert reset.status_code == 204, reset.text
        yield client


class Api:
    """A browser: one cookie jar, same-origin headers on every request."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self.transport = transport
        self.http = httpx.AsyncClient(
            transport=transport,
            base_url=_base(),
            headers={"Origin": _base(), "Sec-Fetch-Site": "same-origin"},
            follow_redirects=False,
        )

    async def __aenter__(self) -> Api:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.http.aclose()

    def another_browser(self) -> Api:
        return Api(self.transport)

    @property
    def session_cookie(self) -> str | None:
        return self.http.cookies.get("__Host-dk_session")

    # --- the test-support routes ---------------------------------------------

    async def make_user(self, **fields: Any) -> User:
        email = fields.pop("email", None) or f"user-{uuid.uuid4().hex[:10]}@site.test"
        body = {"email": email, "password": PASSWORD, "verified": True, **fields}
        response = await self.http.post("/api/_test/users", json=body)
        assert response.status_code == 201, response.text
        data = response.json()
        return User(
            id=data["id"],
            email=email,
            password=body.get("password"),
            totp_secret=data.get("totp_secret"),
        )

    async def mail(self, to: str) -> list[dict[str, str]]:
        response = await self.http.get("/api/_test/mail", params={"to": to})
        assert response.status_code == 200, response.text
        messages: list[dict[str, str]] = response.json()["messages"]
        return messages

    async def last_mail(self, to: str) -> dict[str, str]:
        messages = await self.mail(to)
        assert messages, f"no mail to {to}"
        return messages[-1]

    async def advance(self, seconds: int) -> None:
        response = await self.http.post("/api/_test/clock", json={"advance": seconds})
        assert response.status_code == 204, response.text

    async def run_jobs(self) -> None:
        response = await self.http.post("/api/_test/jobs/run")
        assert response.status_code == 204, response.text

    # --- auth -------------------------------------------------------------------

    async def sign_in(self, user: User, password: str | None = None) -> httpx.Response:
        return await self.http.post(
            "/api/auth/sign-in", json={"email": user.email, "password": password or user.password}
        )

    async def signed_in_as(self, user: User) -> dict[str, Any]:
        response = await self.sign_in(user)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        if body["status"] == "second_factor":
            import pyotp

            assert user.totp_secret, "this account needs a second factor"
            response = await self.http.post(
                "/api/auth/sign-in/second-factor",
                json={"challenge": body["challenge"], "totp": pyotp.TOTP(user.totp_secret).now()},
            )
            assert response.status_code == 200, response.text
            body = response.json()
        assert body["status"] == "signed_in"
        return body

    async def session(self) -> httpx.Response:
        return await self.http.get("/api/auth/session")


@dataclass
class User:
    id: str
    email: str
    password: str | None
    totp_secret: str | None = None


def code_in(text: str) -> str:
    match = re.search(r"\b(\d{6})\b", text)
    assert match, f"no 6-digit code in: {text!r}"
    return match.group(1)


def token_in(text: str, path: str) -> str:
    match = re.search(re.escape(path) + r"\?token=([A-Za-z0-9_\-]+)", text)
    assert match, f"no {path}?token= link in: {text!r}"
    return match.group(1)

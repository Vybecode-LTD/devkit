"""The auth contract suite's client (SPEC.md 14.13; docs/contracts/auth-api.md).

These tests speak HTTP only and import nothing of the kernel, so the same
suite can test a TypeScript port (SPEC.md section 19):

- with CONTRACT_BASE_URL set, against that running server (its harness with
  HARNESS_TEST_SUPPORT=1), with no local database needed;
- otherwise against the Python harness in this process, on the test database.

Each test starts from `POST /api/_test/reset`: no rate-limit counts, no mail,
the real clock, nothing on the fake breach list.

**Not built yet, or broken?** A test for code that hasn't landed is marked
`not_built`: it is expected to fail with `NotBuilt` and nothing else. The
client raises `NotBuilt` only when a route written down in auth-api.md answers
the router's own 404 or 405, which means the route doesn't exist yet. Any other
failure (a typo, a wrong expectation, a fixture that breaks) fails the test,
and a call to a route the contract doesn't name raises `UnknownRoute`.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pyotp
import pytest
import pytest_asyncio

SITE = "https://devkit.test"
#: Not on the bundled list and not seen by Have I Been Pwned (checked 2026-11-12).
PASSWORD = "quiet orbit lantern 4471 marsh"
NEW_PASSWORD = "copper heron valley 2093 tide"
OTHER_PASSWORD = "amber walrus cello 5528 dune"
CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "auth-api.md"
_ROUTE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/[^`?\s]+)")
_ROUTER_CODES = {"kernel.not_found", "kernel.method_not_allowed"}


class NotBuilt(Exception):
    """A route the contract names doesn't exist on this server yet."""


class UnknownRoute(AssertionError):
    """A test called a route that docs/contracts/auth-api.md doesn't name."""


def _contract_routes() -> list[tuple[str, re.Pattern[str]]]:
    routes = []
    for line in CONTRACT.read_text("utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        for method, path in _ROUTE.findall(line.split(" | ", 1)[0]):
            pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path))
            routes.append((method, re.compile(f"^{pattern}$")))
    return routes


CONTRACT_ROUTES = _contract_routes()


def in_contract(method: str, path: str) -> bool:
    return any(m == method and pattern.match(path) for m, pattern in CONTRACT_ROUTES)


#: The mark for a test whose code hasn't landed. Remove it when the test passes.
not_built = pytest.mark.xfail(raises=NotBuilt, strict=True, reason="K2: not built yet")


def _base() -> str:
    return os.environ.get("CONTRACT_BASE_URL", SITE).rstrip("/")


def cookie_domain() -> str:
    return urlsplit(_base()).hostname or "devkit.test"


@contextmanager
def _test_support_flag() -> Iterator[None]:
    before = os.environ.get("HARNESS_TEST_SUPPORT")
    os.environ["HARNESS_TEST_SUPPORT"] = "1"
    try:
        yield
    finally:
        if before is None:
            del os.environ["HARNESS_TEST_SUPPORT"]
        else:
            os.environ["HARNESS_TEST_SUPPORT"] = before


@pytest.fixture(scope="session")
def contract_database(request: pytest.FixtureRequest) -> str | None:
    """The test database, only for the in-process harness: a remote server
    under CONTRACT_BASE_URL needs none here."""
    if os.environ.get("CONTRACT_BASE_URL"):
        return None
    url: str = request.getfixturevalue("migrated_url")
    return url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def server(contract_database: str | None) -> AsyncIterator[httpx.AsyncBaseTransport]:
    """One server for the whole suite; `/api/_test/reset` isolates the tests."""
    if contract_database is None:
        yield httpx.AsyncHTTPTransport()
        return
    migrated_url = contract_database
    from harness.testing import build_test_app  # the harness, not the kernel

    with _test_support_flag():
        app = build_test_app(migrated_url)
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app, raise_app_exceptions=False)


@pytest_asyncio.fixture(loop_scope="session")
async def api(server: httpx.AsyncBaseTransport) -> AsyncIterator[Api]:
    async with Api(server) as client:
        reset = await client.http.post("/api/_test/reset")
        assert reset.status_code == 204, reset.text
        yield client


#: Pass as `extensions=UNCHECKED` for a probe that calls what isn't an API route
#: on purpose (a scanner opening a link with GET).
UNCHECKED = {"devkit_unchecked": True}


async def _check_route(response: httpx.Response) -> None:
    request = response.request
    if request.extensions.get("devkit_unchecked"):
        return
    path = request.url.path
    if not in_contract(request.method, path):
        raise UnknownRoute(f"{request.method} {path} isn't in docs/contracts/auth-api.md")
    if response.status_code in (404, 405):
        await response.aread()
        try:
            code = response.json().get("code")
        except ValueError:
            code = None
        if code in _ROUTER_CODES or code is None:
            raise NotBuilt(f"{request.method} {path} answered {response.status_code} ({code})")


class Api:
    """A browser: one cookie jar, same-origin headers on every request, and
    each route checked against the contract (`UNCHECKED` skips the check)."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self.transport = transport
        headers = {"Origin": _base(), "Sec-Fetch-Site": "same-origin"}
        self.http = httpx.AsyncClient(
            transport=transport,
            base_url=_base(),
            headers=headers,
            follow_redirects=False,
            event_hooks={"response": [_check_route]},
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

    def plant_cookie(self, name: str, value: str) -> None:
        self.http.cookies.set(name, value, domain=cookie_domain(), path="/")

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

    async def forget_every_account(self) -> None:
        """For a test whose precondition is that no one else exists."""
        response = await self.http.post("/api/_test/reset", json={"accounts": True})
        assert response.status_code == 204, response.text

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

    async def mark_breached(self, *passwords: str) -> None:
        response = await self.http.post("/api/_test/breached", json={"passwords": list(passwords)})
        assert response.status_code == 204, response.text

    async def test_routes(self) -> dict[str, list[str]]:
        response = await self.http.get("/api/_test/routes")
        assert response.status_code == 200, response.text
        routes: dict[str, list[str]] = response.json()
        return routes

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
    """The one 6-digit code a message holds."""
    codes = re.findall(r"(?<![\w-])(\d{6})(?![\w-])", text)
    assert len(codes) == 1, f"expected one 6-digit code in: {text!r}"
    return str(codes[0])


def token_in(text: str, path: str) -> str:
    """The `token` of the one link to `path` a message holds."""
    links = [
        url
        for url in re.findall(r"https?://\S+|/\S+", text)
        if urlsplit(url.rstrip(".,)")).path == path
    ]
    assert len(links) == 1, f"expected one {path} link in: {text!r}"
    tokens = parse_qs(urlsplit(links[0].rstrip(".,)")).query).get("token")
    assert tokens, f"no token in {links[0]!r}"
    return tokens[0]


def wrong_totp(secret: str) -> str:
    """A code that is certainly wrong now, and in the steps either side."""
    totp = pyotp.TOTP(secret)
    now = time.time()
    right = {totp.at(now + drift) for drift in (-30, 0, 30)}
    return next(code for code in (f"{n:06d}" for n in range(10**6)) if code not in right)


def query_param(url: str, name: str) -> str:
    values = parse_qs(urlsplit(url).query).get(name)
    assert values, f"no {name} in {url}"
    return values[0]

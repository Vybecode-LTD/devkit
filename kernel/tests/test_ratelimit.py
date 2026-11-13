"""Rate limits per address or per account (SPEC.md 14.6)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI, Request

from kernel.errors import install_handlers
from kernel.ratelimit import RateLimiter, client_address, parse_rule, rate_limit


@pytest.mark.parametrize(
    ("rule", "amount", "seconds"),
    [
        ("5/15m", 5, 900),
        ("10/1m", 10, 60),
        ("3/h", 3, 3600),
        ("1/1s", 1, 1),
        (" 2 / 2d ", 2, 172800),
    ],
)
def test_rules(rule: str, amount: int, seconds: int) -> None:
    item = parse_rule(rule)
    assert (item.amount, item.get_expiry()) == (amount, seconds)


@pytest.mark.parametrize("rule", ["5", "5/15x", "0/1m", "5/0m", "five/1m", "5 per minute"])
def test_bad_rules(rule: str) -> None:
    with pytest.raises(ValueError, match=r"rate rule|at least one"):
        parse_rule(rule)


async def test_budgets() -> None:
    limiter = RateLimiter()
    assert [await limiter.hit("2/1m", "sign-in", "a") for _ in range(3)] == [True, True, False]
    assert await limiter.used_up("2/1m", "sign-in", "a")
    assert 1 <= await limiter.wait_seconds("2/1m", "sign-in", "a") <= 60
    assert await limiter.hit("2/1m", "sign-in", "b")  # another key
    assert await limiter.hit("2/1m", "other", "a")  # another scope
    await limiter.forget("2/1m", "sign-in", "a")
    assert not await limiter.used_up("2/1m", "sign-in", "a")
    assert await limiter.wait_seconds("2/1m", "sign-in", "a") == 0


async def test_switched_off() -> None:
    limiter = RateLimiter(enabled=False)
    assert all([await limiter.hit("1/1m", "s", "k") for _ in range(5)])
    assert not await limiter.used_up("1/1m", "s", "k")


def _app(header: str = "") -> FastAPI:
    app = FastAPI()
    install_handlers(app)
    app.state.limiter = RateLimiter()
    app.state.client_ip_header = header

    @app.post("/sign-in", dependencies=[Depends(rate_limit("2/1m"))])
    async def sign_in() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/a", dependencies=[Depends(rate_limit("1/1m", scope="shared"))])
    async def a() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/b", dependencies=[Depends(rate_limit("1/1m", scope="shared"))])
    async def b() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/draft", dependencies=[Depends(rate_limit("1/1m", key="account"))])
    async def draft(request: Request) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/who")
    async def who(request: Request) -> dict[str, str]:
        return {"key": client_address(request)}

    return app


def _client(app: FastAPI, address: str = "203.0.113.9") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(address, 1234))
    return httpx.AsyncClient(transport=transport, base_url="https://devkit.test")


async def test_the_dependency_answers_429_at_the_threshold() -> None:
    app = _app()
    async with _client(app) as client:
        codes = [(await client.post("/sign-in")).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        refused = await client.post("/sign-in")
        assert refused.json()["code"] == "kernel.rate_limited"
        assert 1 <= int(refused.headers["retry-after"]) <= 60
    async with _client(app, "198.51.100.7") as other:
        assert (await other.post("/sign-in")).status_code == 200


async def test_a_shared_scope_is_one_budget() -> None:
    async with _client(_app()) as client:
        assert (await client.post("/a")).status_code == 200
        assert (await client.post("/b")).status_code == 429


async def test_ipv6_counts_by_64() -> None:
    app = _app()
    async with _client(app, "2001:db8:1:2:aaaa::1") as one:
        assert (await one.get("/who")).json() == {"key": "2001:db8:1:2::/64"}
    async with _client(app, "::ffff:203.0.113.9") as mapped:
        assert (await mapped.get("/who")).json() == {"key": "203.0.113.9"}


async def test_the_trusted_header_only_when_it_holds_one_address() -> None:
    app = _app("X-Real-IP")
    async with _client(app) as client:
        assert (await client.get("/who", headers={"X-Real-IP": "198.51.100.1"})).json() == {
            "key": "198.51.100.1"
        }
        assert (await client.get("/who", headers={"X-Real-IP": "nonsense"})).json() == {
            "key": "203.0.113.9"
        }
        twice = httpx.Headers([("X-Real-IP", "198.51.100.1"), ("X-Real-IP", "198.51.100.2")])
        assert (await client.get("/who", headers=twice)).json() == {"key": "203.0.113.9"}
    async with _client(_app()) as untrusting:
        assert (await untrusting.get("/who", headers={"X-Real-IP": "198.51.100.1"})).json() == {
            "key": "203.0.113.9"
        }


async def test_a_scope_and_key_cant_spell_another_budget() -> None:
    """`limits` joins its identifiers with "/": a key holding a slash must not
    land on another scope's budget."""
    limiter = RateLimiter()
    for _ in range(2):
        await limiter.hit("2/1m", "auth", "code/victim@x.test")
    assert await limiter.used_up("2/1m", "auth", "code/victim@x.test")
    assert not await limiter.used_up("2/1m", "auth/code", "victim@x.test")


def _routers_app() -> FastAPI:
    """Two modules with the same relative path, one router mounted twice and a
    nested router: each route's budget is its own full path."""
    from fastapi import APIRouter

    app = FastAPI()
    install_handlers(app)
    app.state.limiter = RateLimiter()
    app.state.client_ip_header = ""
    for module in ("alpha", "beta"):
        router = APIRouter()

        @router.post("/sign-in", dependencies=[Depends(rate_limit("1/1m"))])
        async def sign_in() -> dict[str, bool]:
            return {"ok": True}

        nested = APIRouter(prefix="/admin")

        @nested.post("/run", dependencies=[Depends(rate_limit("1/1m"))])
        async def run() -> dict[str, bool]:
            return {"ok": True}

        router.include_router(nested)
        app.include_router(router, prefix=f"/api/{module}")
    shared = APIRouter()

    @shared.post("/ping", dependencies=[Depends(rate_limit("1/1m"))])
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(shared, prefix="/api/one")
    app.include_router(shared, prefix="/api/two")
    return app


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("/api/alpha/sign-in", "/api/beta/sign-in"),
        ("/api/alpha/admin/run", "/api/beta/admin/run"),
        ("/api/one/ping", "/api/two/ping"),
    ],
)
async def test_each_route_has_its_own_budget_under_its_full_path(first: str, second: str) -> None:
    async with _client(_routers_app()) as client:
        assert (await client.post(first)).status_code == 200
        assert (await client.post(first)).status_code == 429
        assert (await client.post(second)).status_code == 200

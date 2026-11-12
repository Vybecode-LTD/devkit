"""The security headers, same-origin writes and the www. redirect (SPEC.md section 15)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from kernel.errors import install_handlers
from kernel.security import (
    ContentSecurityPolicy,
    SameOriginWrites,
    SecurityHeaders,
    WwwRedirect,
    origin_of,
)

SITE = "https://devkit.test"
BASE_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
    "img-src 'self' data: https:; connect-src 'self'; frame-src 'self'; media-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def build(*, on: tuple[str, ...] = (), hsts: int = 0, noindex: bool = False) -> FastAPI:
    app = FastAPI()
    install_handlers(app)

    @app.get("/page")
    async def page() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/blog/posts")
    async def write() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/shop/webhooks/stripe")
    async def webhook() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/not-api")
    async def other() -> dict[str, str]:
        return {"ok": "yes"}

    policy = ContentSecurityPolicy()
    policy.allow("frame-src", "https://www.youtube-nocookie.com", module="embeds")
    policy.allow("script-src", "https://js.stripe.com", module="payments")
    app.add_middleware(SameOriginWrites, origins=[SITE])
    app.add_middleware(WwwRedirect, site_url=SITE)
    app.add_middleware(
        SecurityHeaders, policy=policy, modules_on=lambda: on, hsts_max_age=hsts, noindex=noindex
    )
    return app


def client(app: FastAPI, base: str = SITE) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base)


async def test_headers_on_every_answer() -> None:
    async with client(build()) as c:
        for response in (await c.get("/page"), await c.get("/missing")):
            assert response.headers["content-security-policy"] == BASE_POLICY
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
            assert (
                response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
            )
            assert "strict-transport-security" not in response.headers
            assert "x-robots-tag" not in response.headers


async def test_a_modules_hosts_only_while_it_is_on() -> None:
    async with client(build(on=("embeds",))) as c:
        policy = (await c.get("/page")).headers["content-security-policy"]
    assert "frame-src 'self' https://www.youtube-nocookie.com;" in policy
    assert "js.stripe.com" not in policy


async def test_hsts_over_https_only_once_set() -> None:
    async with client(build(hsts=300)) as c:
        assert (await c.get("/page")).headers["strict-transport-security"] == "max-age=300"
    async with client(build(hsts=300), "http://devkit.test") as c:
        assert "strict-transport-security" not in (await c.get("/page")).headers


async def test_noindex_for_staging() -> None:
    async with client(build(noindex=True)) as c:
        assert (await c.get("/page")).headers["x-robots-tag"] == "noindex"


@pytest.mark.parametrize(
    ("directive", "source", "message"),
    [
        ("style-src", "https://cdn.test", "can't add hosts to style-src"),
        ("script-src", "'unsafe-inline'", "isn't an https origin"),
        ("script-src", "http://cdn.test", "isn't an https origin"),
        ("frame-src", "https://*", "isn't an https origin"),
        ("frame-src", "*", "isn't an https origin"),
    ],
)
def test_modules_cant_weaken_the_policy(directive: str, source: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ContentSecurityPolicy().allow(directive, source)


def test_a_host_is_added_once() -> None:
    policy = ContentSecurityPolicy()
    policy.allow("frame-src", "https://w.soundcloud.com")
    policy.allow("frame-src", "https://w.soundcloud.com")
    assert policy.render().count("w.soundcloud.com") == 1


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 200),  # not a browser
        ({"Sec-Fetch-Site": "same-origin", "Origin": SITE}, 200),
        ({"Origin": "https://DEVKIT.test:443"}, 200),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Sec-Fetch-Site": "same-site"}, 403),
        ({"Origin": "https://evil.test"}, 403),
        ({"Origin": "https://devkit.test:8443"}, 403),
        ({"Sec-Fetch-Site": "same-origin", "Origin": "null"}, 403),
    ],
)
async def test_writes_from_elsewhere_are_refused(headers: dict[str, str], status: int) -> None:
    async with client(build()) as c:
        response = await c.post("/api/blog/posts", headers=headers)
    assert response.status_code == status
    if status == 403:
        assert response.json()["code"] == "kernel.cross_site_write"
        assert response.headers["content-security-policy"] == BASE_POLICY


async def test_webhooks_reads_and_non_api_paths_pass() -> None:
    cross = {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.test"}
    async with client(build()) as c:
        assert (await c.post("/api/shop/webhooks/stripe", headers=cross)).status_code == 200
        assert (await c.post("/not-api", headers=cross)).status_code == 200
        assert (await c.get("/page", headers=cross)).status_code == 200


async def test_www_goes_to_the_site_with_path_and_query() -> None:
    async with client(build(), "https://www.devkit.test") as c:
        response = await c.get("/blog/a%20b?ref=mail&x=1")
    assert response.status_code == 301
    assert response.headers["location"] == "https://devkit.test/blog/a%20b?ref=mail&x=1"
    assert response.headers["x-frame-options"] == "DENY"


async def test_other_hosts_are_answered() -> None:
    async with client(build(), "https://staging.devkit.test") as c:
        assert (await c.get("/page")).status_code == 200


def test_origin_of() -> None:
    assert origin_of("HTTPS://Devkit.Test:443/path") == "https://devkit.test"
    assert origin_of("http://localhost:5173") == "http://localhost:5173"
    assert origin_of("http://[::1]:8000") == "http://[::1]:8000"

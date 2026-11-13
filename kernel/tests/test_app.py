"""The app factory: refusals at start, docs, health, access marks and the harness."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, Depends, WebSocket

import kernel
from harness.layout import KERNEL
from kernel.access import ACCESS_MARK, public, undeclared
from kernel.modules import InstalledModule

from .conftest import AppFactory, Client, manifest


def test_refuses_to_start_on_a_bad_secret(app_factory: AppFactory) -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY is shorter than 43 characters"):
        app_factory(secret_key="short")


def test_refuses_to_start_on_an_unknown_module(app_factory: AppFactory) -> None:
    with pytest.raises(RuntimeError, match="MODULES names blgo, which is not installed"):
        app_factory([InstalledModule(manifest("blog"))], modules="blgo")


def test_refuses_a_missing_requirement(app_factory: AppFactory) -> None:
    with pytest.raises(RuntimeError, match="comments requires blog"):
        app_factory([InstalledModule(manifest("comments", requires={"blog": "^0.1"}))])


async def test_docs_only_with_debug(app_factory: AppFactory) -> None:
    async with Client(app_factory()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404
    async with Client(app_factory(debug=True)) as client:
        assert (await client.get("/openapi.json")).status_code == 200


async def test_health(app_factory: AppFactory) -> None:
    async with Client(app_factory()) as client:
        response = await client.get("/api/kernel/health")
    assert response.json() == {"status": "ok", "version": kernel.__version__, "database": "ok"}
    assert response.headers["x-frame-options"] == "DENY"


async def test_health_without_a_database(app_factory: AppFactory) -> None:
    app = app_factory(database_url="postgresql://devkit:devkit@127.0.0.1:1/none")
    async with Client(app) as client:
        response = await client.get("/api/kernel/health")
    assert (response.status_code, response.json()["database"]) == (503, "unreachable")


def test_every_kernel_route_declares_its_access(app_factory: AppFactory) -> None:
    assert undeclared(app_factory()) == []


def test_a_route_with_no_access_fails_the_audit(app_factory: AppFactory) -> None:
    router = APIRouter()

    @router.post("/open")
    async def open_route() -> None: ...

    app = app_factory([InstalledModule(manifest("leaky"), router=router)])
    assert undeclared(app) == ["POST /api/leaky/open"]


def test_the_audit_sees_admin_routes_marked_public_by_their_router(
    app_factory: AppFactory,
) -> None:
    router = APIRouter()
    admin = APIRouter(prefix="/admin", dependencies=[Depends(public)])

    @admin.delete("/users/{user_id}")
    async def delete_user(user_id: str) -> None: ...

    router.include_router(admin)
    app = app_factory([InstalledModule(manifest("forum"), router=router)])
    assert undeclared(app) == [
        "DELETE /api/forum/admin/users/{user_id} (an admin route can't be public)"
    ]


def test_the_audit_refuses_public_beside_another_mark(app_factory: AppFactory) -> None:
    def member() -> None: ...

    setattr(member, ACCESS_MARK, "member")
    router = APIRouter(dependencies=[Depends(public)])

    @router.get("/mine", dependencies=[Depends(member)])
    async def mine() -> None: ...

    app = app_factory([InstalledModule(manifest("mixed"), router=router)])
    assert undeclared(app) == ["GET /api/mixed/mine (public beside member)"]


def test_the_audit_sees_websockets_and_mounts(app_factory: AppFactory) -> None:
    from starlette.applications import Starlette

    router = APIRouter()

    @router.websocket("/live")
    async def live(websocket: WebSocket) -> None: ...

    @router.websocket("/open-live", dependencies=[Depends(public)])
    async def open_live(websocket: WebSocket) -> None: ...

    app = app_factory([InstalledModule(manifest("chat"), router=router)])
    app.mount("/api/legacy", Starlette())
    assert undeclared(app) == [
        "MOUNT /api/legacy (a mounted app under /api can't declare access)",
        "WEBSOCKET /api/chat/live",
    ]


def test_the_versions_agree() -> None:
    manifest_version = json.loads((KERNEL / "kernel.json").read_text("utf-8"))["version"]
    web = (KERNEL / "web" / "src" / "version.ts").read_text("utf-8")
    assert kernel.__version__ == manifest_version
    assert f'"{manifest_version}"' in web


def test_the_public_surface() -> None:
    for name in kernel.__all__:
        assert hasattr(kernel, name), name


def test_the_harness_builds(monkeypatch: pytest.MonkeyPatch, migrated_url: str) -> None:
    import importlib

    from kernel.config import reset_config

    monkeypatch.setenv("DATABASE_URL", migrated_url)
    reset_config()
    try:
        main = importlib.import_module("harness.main")
        assert undeclared(main.app) == []
        assert Path(main.__file__).name == "main.py"
    finally:
        monkeypatch.undo()
        reset_config()


def _boom_module() -> InstalledModule:
    router = APIRouter()

    @router.get("/boom", dependencies=[Depends(public)])
    async def boom() -> None:
        raise RuntimeError("kaboom")

    @router.post("/echo", dependencies=[Depends(public)])
    async def echo(body: dict[str, str]) -> dict[str, int]:
        return {"keys": len(body)}

    return InstalledModule(manifest("probe"), router=router)


async def test_an_unexpected_error_keeps_the_security_headers(app_factory: AppFactory) -> None:
    """Handled inside SecurityHeaders and not raised on, so the 500 carries the
    headers and the server logs it once (no second "Exception in ASGI
    application")."""
    app = app_factory([_boom_module()])
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="https://devkit.test") as c:
            response = await c.get("/api/probe/boom")  # raises here if the error escapes
    assert (response.status_code, response.json()["code"]) == (500, "kernel.internal_error")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_body_over_the_limit_is_refused(app_factory: AppFactory) -> None:
    app = app_factory([_boom_module()], max_body_bytes=1024)
    big = {"text": "x" * 2000}
    async with Client(app) as client:
        assert (await client.post("/api/probe/echo", json={"a": "b"})).status_code == 200
        declared = await client.post("/api/probe/echo", json=big)
        assert (declared.status_code, declared.json()["code"]) == (413, "kernel.too_large")

        async def chunks() -> AsyncIterator[bytes]:  # no Content-Length: counted as it comes
            yield b'{"text": "'
            for _ in range(20):
                yield b"x" * 100
            yield b'"}'

        streamed = await client.post(
            "/api/probe/echo", content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert (streamed.status_code, streamed.json()["code"]) == (413, "kernel.too_large")

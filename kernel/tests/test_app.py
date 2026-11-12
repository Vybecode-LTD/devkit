"""The app factory: refusals at start, docs, health, access marks and the harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import APIRouter

import kernel
from harness.layout import KERNEL
from kernel.access import undeclared
from kernel.modules import InstalledModule

from .conftest import AppFactory, Client, manifest


def test_refuses_to_start_on_a_bad_secret(app_factory: AppFactory) -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY is shorter than 32 bytes"):
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

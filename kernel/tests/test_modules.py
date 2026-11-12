"""Module switches: MODULES, the admin's switch and requirements (SPEC.md section 12)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.access import public
from kernel.errors import Problem
from kernel.modules import InstalledModule, ModuleRegistry

from .conftest import AppFactory, Client, manifest, unique_id


def registry(*modules: InstalledModule, allowed: set[str] | None = None) -> ModuleRegistry:
    return ModuleRegistry(modules, allowed if allowed is not None else {m.id for m in modules})


def test_requirements_chain() -> None:
    media = InstalledModule(manifest("media"))
    blog = InstalledModule(manifest("blog", requires={"media": "^0.1"}))
    comments = InstalledModule(manifest("comments", requires={"blog": "^0.1"}))
    shop = InstalledModule(manifest("shop"))
    found = registry(media, blog, comments, shop)
    assert found.effective(()) == {"media", "blog", "comments", "shop"}
    assert found.effective({"media"}) == {"shop"}
    assert found.effective({"blog"}) == {"media", "shop"}
    assert found.requiring("blog") == ["comments"]
    assert (
        registry(media, blog, comments, shop, allowed={"blog", "comments"}).effective(()) == set()
    )


def test_bad_installs_are_refused() -> None:
    blog = InstalledModule(manifest("blog", requires={"media": "^0.1"}))
    with pytest.raises(ValueError, match="blog requires media, which is not installed"):
        registry(blog)
    with pytest.raises(ValueError, match="installed twice"):
        registry(InstalledModule(manifest("shop")), InstalledModule(manifest("shop")))


async def test_switching_on_and_off(db: AsyncSession) -> None:
    base, extra = unique_id("base"), unique_id("extra")
    found = registry(
        InstalledModule(manifest(base)), InstalledModule(manifest(extra, requires={base: "^0.1"}))
    )
    assert await found.on(db) == {base, extra}
    assert await found.set_enabled(db, base, False) == set()
    assert found.on_cached() == set()
    assert await found.switched_off(db) >= {base}
    assert await found.set_enabled(db, base, True) == {base, extra}


async def test_unknown_and_disallowed_switches_are_refused(db: AsyncSession) -> None:
    found = registry(
        InstalledModule(manifest("blog")), InstalledModule(manifest("shop")), allowed={"blog"}
    )
    with pytest.raises(Problem) as unknown:
        await found.set_enabled(db, "nope", False)
    assert (unknown.value.status, unknown.value.code) == (422, "kernel.module_unknown")
    with pytest.raises(Problem) as disallowed:
        await found.set_enabled(db, "shop", True)
    assert disallowed.value.code == "kernel.module_not_allowed"


def _module_with_route(module_id: str) -> InstalledModule:
    router = APIRouter()

    @router.get("/hello", dependencies=[Depends(public)])
    async def hello() -> dict[str, str]:
        return {"hello": module_id}

    return InstalledModule(manifest(module_id), router=router)


async def test_a_module_switched_off_answers_404(app_factory: AppFactory) -> None:
    module_id = unique_id("greet")
    app = app_factory([_module_with_route(module_id)])
    async with Client(app) as client:
        assert (await client.get(f"/api/{module_id}/hello")).json() == {"hello": module_id}
        assert module_id in (await client.get("/api/kernel/modules")).json()["on"]
        async with app.state.database.sessions() as session:
            await app.state.modules.set_enabled(session, module_id, False)
        off = await client.get(f"/api/{module_id}/hello")
        assert (off.status_code, off.json()["code"]) == (404, "kernel.module_off")
        assert module_id not in (await client.get("/api/kernel/modules")).json()["on"]
        async with app.state.database.sessions() as session:
            await app.state.modules.set_enabled(session, module_id, True)
        assert (await client.get(f"/api/{module_id}/hello")).status_code == 200


async def test_modules_left_out_of_MODULES_are_never_mounted_on(app_factory: AppFactory) -> None:
    module_id = unique_id("greet")
    app = app_factory(
        [_module_with_route(module_id), InstalledModule(manifest("other"))], modules="other"
    )
    async with Client(app) as client:
        assert (await client.get(f"/api/{module_id}/hello")).status_code == 404
        assert (await client.get("/api/kernel/modules")).json() == {"on": ["other"]}

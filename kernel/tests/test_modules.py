"""Module switches: MODULES, the admin's switch and requirements (SPEC.md section 12)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import event
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


# --- one short-lived cache for require_module and the CSP (audit F14) ---


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_the_on_set_is_read_at_most_once_per_ttl(db: AsyncSession) -> None:
    module_id = unique_id("cached")
    clock = _Clock()
    here = ModuleRegistry([InstalledModule(manifest(module_id))], {module_id}, ttl=5, clock=clock)
    elsewhere = registry(InstalledModule(manifest(module_id)))  # another process
    assert await here.on(db) == {module_id}
    await elsewhere.set_enabled(db, module_id, False)
    clock.now += 4
    assert await here.on(db) == {module_id}  # still the set read 4 s ago
    clock.now += 2
    assert await here.on(db) == set()  # past the ttl: read again
    assert await here.set_enabled(db, module_id, True) == {module_id}  # its own switch: at once


def _counting_queries(app: FastAPI) -> list[str]:
    seen: list[str] = []

    def count(*args: object) -> None:
        seen.append(str(args[2]))

    event.listen(app.state.database.engine.sync_engine, "before_cursor_execute", count)
    return seen


async def test_module_requests_dont_read_the_database_while_its_fresh(
    app_factory: AppFactory,
) -> None:
    module_id = unique_id("greet")
    app = app_factory([_module_with_route(module_id)])
    async with Client(app) as client:
        assert (await client.get(f"/api/{module_id}/hello")).status_code == 200
        seen = _counting_queries(app)
        assert (await client.get(f"/api/{module_id}/hello")).status_code == 200
        assert seen == []


def _embeds(module_id: str) -> InstalledModule:
    return InstalledModule(manifest(module_id), csp=(("frame-src", "https://player.vimeo.com"),))


async def test_another_process_switching_a_module_reaches_this_ones_csp(
    app_factory: AppFactory,
) -> None:
    """No module request in between: the page's own headers notice."""
    module_id = unique_id("embeds")
    first = app_factory([_embeds(module_id)], modules_cache_seconds=0)
    second = app_factory([_embeds(module_id)], modules_cache_seconds=0)
    async with Client(first), Client(second) as client:
        assert "player.vimeo.com" in (await client.get("/")).headers["content-security-policy"]
        async with first.state.database.sessions() as session:
            await first.state.modules.set_enabled(session, module_id, False)
        assert "player.vimeo.com" not in (await client.get("/")).headers["content-security-policy"]
        async with first.state.database.sessions() as session:
            await first.state.modules.set_enabled(session, module_id, True)
        assert "player.vimeo.com" in (await client.get("/")).headers["content-security-policy"]


async def test_the_page_keeps_the_last_set_when_the_database_doesnt_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    module_id = unique_id("cached")
    clock = _Clock()
    found = ModuleRegistry([InstalledModule(manifest(module_id))], {module_id}, ttl=5, clock=clock)

    def down() -> AsyncSession:
        raise OSError("connection refused")

    with caplog.at_level(logging.WARNING, logger="kernel.modules"):
        assert await found.current(down) == {module_id}
        assert await found.current(down) == {module_id}  # not tried again inside the ttl
    assert caplog.text.count("Couldn't read which modules are switched off") == 1


async def test_an_older_read_cant_undo_a_switch_made_here(db: AsyncSession) -> None:
    """Review of #9: a refresh that read before the switch, and finishes after
    it, must not put the old set back for another TTL."""
    module_id = unique_id("raced")
    found = registry(InstalledModule(manifest(module_id)))
    await found.on(db)
    first_read = asyncio.Event()
    release = asyncio.Event()
    reads = 0
    real = found.switched_off

    async def switched_off(session: AsyncSession) -> frozenset[str]:
        nonlocal reads
        reads += 1
        if reads == 1:  # the refresh that started first: it sees the old state
            first_read.set()
            await release.wait()
            return frozenset()
        return await real(session)

    found.switched_off = switched_off  # type: ignore[method-assign]
    stale = asyncio.create_task(found.on(db, fresh=True))
    await first_read.wait()
    async with AsyncSession(db.bind) as other:
        assert await found.set_enabled(other, module_id, False) == set()
    release.set()
    await stale
    assert found.on_cached() == set()
    assert await found.on(db) == set()  # and the cache is still the switch's

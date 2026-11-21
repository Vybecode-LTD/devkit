"""Module switches: MODULES, the admin's switch and requirements (SPEC.md section 12)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import events, server_copy
from kernel.access import public
from kernel.errors import Problem
from kernel.models import AuditEvent
from kernel.modules import InstalledModule, ModuleRegistry, load_module, module_jobs

from .conftest import AppFactory, Client, Heard, manifest, unique_id


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


@pytest.mark.parametrize("taken", ["auth", "kernel", "site"])
def test_a_module_can_t_take_the_kernel_s_own_ids(taken: str) -> None:
    """`/api/auth` and `/api/kernel` are the kernel's routes, `kernel` its
    Alembic branch, and both its table prefixes: a module of either id would
    collide with them, and its spec would fold into the kernel's (cubic on #78)."""
    with pytest.raises(ValueError, match=f"{taken} is the kernel's own"):
        registry(InstalledModule(manifest(taken)))


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
    assert (unknown.value.status, unknown.value.code) == (404, "kernel.module_unknown")
    with pytest.raises(Problem) as disallowed:
        await found.set_enabled(db, "shop", True)
    assert (disallowed.value.status, disallowed.value.code) == (422, "kernel.module_not_allowed")
    # The Features page lists only what MODULES allows.
    assert [item["id"] for item in await found.listing(db)] == ["blog"]


async def test_a_switch_is_logged_once_and_heard_for_each_module_it_changes(
    db: AsyncSession, heard: Heard
) -> None:
    """A switch emits kernel.module.disabled or .enabled for every module whose
    on-state it changed, the one requiring it too (SPEC 11); a switch to where
    it already is changes nothing (K4 contract change 19)."""
    base, extra = unique_id("base"), unique_id("extra")
    found = registry(
        InstalledModule(manifest(base)), InstalledModule(manifest(extra, requires={base: "^0.1"}))
    )
    await found.set_enabled(db, base, False)
    await found.set_enabled(db, base, False)  # already off
    await found.set_enabled(db, extra, True)  # already on, and still off with base
    await found.set_enabled(db, base, True)
    assert sorted((name, payload["module"]) for name, payload in await heard.drain()) == sorted(
        [
            ("kernel.module.disabled", base),
            ("kernel.module.disabled", extra),
            ("kernel.module.enabled", base),
            ("kernel.module.enabled", extra),
        ]
    )
    logged = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.target_type == "kernel.module")
            .where(AuditEvent.target_id.in_([base, extra]))
            .order_by(AuditEvent.id)
        )
    ).all()
    assert [(entry.action, entry.target_id, entry.details) for entry in logged] == [
        ("kernel.module.disabled", base, {"on": [], "off": sorted([base, extra])}),
        ("kernel.module.enabled", base, {"on": sorted([base, extra]), "off": []}),
    ]


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
    async with Client(app, drain=False) as client:  # the queue's own queries aside
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


# --- building a module from its manifest (kernel.modules.load_module) ---------------------


def _module_folder(root: Path, module_id: str, files: dict[str, str]) -> Path:
    """A module's manifest beside its package's files, as a site holds it
    (`backend/modules/<id_>/`, module.json inside the package)."""
    package = root / module_id.replace("-", "_")
    package.mkdir(parents=True)
    raw = {
        "id": module_id,
        "name": module_id.title(),
        "version": "0.1.0",
        "requires": {"kernel": "^0.1", "modules": {}},
        "routes": {"api": f"/api/{module_id}", "public": ["/photos"], "member": [], "admin": []},
    }
    (package / "module.json").write_text(json.dumps(raw), "utf-8")
    for name, body in files.items():
        (package / name).write_text(body, "utf-8")
    return package


def test_load_module_builds_a_module_from_its_fixed_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_id = unique_id("gallery")
    name = module_id.replace("-", "_")
    folder = _module_folder(
        tmp_path,
        module_id,
        {
            "__init__.py": 'CSP = [("frame-src", "https://player.test")]\n',
            "router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
            "schemas.py": "from pydantic import BaseModel\nclass Settings(BaseModel):\n    size: int = 3\n",
            "emails.py": (
                "from kernel import email\n"
                f'EMAILS = {{"{module_id}.new_photo": email.Template("New photo", "See it.")}}\n'
            ),
            "jobs.py": (
                "from kernel import jobs\n"
                f'@jobs.handler("{module_id}.resize")\n'
                "async def resize(ctx, payload):\n"
                "    return None\n"
            ),
            "events.py": (
                "from kernel import events, jobs\n"
                "from kernel.events import UserDeleted\n"
                f"@events.payload('{module_id}.photo.added', v=1)\n"
                "class Added(events.Payload):\n"
                "    photo_id: int\n"
                f"@events.on('auth.user.deleted', '{module_id}.forget_user')\n"
                "async def forget_user(ctx: jobs.Context, event: events.Event) -> None:\n"
                "    return None\n"
            ),
            "moderation.py": (
                "from kernel import moderation\n"
                "from kernel.moderation import Kind\n"
                f'@moderation.kind("{module_id}.photo", actions=("hide",))\n'
                "class Photo(moderation.Kind):\n"
                "    async def describe(self, db, id):\n"
                "        return None\n"
                "    async def apply(self, db, id, action):\n"
                "        return None\n"
            ),
            "server_copy.py": (
                "from kernel import server_copy\n"
                "class GalleryPages(server_copy.Pages):\n"
                "    async def page(self, db, path, params):\n"
                "        return None\n"
                "PAGES = GalleryPages()\n"
            ),
            "lifecycle.py": (
                "import uuid\n"
                "from sqlalchemy import MetaData\n"
                "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\n"
                "from kernel import lifecycle\n"
                "class _Base(DeclarativeBase):\n"
                "    metadata = MetaData()\n"
                "class Photo(lifecycle.Publishable, _Base):\n"
                f"    __tablename__ = '{name}_photo'\n"
                f"    __content_type__ = '{module_id}.photo'\n"
                "    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)\n"
                "PUBLISHABLE = (Photo,)\n"
            ),
            "search.py": (
                "from kernel import search\n"
                "class Photos(search.Source):\n"
                f"    content_type = '{module_id}.photo'\n"
                "    async def document(self, db, content_id):\n"
                "        return None\n"
                "    async def documents(self, db):\n"
                "        for _ in ():\n"
                "            yield _\n"
                "SEARCH = (Photos(),)\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        module = load_module(folder / "module.json")
    finally:
        for loaded in [each for each in sys.modules if each.startswith(name)]:
            del sys.modules[loaded]
    assert module.id == module_id
    assert module.manifest.version == "0.1.0"
    assert module.router is not None
    assert module.settings is not None
    assert module.settings().model_dump() == {"size": 3}
    assert module.csp == (("frame-src", "https://player.test"),)
    assert list(module.emails) == [f"{module_id}.new_photo"]
    assert [job.name for job in module.jobs] == [f"{module_id}.resize"]
    assert [events.declaration(model) for model in module.payloads] == [
        (f"{module_id}.photo.added", 1)
    ]
    assert [listener.name for listener in module.listeners] == [f"{module_id}.forget_user"]
    assert [kind.name for kind in module.reportable] == [f"{module_id}.photo"]
    assert isinstance(module.pages, server_copy.Pages)
    assert [model.__content_type__ for model in module.publishable] == [f"{module_id}.photo"]
    assert [source.content_type for source in module.searchable] == [f"{module_id}.photo"]


def test_a_modules_vocabularies_reach_the_taxonomy_from_its_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Taxonomy is the manifest's alone (decision 0052, hook 2): what discovery
    reads from module.json is what the start's checks build on."""
    from kernel import taxonomy

    module_id = unique_id("library")
    folder = _module_folder(tmp_path, module_id, {"__init__.py": ""})
    raw = json.loads((folder / "module.json").read_text("utf-8"))
    raw["vocabularies"] = [{"key": "shelves", "label": "Shelves", "hierarchical": True}]
    raw["content_types"] = [{"key": f"{module_id}.book", "label": "Book", "taxonomy": ["shelves"]}]
    (folder / "module.json").write_text(json.dumps(raw), "utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        found = taxonomy.build([load_module(folder / "module.json")])
    finally:
        for loaded in [each for each in sys.modules if each.startswith(folder.name)]:
            del sys.modules[loaded]
    assert found.vocabularies["shelves"].modules == (module_id,)
    assert found.content_types == {f"{module_id}.book": frozenset({"shelves"})}


def test_load_module_of_a_package_with_none_of_the_names_or_none_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_id, absent_id = unique_id("bare"), unique_id("absent")
    bare = _module_folder(tmp_path, bare_id, {"__init__.py": ""})
    absent = _module_folder(tmp_path, absent_id, {})
    (absent / "module.json").rename(tmp_path / "absent.json")
    absent.rmdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        found = load_module(bare / "module.json")
    finally:
        for loaded in [each for each in sys.modules if each.startswith(bare_id.replace("-", "_"))]:
            del sys.modules[loaded]
    assert (found.router, found.settings, found.pages) == (None, None, None)
    assert (
        found.csp,
        found.jobs,
        found.payloads,
        found.listeners,
        found.reportable,
        found.publishable,
        found.searchable,
    ) == ((), (), (), (), (), (), ())
    assert found.emails == {}
    assert module_jobs(f"{absent_id.replace('-', '_')}.jobs") == ()  # no package at all
    # Its package isn't importable: the manifest only.
    nothing = load_module(tmp_path / "absent.json")
    assert nothing.id == absent_id
    assert nothing.router is None

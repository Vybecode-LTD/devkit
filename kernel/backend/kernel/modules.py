"""Which modules a site has, and which are on (SPEC.md section 12).

Lifted from VybeSite's parts (`services/parts.py`, `middleware/parts.py`),
with the list of modules read from the installed manifests instead of a
fixed tuple.

**Who decides:** the developer at deploy, the admin within it. MODULES lists
the modules a deploy may use (`kernel.config.modules_allowed`); the admin
switches any of those off on the Features page (`kernel_module_state`). A
module is **on** when MODULES allows it, the admin hasn't switched it off,
and every module it requires (`requires.modules`) is on.

**What off means:** its routes answer 404 (`require_module`, which the kernel
puts in front of every module router), its slots are hidden, its jobs pause
and its event handlers wait (K3). Its data is kept, so switching it back on
resumes.

**One short-lived cache.** The on-set is read from the database at most once
every MODULES_CACHE_SECONDS (5 by default) per process, and shared: by
`require_module`, the security headers' CSP (`current`, before each
response) and `/api/kernel/modules`. A switch made in this process applies
at once; one made by another worker reaches this one within the TTL, in both
directions. If the database doesn't answer, the last set read stands and the
miss is logged, once per TTL.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, events
from kernel.db import get_db
from kernel.email import Template
from kernel.errors import Problem
from kernel.events import Listener, Payload
from kernel.jobs import Job
from kernel.models import ModuleState

if TYPE_CHECKING:  # kernel.moderation reads OFF from here; server_copy builds from these
    from kernel.moderation import Kind
    from kernel.search import Source
    from kernel.server_copy import Pages


@dataclass(frozen=True)
class Manifest:
    """The parts of a module.json the kernel acts on. `raw` holds the rest."""

    id: str
    name: str
    version: str
    requires: dict[str, str]
    raw: dict[str, Any] = field(repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            requires=dict(data.get("requires", {}).get("modules", {})),
            raw=data,
        )

    @classmethod
    def from_file(cls, path: Path) -> Manifest:
        return cls.from_dict(json.loads(path.read_text("utf-8")))

    @property
    def package(self) -> str:
        """The id as a Python package: hyphens become underscores."""
        return self.id.replace("-", "_")


@dataclass(frozen=True)
class InstalledModule:
    """A module as the app is built from it."""

    manifest: Manifest
    router: APIRouter | None = None
    #: The module's settings model, stored by `kernel.settings`.
    settings: type[BaseModel] | None = None
    #: Hosts the module adds to the CSP while it's on: (directive, https origin).
    csp: tuple[tuple[str, str], ...] = ()
    #: The module's email templates, each named `<id>.<name>` (kernel.email).
    #: A site may reword them through create_app(emails=...).
    emails: Mapping[str, Template] = field(default_factory=dict)
    #: The module's jobs, each named `<id>.<name>` (kernel.jobs): what its
    #: `jobs.py` declares with `@jobs.handler` and `@jobs.scheduled`.
    jobs: tuple[Job, ...] = ()
    #: The event payloads the module owns, each `<id>.<entity>.<verb>`, and its
    #: listeners (kernel.events): what its `events.py` declares with
    #: `@events.payload` and `@events.on`.
    payloads: tuple[type[Payload], ...] = ()
    listeners: tuple[Listener, ...] = ()
    #: What the module lets people report, each `<id>.<entity>`
    #: (kernel.moderation): what its `moderation.py` declares with `@moderation.kind`.
    reportable: tuple[type[Kind], ...] = ()
    #: The module's public pages (kernel.server_copy): its `server_copy.py`'s
    #: `PAGES`. A module with `routes.public` must have them, and only then.
    pages: Pages | None = None
    #: The module's publishable models (kernel.lifecycle, decision 0052): its
    #: `lifecycle.py`'s `PUBLISHABLE`, each a `lifecycle.Publishable` named by
    #: its `__content_type__`.
    publishable: tuple[type[Any], ...] = ()
    #: The module's search sources (kernel.search, decision 0052): its
    #: `search.py`'s `SEARCH`, a `search.Source` for each content type it
    #: lets site search find.
    searchable: tuple[Source, ...] = ()
    #: The module's seed data (kernel.seed, decision 0052): its `seed.py`'s
    #: `async def seed(db, ctx: kernel.seed.Context) -> None`, or None.
    seed: Callable[[Any, Any], Awaitable[None]] | None = None

    @property
    def id(self) -> str:
        return self.manifest.id


# --- building a module from its manifest ---------------------------------------------------


def _found(module_name: str) -> Any:
    """The module `module_name`, imported, or None when there's no such file."""
    try:
        if importlib.util.find_spec(module_name) is None:
            return None
    except ModuleNotFoundError:  # its package isn't there at all
        return None
    return importlib.import_module(module_name)


def _attribute(module_name: str, attribute: str) -> Any:
    found = _found(module_name)
    return None if found is None else getattr(found, attribute, None)


def module_jobs(module_name: str) -> tuple[Job, ...]:
    """Every `kernel.jobs.Job` in `module_name`: what `@jobs.handler` and
    `@jobs.scheduled` make (decision 0035)."""
    found = _found(module_name)
    if found is None:
        return ()
    return tuple(value for value in vars(found).values() if isinstance(value, Job))


def module_events(
    module_name: str,
) -> tuple[tuple[type[Payload], ...], tuple[Listener, ...]]:
    """The payloads `module_name` declares itself (not ones it imports, such
    as the kernel's) and its listeners (decision 0036)."""
    found = _found(module_name)
    if found is None:
        return (), ()
    values = list(vars(found).values())
    payloads = tuple(
        value
        for value in values
        if isinstance(value, type)
        and value.__module__ == found.__name__
        and events.declaration(value) is not None
    )
    listeners = tuple(value for value in values if isinstance(value, Listener))
    return payloads, listeners


def module_kinds(module_name: str) -> tuple[type[Kind], ...]:
    """The kinds `module_name` declares itself: not `Kind`, nor one it imports
    (decision 0039)."""
    from kernel.moderation import Kind  # moderation reads OFF from here

    found = _found(module_name)
    if found is None:
        return ()
    return tuple(
        value
        for value in vars(found).values()
        if isinstance(value, type)
        and issubclass(value, Kind)
        and value.__module__ == found.__name__
        and value.name
    )


def load_module(manifest: Path) -> InstalledModule:
    """The module whose `module.json` is at `manifest`, built from its
    package's fixed names (decision 0009). The harness and every site build
    their modules with it (K5 contract §2):

    - `<id_>/router.py`'s `router`, mounted at /api/<id>;
    - `<id_>/schemas.py`'s `Settings`, the module's settings model;
    - `<id_>/__init__.py`'s `CSP`, the hosts it adds while it's on, as
      (directive, https origin) pairs;
    - `<id_>/emails.py`'s `EMAILS`, its email templates (kernel.email);
    - `<id_>/jobs.py`'s jobs (kernel.jobs);
    - `<id_>/events.py`'s event payloads and listeners (kernel.events);
    - `<id_>/moderation.py`'s kinds (kernel.moderation);
    - `<id_>/server_copy.py`'s `PAGES`, its public pages (kernel.server_copy);
    - `<id_>/lifecycle.py`'s `PUBLISHABLE`, its publishable models
      (kernel.lifecycle);
    - `<id_>/search.py`'s `SEARCH`, its search sources (kernel.search);
    - `<id_>/seed.py`'s `seed`, its seed data (kernel.seed).

    The package `<id_>` must be importable: the caller puts its folder on
    `sys.path`. A package that isn't there gives the manifest alone."""
    found = Manifest.from_file(manifest)
    package = found.package
    if _found(package) is None:
        return InstalledModule(found)
    payloads, listeners = module_events(f"{package}.events")
    return InstalledModule(
        found,
        router=_attribute(f"{package}.router", "router"),
        settings=_attribute(f"{package}.schemas", "Settings"),
        csp=tuple(_attribute(package, "CSP") or ()),
        emails=dict(_attribute(f"{package}.emails", "EMAILS") or {}),
        jobs=module_jobs(f"{package}.jobs"),
        payloads=payloads,
        listeners=listeners,
        reportable=module_kinds(f"{package}.moderation"),
        pages=_attribute(f"{package}.server_copy", "PAGES"),
        publishable=tuple(_attribute(f"{package}.lifecycle", "PUBLISHABLE") or ()),
        searchable=tuple(_attribute(f"{package}.search", "SEARCH") or ()),
        seed=_attribute(f"{package}.seed", "seed"),
    )


OFF = "This part of the site is switched off."

#: The first key of the switches' advisory lock: pg_advisory_xact_lock(LOCK_CLASS, 0).
LOCK_CLASS = 84712032

log = logging.getLogger(__name__)


#: Ids a module can't take: the kernel's own route prefixes (`/api/auth`,
#: `/api/kernel`), Alembic branch and table prefixes (cubic on #78), and
#: `site`, which names the site's own pages (kernel.server_copy.SITE,
#: decision 0048).
RESERVED_IDS = frozenset({"auth", "kernel", "site"})


class ModuleRegistry:
    def __init__(
        self,
        installed: Iterable[InstalledModule],
        allowed: Iterable[str],
        *,
        ttl: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.installed: dict[str, InstalledModule] = {}
        for module in installed:
            if module.id in RESERVED_IDS:
                raise ValueError(f"{module.id} is the kernel's own id: a module can't take it.")
            if module.id in self.installed:
                raise ValueError(f"Module {module.id} is installed twice.")
            self.installed[module.id] = module
        self.allowed = frozenset(allowed) & set(self.installed)
        for module in self.installed.values():
            missing = sorted(set(module.manifest.requires) - set(self.installed))
            if missing:
                raise ValueError(
                    f"{module.id} requires {', '.join(missing)}, which "
                    f"{'is' if len(missing) == 1 else 'are'} not installed."
                )
        self._cached = self.effective(())
        self.ttl = ttl
        self._clock = clock
        self._read_at: float | None = None  # never read: stale
        #: Reads are numbered as they start; one is kept only if none started
        #: after it has been kept, so a slow read can't undo a newer switch.
        self._reads_started = 0
        self._newest_kept = 0
        self._reading = asyncio.Lock()

    def effective(self, switched_off: Iterable[str]) -> frozenset[str]:
        """The modules on: allowed, not switched off, and with every module
        they require on, through any chain of requirements."""
        on = set(self.allowed) - set(switched_off)
        changed = True
        while changed:
            changed = False
            for module_id in sorted(on):
                if not set(self.installed[module_id].manifest.requires) <= on:
                    on.discard(module_id)
                    changed = True
        return frozenset(on)

    def requiring(self, module_id: str) -> list[str]:
        """The installed modules that can't work without `module_id`."""
        return sorted(
            other.id for other in self.installed.values() if module_id in other.manifest.requires
        )

    async def switched_off(self, db: AsyncSession) -> frozenset[str]:
        statement = select(ModuleState.module_id).where(ModuleState.enabled.is_(False))
        return frozenset((await db.execute(statement)).scalars())

    def _stale(self) -> bool:
        return self._read_at is None or self._clock() - self._read_at >= self.ttl

    async def on(self, db: AsyncSession, *, fresh: bool = False) -> frozenset[str]:
        """The modules on, read through `db` when the cache is past its TTL
        (or `fresh`)."""
        if fresh or self._stale():
            self._reads_started += 1
            number = self._reads_started
            switched_off = await self.switched_off(db)
            if number > self._newest_kept:
                self._newest_kept = number
                self._cached = self.effective(switched_off)
                self._read_at = self._clock()
        return self._cached

    async def current(
        self, sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]]
    ) -> frozenset[str]:
        """The modules on, for code with no session of its own (the CSP):
        read through a new session when the cache is stale; while another
        read is under way, or when the database doesn't answer, the last set."""
        if not self._stale() or self._reading.locked():
            return self._cached
        async with self._reading:
            if self._stale():
                try:
                    async with sessions() as session:
                        await self.on(session)
                except (SQLAlchemyError, OSError) as error:
                    self._read_at = self._clock()  # try again after the TTL, not every request
                    log.warning(
                        "Couldn't read which modules are switched off (%s); keeping the "
                        "last set read.",
                        type(error).__name__,
                    )
        return self._cached

    def on_cached(self) -> frozenset[str]:
        """The on-set this process last read, for code that can't wait on the
        database. Before the first read, every module MODULES allows."""
        return self._cached

    async def set_enabled(
        self, db: AsyncSession, module_id: str, enabled: bool, *, by: Any = None
    ) -> frozenset[str]:
        """Switch a module on or off and commit. Returns the modules on after.

        Refuses a module that isn't installed (404) and one MODULES leaves out
        (422): switched here, it would stay that way when a later deploy
        allows it. Switching one off also turns off every module requiring
        it, which keeps its own switch.

        A switch that changes something is audited as `kernel.module.enabled`
        or `kernel.module.disabled`, and emits that event for every module
        whose on-state it changed, a module requiring it included (SPEC 11).
        Switches take one advisory lock, so two of them never read each
        other's half; one to where it already is changes nothing."""
        if module_id not in self.installed:
            raise Problem("kernel.module_unknown", 404, f"There's no module called {module_id}.")
        if module_id not in self.allowed:
            raise Problem(
                "kernel.module_not_allowed",
                422,
                f"{self.installed[module_id].manifest.name} isn't available on this site "
                "(MODULES), so it can't be switched on or off here.",
            )
        await db.execute(text("SELECT pg_advisory_xact_lock(:kind, 0)"), {"kind": LOCK_CLASS})
        switched_off = await self.switched_off(db)
        if (module_id not in switched_off) == enabled:
            await db.commit()  # ends the transaction, and the lock with it
            return await self.on(db, fresh=True)
        before = self.effective(switched_off)
        after = self.effective(
            switched_off - {module_id} if enabled else switched_off | {module_id}
        )
        statement = insert(ModuleState).values(
            module_id=module_id, enabled=enabled, updated_by_id=by
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ModuleState.module_id],
            set_={
                "enabled": enabled,
                "updated_by_id": by,
                "updated_at": statement.excluded.updated_at,
            },
        )
        await db.execute(statement)
        target = ("kernel.module", module_id)
        details = {"on": sorted(after - before), "off": sorted(before - after)}
        if enabled:
            audit.record(db, "kernel.module.enabled", actor=by, target=target, details=details)
        else:
            audit.record(db, "kernel.module.disabled", actor=by, target=target, details=details)
        for changed in sorted(after - before):
            await events.emit(db, "kernel.module.enabled", events.ModuleEnabled(module=changed))
        for changed in sorted(before - after):
            await events.emit(db, "kernel.module.disabled", events.ModuleDisabled(module=changed))
        await db.commit()
        return await self.on(db, fresh=True)

    async def listing(self, db: AsyncSession) -> list[dict[str, Any]]:
        """The modules MODULES allows, by name, as the Features page shows
        them: `switched` is the admin's switch, `on` also needs every module
        it requires on. Both come from one read of the switches, so a switch
        made meanwhile can't set them at odds (CodeRabbit on #87)."""
        switched_off = await self.switched_off(db)
        on = self.effective(switched_off)
        items = [
            {
                "id": module.id,
                "name": module.manifest.name,
                "summary": str(module.manifest.raw.get("summary", "")),
                "category": str(module.manifest.raw.get("category", "")),
                "on": module.id in on,
                "switched": module.id not in switched_off,
                "requires": sorted(module.manifest.requires),
                "required_by": self.requiring(module.id),
            }
            for module in self.installed.values()
            if module.id in self.allowed
        ]
        return sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))


def require_module(module_id: str) -> Callable[..., Awaitable[None]]:
    """A dependency that answers 404 while `module_id` is off. The kernel puts
    it in front of every module's router; it runs before the route's own
    dependencies, so nothing else is read for a module that's off. It reads
    the shared cache, so most requests cost no query."""

    async def module_is_on(request: Request, db: AsyncSession = Depends(get_db)) -> None:
        registry: ModuleRegistry = request.app.state.modules
        if module_id not in await registry.on(db):
            raise Problem("kernel.module_off", 404, OFF)

    module_is_on.__name__ = f"require_module_{module_id.replace('-', '_')}"
    return module_is_on

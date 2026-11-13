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
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.db import get_db
from kernel.errors import Problem
from kernel.models import ModuleState


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

    @property
    def id(self) -> str:
        return self.manifest.id


OFF = "This part of the site is switched off."

log = logging.getLogger(__name__)


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
        """The last on-set read, for code that can't wait on the database."""
        return self._cached

    async def set_enabled(
        self, db: AsyncSession, module_id: str, enabled: bool, *, by: Any = None
    ) -> frozenset[str]:
        """Switch a module on or off and commit. Returns the modules on after.

        Refuses (422) a module that isn't installed, and one MODULES leaves
        out: switched here, it would stay that way when a later deploy allows
        it. Switching one off also turns off every module requiring it, which
        keeps its own switch."""
        if module_id not in self.installed:
            raise Problem("kernel.module_unknown", 422, f"There's no module called {module_id}.")
        if module_id not in self.allowed:
            raise Problem(
                "kernel.module_not_allowed",
                422,
                f"{self.installed[module_id].manifest.name} isn't available on this site "
                "(MODULES), so it can't be switched on or off here.",
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
        await db.commit()
        # K3: emit kernel.module.enabled / kernel.module.disabled and audit it.
        return await self.on(db, fresh=True)


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

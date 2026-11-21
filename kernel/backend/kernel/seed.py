"""Seed data (SPEC.md sections 4, 7 and 12; hook 4, decision 0052; contract
`dev plans/contracts/hooks.md`).

A module's `seed.py` gives `async def seed(db, ctx: Context) -> None`: rows
that show the module working, for a demo, a review or a screenshot, never a
live site's. It MUST be idempotent: fixed ids or slugs, and a check or an
upsert before each write, so a second run changes nothing. A module without
one takes no part. The site's own (`backend/app/site/seed.py`) has the same
shape and runs last.

`run(db, installed, site=...)` seeds the modules that have one, each after
the modules it requires (`requires.modules`), ties by id, then the site's, in
the one transaction it commits: a seed that raises keeps nothing. The kernel
has nothing of its own to seed: the accounts seeds ask for are made as they
first ask (`Context.user`). A run is audited as `kernel.seed.ran`, with the
parts it seeded.

It refuses unless `MECHFRAME_ALLOW_SEED=1` is in the process's environment,
raising `Refused` before any seed runs. The variable is read from the
environment only, never `.env`, and the site template's `.railway/railway.ts`
never sets it (a template test holds that), so no file turns seeding on for
good: it's set for the one run and cleared after it, in PowerShell
`$env:MECHFRAME_ALLOW_SEED = "1"; try { mechframe seed } finally { Remove-Item Env:MECHFRAME_ALLOW_SEED }`.

`Context` gives each seed:

- `module`, the id it seeds for (`site` for the site's own);
- `now`, a fixed instant, so what a seed writes is the same each run (for a
  time relative to the day it runs, such as a post scheduled for next week,
  use the kernel's clock);
- `random`, a `random.Random` seeded with the module's id, so its draws are
  the same each run and no other module's seed changes them;
- `await user(role)`: a seeded account holding the role and `member`,
  `seed-<role>@example.com`, verified, with no password (no one signs in as
  it), made the first time any seed asks and the role given back if it was
  taken away. Never `owner`, who is made with `mechframe create-owner`, and
  never an account at that address the seed didn't make (one with a
  password, the owner role, an unverified address or not active): the run
  is refused rather than take it over (CodeRabbit on #102);
- `await put_image(name, width=1200, height=630)`: a PNG of one colour (the
  colour drawn from the module and the name) stored in the public bucket at
  `<module>/seed/<name>.png`; answers the key.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import random
import re
import struct
import uuid
import zlib
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, events, storage
from kernel.auth.accounts import normal_email
from kernel.auth.models import Role, User, UserRole
from kernel.auth.permissions import OWNER

if TYPE_CHECKING:
    from kernel.modules import InstalledModule

#: The variable that allows a run, read from the process's environment only.
ALLOW = "MECHFRAME_ALLOW_SEED"
#: Every seed's clock.
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
#: The id the site's own seed runs under.
SITE = "site"
ACTION = "kernel.seed.ran"
_MEMBER = "member"
_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
_MAX_SIDE = 4000


class Refused(Exception):
    """Nothing was seeded; the message says why."""


#: A module's or the site's seed.
Seed = Callable[[AsyncSession, "Context"], Awaitable[None]]


def allowed(environ: Mapping[str, str]) -> bool:
    """Whether `environ` allows seeding: MECHFRAME_ALLOW_SEED=1, nothing else."""
    return environ.get(ALLOW) == "1"


def check_allowed(environ: Mapping[str, str] | None = None) -> None:
    """Refused unless the environment (the process's by default) allows seeding."""
    if not allowed(os.environ if environ is None else environ):
        raise Refused(
            f"Seeding is off: set {ALLOW}=1 in the environment for this one run "
            "(never on a live site, and never in .env or railway.ts)."
        )


class _People:
    """The seeded accounts, by role, shared by every seed in a run."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ids: dict[str, uuid.UUID] = {}

    async def user(self, role: str) -> uuid.UUID:
        if role == OWNER:
            raise ValueError(
                "A seed never makes an owner: the owner is made with mechframe create-owner."
            )
        if role in self.ids:
            return self.ids[role]
        db = self.db
        if await db.get(Role, role) is None:
            raise ValueError(f"There's no role {role}: a seed asks for one the site has.")
        email = f"seed-{role}@example.com"
        normal = normal_email(email)
        person: User | None = await db.scalar(select(User).where(User.email_normal == normal))
        wanted = sorted({_MEMBER, role})
        if person is None:
            person = User(
                email=email,
                email_normal=normal,
                display_name=f"Seed {role}",
                email_verified_at=NOW,
            )
            db.add(person)
            await db.flush()
            await db.refresh(person)  # the columns the database fills in
            db.add_all([UserRole(user_id=person.id, role_id=each) for each in wanted])
            await events.emit(db, "auth.user.created", events.UserCreated(user_id=person.id))
            added = wanted
        else:
            held = set(
                await db.scalars(select(UserRole.role_id).where(UserRole.user_id == person.id))
            )
            if (
                person.password_hash is not None
                or person.email_verified_at is None
                or person.status != "active"
                or OWNER in held
            ):
                raise ValueError(
                    f"{email} isn't one a seed made: it has a password, the owner role, an "
                    "unverified address or isn't active. Delete that account, or seed "
                    f"without the role {role}."
                )
            added = [each for each in wanted if each not in held]
            db.add_all([UserRole(user_id=person.id, role_id=each) for each in added])
            if added:
                person.role_version += 1
        if added:
            await events.emit(
                db,
                "auth.user.role_changed",
                events.UserRoleChanged(user_id=person.id, added=added, removed=[]),
            )
        await db.flush()
        self.ids[role] = person.id
        return person.id


def _png(width: int, height: int, rgb: bytes) -> bytes:
    """A PNG of `width` by `height` pixels, all `rgb`: 8-bit truecolour, no filter."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = (b"\x00" + rgb * width) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


class Context:
    """What a seed is given: its module, a fixed clock, a seeded random, the
    seeded people and placeholder images."""

    def __init__(self, module: str, people: _People) -> None:
        self.module = module
        self.now = NOW
        # Seeded data, never a secret: the same draws every run.
        self.random = random.Random(f"mechframe.seed:{module}")  # noqa: S311
        self._people = people

    async def user(self, role: str) -> uuid.UUID:
        """The seeded account holding `role` (and `member`); made the first time."""
        return await self._people.user(role)

    async def put_image(self, name: str, *, width: int = 1200, height: int = 630) -> str:
        """A one-colour PNG at `<module>/seed/<name>.png` in the public bucket;
        its key. `name` is 1 to 64 lowercase letters, digits and dashes."""
        if not (isinstance(name, str) and _NAME.fullmatch(name)):
            raise ValueError(
                f"{name!r} isn't a seed image's name: 1 to 64 lowercase letters, digits and "
                "dashes, not starting or ending with a dash."
            )
        if not (1 <= width <= _MAX_SIDE and 1 <= height <= _MAX_SIDE):
            raise ValueError(f"A seed image is 1 to {_MAX_SIDE} pixels a side.")
        key = f"{self.module}/seed/{name}.png"
        colour = hashlib.sha256(key.encode()).digest()[:3]
        # Off the event loop: at 4,000 pixels a side it's 48 MB of rows to compress.
        data = await run_in_threadpool(_png, width, height, colour)
        await storage.put(key, data, content_type="image/png", public=True)
        return key


def order(installed: Iterable[InstalledModule]) -> list[InstalledModule]:
    """The modules that seed, each after the modules it requires, ties by id.
    ValueError for a circle of requires."""
    by_id = {module.id: module for module in installed}
    graph = TopologicalSorter(
        {
            ident: [each for each in m.manifest.requires if each in by_id]
            for ident, m in by_id.items()
        }
    )
    try:
        graph.prepare()
    except CycleError as error:
        raise ValueError(f"The modules' requires make a circle: {error.args[1]}.") from None
    ordered: list[InstalledModule] = []
    while graph.is_active():
        ready = sorted(graph.get_ready())
        ordered += [by_id[ident] for ident in ready if by_id[ident].seed is not None]
        graph.done(*ready)
    return ordered


async def run(
    db: AsyncSession,
    installed: Iterable[InstalledModule],
    *,
    site: Seed | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Seeds the installed modules that have a seed, then the site's own, in
    one transaction it commits; answers the ids seeded, in order. Raises
    Refused unless `environ` (the process's by default) allows it."""
    check_allowed(environ)
    parts: list[tuple[str, Seed]] = [
        (module.id, module.seed) for module in order(installed) if module.seed is not None
    ]
    if site is not None:
        parts.append((SITE, site))
    for ident, does in parts:
        if not inspect.iscoroutinefunction(does):
            raise ValueError(f"{ident}'s seed is `async def seed(db, ctx)`, called once a run.")
    people = _People(db)
    try:
        for ident, does in parts:
            await does(db, Context(ident, people))
        seeded = [ident for ident, _ in parts]
        audit.record(db, ACTION, actor=None, details={"seeded": seeded})
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return seeded

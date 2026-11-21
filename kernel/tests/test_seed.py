"""Seed data (decision 0052, hook 4; contract `dev plans/contracts/hooks.md`):
`seed.run` refuses unless MECHFRAME_ALLOW_SEED=1, seeds the modules after
those they require and the site's own last, in one transaction, and a second
run changes nothing; the context's fixed clock, seeded random, seeded people
and placeholder images; and the harness's command."""

from __future__ import annotations

import struct
import uuid
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, MetaData, String, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kernel import seed
from kernel.auth.models import User, UserRole
from kernel.db import NAMING, Database
from kernel.models import AuditEvent
from kernel.modules import InstalledModule, Manifest

pytestmark = pytest.mark.db

ALLOWED = {seed.ALLOW: "1"}
Seed = Callable[[AsyncSession, seed.Context], Awaitable[None]]


class _Base(DeclarativeBase):
    """The tests' own table, apart from the kernel's metadata."""

    metadata = MetaData(naming_convention=NAMING)


class Row(_Base):
    __tablename__ = "seed_test_row"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    module: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    author_id: Mapped[uuid.UUID | None]


@pytest_asyncio.fixture(loop_scope="session")
async def rows(database: Database) -> AsyncIterator[Database]:
    async with database.engine.begin() as connection:
        await connection.run_sync(_Base.metadata.create_all)
    await _forget_the_seeded_people(database)
    try:
        yield database
    finally:
        async with database.engine.begin() as connection:
            await connection.run_sync(_Base.metadata.drop_all)
        await _forget_the_seeded_people(database)


async def _forget_the_seeded_people(database: Database) -> None:
    async with database.sessions() as db:
        await db.execute(delete(User).where(User.email_normal.like("seed-%@example.com")))
        await db.commit()


def _module(
    module_id: str, does: Seed | None = None, requires: tuple[str, ...] = ()
) -> InstalledModule:
    manifest = Manifest.from_dict(
        {
            "id": module_id,
            "name": module_id.title(),
            "version": "0.1.0",
            "summary": "A module for the seed tests",
            "category": "admin",
            "requires": {"modules": dict.fromkeys(requires, "^0.1")},
        }
    )
    return InstalledModule(manifest, seed=does)


def _writes(value: str = "") -> Seed:
    """A seed that upserts one row by a fixed key: a module's idempotent seed."""

    async def does(db: AsyncSession, ctx: seed.Context) -> None:
        drawn = f"{value}{ctx.random.randint(0, 10**9)}"
        key = f"{ctx.module}-row"
        found = await db.get(Row, key)
        if found is None:
            db.add(Row(key=key, module=ctx.module, value=drawn, at=ctx.now))
        else:
            found.value, found.at = drawn, ctx.now

    return does


async def _all_rows(database: Database) -> list[tuple[str, str, str, datetime]]:
    async with database.sessions() as db:
        found = await db.scalars(select(Row).order_by(Row.key))
        return [(row.key, row.module, row.value, row.at) for row in found]


# --- the refusal -------------------------------------------------------------------


@pytest.mark.parametrize("environ", [{}, {seed.ALLOW: "0"}, {seed.ALLOW: "yes"}, {seed.ALLOW: ""}])
async def test_without_the_variable_it_refuses_before_any_seed_runs(
    rows: Database, environ: dict[str, str]
) -> None:
    ran: list[str] = []

    async def does(db: AsyncSession, ctx: seed.Context) -> None:
        ran.append(ctx.module)

    async with rows.sessions() as db:
        with pytest.raises(seed.Refused, match="MECHFRAME_ALLOW_SEED=1"):
            await seed.run(db, [_module("solo", does)], site=does, environ=environ)
    assert ran == []
    assert not seed.allowed(environ)


async def test_by_default_it_reads_the_process_environment(
    rows: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(seed.ALLOW, raising=False)
    async with rows.sessions() as db:
        with pytest.raises(seed.Refused):
            await seed.run(db, [_module("solo", _writes())])
    monkeypatch.setenv(seed.ALLOW, "1")
    async with rows.sessions() as db:
        assert await seed.run(db, [_module("solo", _writes())]) == ["solo"]


# --- the order and the transaction ---------------------------------------------------


async def test_modules_seed_after_those_they_require_ties_by_id_and_the_site_last(
    rows: Database,
) -> None:
    ran: list[str] = []

    async def does(db: AsyncSession, ctx: seed.Context) -> None:
        ran.append(ctx.module)

    installed = [
        _module("alpha", does, requires=("gamma",)),
        _module("gamma", does),
        _module("beta", does),
        _module("delta"),  # takes no part
        _module("epsilon", does, requires=("delta", "alpha")),
    ]
    async with rows.sessions() as db:
        seeded = await seed.run(db, installed, site=does, environ=ALLOWED)
    assert ran == ["beta", "gamma", "alpha", "epsilon", "site"]
    assert seeded == ran


async def test_a_run_is_audited_with_what_it_seeded(rows: Database) -> None:
    async with rows.sessions() as db:
        before = await db.scalar(
            select(func.max(AuditEvent.id)).where(AuditEvent.action == "kernel.seed.ran")
        )
        await seed.run(db, [_module("solo", _writes())], environ=ALLOWED)
    async with rows.sessions() as db:
        found = list(
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "kernel.seed.ran", AuditEvent.id > (before or 0)
                )
            )
        )
    assert [(event.actor_id, event.details) for event in found] == [(None, {"seeded": ["solo"]})]


async def test_a_second_run_changes_nothing(rows: Database) -> None:
    async def with_people(db: AsyncSession, ctx: seed.Context) -> None:
        await _writes()(db, ctx)
        row = await db.get(Row, f"{ctx.module}-row")
        assert row is not None
        row.author_id = await ctx.user("editor")

    installed = [_module("first", with_people), _module("second", _writes("b"))]
    async with rows.sessions() as db:
        await seed.run(db, installed, environ=ALLOWED)
    once = await _all_rows(rows)
    people = await _seeded_people(rows)
    async with rows.sessions() as db:
        await seed.run(db, installed, environ=ALLOWED)
    assert await _all_rows(rows) == once
    assert await _seeded_people(rows) == people
    assert [key for key, *_ in once] == ["first-row", "second-row"]


async def test_a_seed_that_raises_keeps_nothing(rows: Database) -> None:
    async def breaks(db: AsyncSession, ctx: seed.Context) -> None:
        await ctx.user("editor")
        raise RuntimeError("the second module's seed broke")

    async with rows.sessions() as db:
        with pytest.raises(RuntimeError, match="broke"):
            await seed.run(
                db, [_module("first", _writes()), _module("second", breaks)], environ=ALLOWED
            )
    assert await _all_rows(rows) == []
    assert await _seeded_people(rows) == []


async def test_a_seed_that_isnt_an_async_function_is_refused(rows: Database) -> None:
    def plain(db: AsyncSession, ctx: seed.Context) -> None:
        return None

    async with rows.sessions() as db:
        with pytest.raises(ValueError, match="plain's seed"):
            await seed.run(db, [_module("plain", plain)], environ=ALLOWED)  # type: ignore[arg-type]


def test_a_circle_of_requires_is_refused() -> None:
    with pytest.raises(ValueError, match="circle"):
        seed.order([_module("one", requires=("two",)), _module("two", requires=("one",))])


# --- the context -----------------------------------------------------------------------


async def test_the_clock_is_fixed_and_random_is_seeded_with_the_modules_id(
    rows: Database,
) -> None:
    drawn: dict[str, list[list[int]]] = {"first": [], "second": []}
    times: list[datetime] = []

    async def draws(db: AsyncSession, ctx: seed.Context) -> None:
        drawn[ctx.module].append([ctx.random.randint(0, 10**9) for _ in range(5)])
        times.append(ctx.now)

    for _ in range(2):
        async with rows.sessions() as db:
            await seed.run(db, [_module("first", draws), _module("second", draws)], environ=ALLOWED)
    assert drawn["first"][0] == drawn["first"][1]
    assert drawn["second"][0] == drawn["second"][1]
    assert drawn["first"][0] != drawn["second"][0]
    assert times == [datetime(2026, 1, 1, 12, tzinfo=UTC)] * 4 == [seed.NOW] * 4


async def _seeded_people(database: Database) -> list[tuple[str, str | None, bool, list[str]]]:
    async with database.sessions() as db:
        people = await db.scalars(
            select(User).where(User.email_normal.like("seed-%@example.com")).order_by(User.email)
        )
        found = []
        for person in people:
            roles = await db.scalars(
                select(UserRole.role_id)
                .where(UserRole.user_id == person.id)
                .order_by(UserRole.role_id)
            )
            found.append(
                (
                    person.email,
                    person.password_hash,
                    person.email_verified_at == seed.NOW,
                    list(roles),
                )
            )
        return found


async def test_a_seeded_person_holds_the_role_and_member_with_no_password(rows: Database) -> None:
    ids: dict[str, list[uuid.UUID]] = {"first": [], "second": []}

    async def asks(db: AsyncSession, ctx: seed.Context) -> None:
        ids[ctx.module] += [await ctx.user("editor"), await ctx.user("editor")]
        ids[ctx.module].append(await ctx.user("member"))

    async with rows.sessions() as db:
        await seed.run(db, [_module("first", asks), _module("second", asks)], environ=ALLOWED)
    editor, again, member = ids["first"]
    assert editor == again != member
    assert ids["second"] == ids["first"]
    assert await _seeded_people(rows) == [
        ("seed-editor@example.com", None, True, ["editor", "member"]),
        ("seed-member@example.com", None, True, ["member"]),
    ]

    # The admin took the role away: the next run gives it back.
    async with rows.sessions() as db:
        await db.execute(
            delete(UserRole).where(UserRole.user_id == editor, UserRole.role_id == "editor")
        )
        await db.commit()
    async with rows.sessions() as db:
        await seed.run(db, [_module("first", asks)], environ=ALLOWED)
    assert ids["first"][3] == editor
    assert (await _seeded_people(rows))[0][3] == ["editor", "member"]


@pytest.mark.parametrize(
    ("role", "refusal"), [("owner", "create-owner"), ("no-such-role", "no role no-such-role")]
)
async def test_no_owner_is_seeded_and_an_unknown_role_is_refused(
    rows: Database, role: str, refusal: str
) -> None:
    async def asks(db: AsyncSession, ctx: seed.Context) -> None:
        await ctx.user(role)

    async with rows.sessions() as db:
        with pytest.raises(ValueError, match=refusal):
            await seed.run(db, [_module("first", asks)], environ=ALLOWED)
    assert await _seeded_people(rows) == []


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    length, kind = struct.unpack(">I4s", data[8:16])
    assert (length, kind) == (13, b"IHDR")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _png_pixels(data: bytes) -> set[bytes]:
    """Every pixel's RGB in a PNG this module wrote (one IDAT, filter 0)."""
    width, height = _png_size(data)
    at = data.index(b"IDAT")
    (length,) = struct.unpack(">I", data[at - 4 : at])
    raw = zlib.decompress(data[at + 4 : at + 4 + length])
    stride = 1 + width * 3
    assert len(raw) == stride * height
    return {
        raw[row * stride + 1 + x * 3 : row * stride + 4 + x * 3]
        for row in range(height)
        for x in range(width)
    }


async def test_put_image_stores_one_plain_png_under_the_modules_key(
    rows: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored: list[tuple[str, bytes, dict[str, Any]]] = []

    async def put(key: str, data: bytes, **options: Any) -> None:
        stored.append((key, data, options))

    monkeypatch.setattr(seed.storage, "put", put)
    keys: list[str] = []

    async def images(db: AsyncSession, ctx: seed.Context) -> None:
        keys.append(await ctx.put_image("hero"))
        keys.append(await ctx.put_image("thumb", width=40, height=30))

    for _ in range(2):
        async with rows.sessions() as db:
            await seed.run(db, [_module("gallery", images)], site=images, environ=ALLOWED)
    assert keys[:4] == [
        "gallery/seed/hero.png",
        "gallery/seed/thumb.png",
        "site/seed/hero.png",
        "site/seed/thumb.png",
    ]
    assert keys[4:] == keys[:4]
    assert [key for key, _, _ in stored] == keys
    assert all(options == {"content_type": "image/png", "public": True} for *_, options in stored)
    hero, thumb = stored[0][1], stored[1][1]
    assert _png_size(hero) == (1200, 630)
    assert _png_size(thumb) == (40, 30)
    assert len(_png_pixels(thumb)) == 1  # one colour
    assert stored[4][1] == hero  # the same bytes each run
    assert _png_pixels(stored[2][1]) != _png_pixels(hero)  # each module and name its own colour


@pytest.mark.parametrize(
    ("name", "size"),
    [
        ("Hero", {}),
        ("a/b", {}),
        ("", {}),
        ("x" * 65, {}),
        ("hero", {"width": 0}),
        ("hero", {"height": 4001}),
    ],
)
async def test_put_image_refuses_a_bad_name_or_size(
    rows: Database, monkeypatch: pytest.MonkeyPatch, name: str, size: dict[str, int]
) -> None:
    async def put(key: str, data: bytes, **options: Any) -> None:
        raise AssertionError("nothing is stored")

    monkeypatch.setattr(seed.storage, "put", put)

    async def images(db: AsyncSession, ctx: seed.Context) -> None:
        await ctx.put_image(name, **size)

    async with rows.sessions() as db:
        with pytest.raises(ValueError, match="seed image"):
            await seed.run(db, [_module("gallery", images)], environ=ALLOWED)


# --- the harness's command -------------------------------------------------------------


def test_the_harness_command_refuses_without_the_variable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from harness import seed as command

    monkeypatch.delenv(seed.ALLOW, raising=False)
    assert command.main() == 2
    assert "MECHFRAME_ALLOW_SEED=1" in capsys.readouterr().err


def test_the_harness_command_seeds_its_apps_modules_on_its_database(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Allowed, it builds the harness's modules as a worker does, seeds them on
    its database and says what it seeded; a start that's refused is a 2."""
    from harness import seed as command

    ran: list[str] = []

    async def does(db: AsyncSession, ctx: seed.Context) -> None:
        ran.append(ctx.module)

    class Built:
        installed: tuple[InstalledModule, ...] = (_module("solo", does), _module("bare"))

        def database(self) -> Database:
            return Database(migrated_url, pool_size=1, max_overflow=0)

    asked: dict[str, Any] = {}

    def assemble(**given: Any) -> Built:
        asked.update(given)
        return Built()

    monkeypatch.setattr(command, "assemble", assemble)
    monkeypatch.setenv(seed.ALLOW, "1")
    assert command.main() == 0
    assert ran == ["solo"]
    assert asked["role"] == "worker"
    assert capsys.readouterr().out == "Seeded: solo.\n"

    Built.installed = (_module("bare"),)
    assert command.main() == 0
    assert capsys.readouterr().out == "Seeded: nothing, since no module has a seed.\n"

    def refused(**given: Any) -> Built:
        raise RuntimeError("Refusing to start: a module's manifest is wrong")

    monkeypatch.setattr(command, "assemble", refused)
    assert command.main() == 2
    assert "Refused: Refusing to start" in capsys.readouterr().err

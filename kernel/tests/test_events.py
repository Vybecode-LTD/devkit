"""kernel.events: declaring payloads and listeners, emitting in the caller's
transaction, and delivery as jobs (contract k3-events, decision 0036).

Each test's events belong to module ids of its own, and an app's worker
claims only the jobs it has listeners for, so tests sharing the run's
database never run each other's deliveries. The kernel's own emits are tested
beside the changes that make them (sign-up, resets, email change, the
unverified sweep, settings).
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError
from sqlalchemy import Column, MetaData, String, Table, Uuid, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, events, jobs
from kernel.app import create_app
from kernel.auth import unverified
from kernel.auth.accounts import normal_email
from kernel.auth.models import User, UserRole
from kernel.db import Database
from kernel.email import LogMailer
from kernel.models import Job as JobRow
from kernel.models import ModuleState
from kernel.modules import InstalledModule, Manifest
from kernel.tests.conftest import kernel_events_only, make_config, unique_id

Heard = list[tuple[int, events.Event]]


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    """Real time, and only the kernel's events installed after each test: an
    app built here installs its modules' listeners for the whole process."""
    clock.reset()
    yield
    clock.reset()
    kernel_events_only()


async def _nothing(ctx: jobs.Context, event: events.Event) -> None:
    return None


def _payload(owner: str, entity: str = "post", verb: str = "published") -> type[events.Payload]:
    @events.payload(f"{owner}.{entity}.{verb}", v=1)
    class Published(events.Payload):
        post_id: int

    return Published


def _ear(
    owner: str, event: str, name: str = "heard", *, failing: int = 0
) -> tuple[events.Listener, Heard]:
    """A listener that records each try, failing its first `failing` tries."""
    heard: Heard = []

    async def listener(ctx: jobs.Context, delivered: events.Event) -> None:
        heard.append((ctx.try_number, delivered))
        if ctx.try_number <= failing:
            raise ValueError("not yet")

    return events.on(event, f"{owner}.{name}")(listener), heard


def _module(
    module_id: str,
    *,
    payloads: Sequence[type[events.Payload]] = (),
    listeners: Sequence[events.Listener] = (),
    emits: list[str] | None = None,
    listens: list[str] | None = None,
    declared_jobs: Sequence[jobs.Job] = (),
) -> InstalledModule:
    if emits is None:
        emits = [events.declaration(model)[0] for model in payloads]
    if listens is None:
        listens = sorted({listener.event for listener in listeners})
    raw: dict[str, Any] = {
        "id": module_id,
        "name": module_id.title(),
        "version": "0.1.0",
        "requires": {"kernel": "^0.1", "modules": {}},
        "events": {"emits": emits, "listens": listens},
    }
    return InstalledModule(
        Manifest.from_dict(raw),
        jobs=tuple(declared_jobs),
        payloads=tuple(payloads),
        listeners=tuple(listeners),
    )


def _refused(*installed: InstalledModule) -> str:
    with pytest.raises(RuntimeError, match="Refusing to start") as refused:
        create_app(modules=list(installed), config=make_config())
    return str(refused.value)


@asynccontextmanager
async def _site(url: str, *installed: InstalledModule, **config: Any) -> AsyncIterator[FastAPI]:
    app = create_app(
        modules=list(installed),
        config=make_config(database_url=url, modules_cache_seconds=0, **config),
        mailer=LogMailer(),
    )
    # The app's worker runs only its modules' deliveries here: with the
    # kernel's own jobs it would also run mail other tests left queued, once a
    # test moves the clock past their retry.
    worker = app.state.worker
    worker.jobs = {name: job for name, job in worker.jobs.items() if not name.startswith("kernel.")}
    try:
        yield app
    finally:
        await app.state.database.dispose()


def _sessions(app: FastAPI) -> AsyncSession:
    made: AsyncSession = app.state.database.sessions()
    return made


async def _emit(app: FastAPI, name: str, payload: events.Payload) -> int:
    async with _sessions(app) as db:
        queued = await events.emit(db, name, payload)
        await db.commit()
    return queued


async def _deliveries(app: FastAPI, listener: events.Listener) -> list[JobRow]:
    async with _sessions(app) as db:
        rows = await db.scalars(select(JobRow).where(JobRow.name == listener.name))
        return list(rows)


# --- declaring --------------------------------------------------------------------------


def test_the_kernel_declares_the_four_events_it_emits() -> None:
    assert {events.declaration(model) for model in events.KERNEL_PAYLOADS} == {
        ("auth.user.created", 1),
        ("auth.user.verified", 1),
        ("auth.user.deleted", 1),
        ("kernel.settings.changed", 1),
    }
    assert events.declaration(events.UserDeleted) == ("auth.user.deleted", 1)
    assert events.declaration(events.SettingsChanged) == ("kernel.settings.changed", 1)


def test_a_payload_is_frozen_strict_and_refuses_unknown_fields() -> None:
    user_id = uuid.uuid4()
    gone = events.UserDeleted(user_id=user_id)
    with pytest.raises(ValidationError):
        events.UserDeleted(user_id=str(user_id))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        events.UserDeleted(user_id=user_id, email="kim@site.test")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        gone.user_id = uuid.uuid4()  # type: ignore[misc]


def test_a_class_never_declared_has_no_declaration() -> None:
    class Loose(events.Payload):
        n: int

    assert events.declaration(Loose) is None


@pytest.mark.parametrize(
    "name",
    [
        "blog.post",
        "Blog.post.published",
        "blog.post.published.again",
        "blog..published",
        "blog.post.Published",
        "blog_x.post.published",
        "blog.post.1published",
    ],
)
def test_a_payload_s_event_name_is_checked(name: str) -> None:
    with pytest.raises(ValueError, match="event"):

        @events.payload(name, v=1)
        class Bad(events.Payload):
            n: int


@pytest.mark.parametrize("version", [0, -1, True])
def test_a_payload_s_version_is_a_whole_number_from_1(version: Any) -> None:
    with pytest.raises(ValueError, match="version"):

        @events.payload("blog.post.published", v=version)
        class Bad(events.Payload):
            n: int


def test_only_a_payload_model_is_declared() -> None:
    with pytest.raises(TypeError, match=r"events\.Payload"):

        @events.payload("blog.post.published", v=1)
        class Plain(BaseModel):
            n: int


def test_a_listener_is_a_job_of_its_module_that_tries_8_times() -> None:
    listener = events.on("auth.user.deleted", "blog.forget_user", timeout=60)(_nothing)
    assert isinstance(listener, events.Listener)
    assert (listener.event, listener.name, listener.owner) == (
        "auth.user.deleted",
        "blog.forget_user",
        "blog",
    )
    job = listener.job
    assert (job.name, job.tries, job.timeout, job.schedule) == ("blog.forget_user", 8, 60, None)
    assert events.on("auth.user.deleted", "blog.forget")(_nothing).job.timeout == 300


def test_a_listener_s_event_job_name_and_function_are_checked() -> None:
    with pytest.raises(ValueError, match="event"):
        events.on("auth.user", "blog.forget_user")(_nothing)
    with pytest.raises(ValueError, match="job"):
        events.on("auth.user.deleted", "Blog.forget_user")(_nothing)
    with pytest.raises(ValueError, match="timeout"):
        events.on("auth.user.deleted", "blog.forget_user", timeout=0)(_nothing)

    def plain(ctx: jobs.Context, event: events.Event) -> None:
        return None

    with pytest.raises(TypeError, match="async"):
        events.on("auth.user.deleted", "blog.forget_user")(plain)  # type: ignore[arg-type]


def test_an_event_parses_into_the_kernel_s_model_or_a_view_of_its_own() -> None:
    user_id = uuid.uuid4()
    event = events.Event(
        uuid.uuid4(), "auth.user.deleted", 1, clock.now(), {"user_id": str(user_id)}
    )
    assert event.parse(events.UserDeleted) == events.UserDeleted(user_id=user_id)

    class View(BaseModel):
        user_id: uuid.UUID

    assert event.parse(View).user_id == user_id
    with pytest.raises(ValidationError):
        event.parse(events.SettingsChanged)


# --- the start's checks -----------------------------------------------------------------


def test_a_module_declares_only_its_own_events() -> None:
    owner = unique_id()
    message = _refused(_module(owner, payloads=[_payload("other")]))
    assert owner in message
    assert "other.post.published" in message


def test_a_payload_class_never_declared_is_refused() -> None:
    class Loose(events.Payload):
        n: int

    owner = unique_id()
    message = _refused(_module(owner, payloads=[Loose], emits=[]))
    assert "Loose" in message
    assert "@events.payload" in message


def test_a_module_can_t_declare_an_auth_or_kernel_event() -> None:
    message = _refused(_module(unique_id(), payloads=[_payload("auth", "user", "banned")]))
    assert "auth.user.banned" in message


def test_an_event_declared_twice_is_refused() -> None:
    owner = unique_id()
    message = _refused(_module(owner, payloads=[_payload(owner), _payload(owner)]))
    assert f"{owner}.post.published" in message
    assert "twice" in message


@pytest.mark.parametrize("listed", ["missing", "extra"])
def test_module_json_lists_exactly_the_events_its_events_py_declares(listed: str) -> None:
    owner = unique_id()
    if listed == "missing":
        installed = _module(owner, payloads=[_payload(owner)], emits=[])
    else:
        installed = _module(owner, emits=[f"{owner}.post.published"])
    message = _refused(installed)
    assert f"{owner}.post.published" in message
    assert "module.json" in message


@pytest.mark.parametrize("listed", ["missing", "extra"])
def test_module_json_lists_exactly_the_events_its_listeners_hear(listed: str) -> None:
    owner = unique_id()
    if listed == "missing":
        listener, _ = _ear(owner, "auth.user.deleted")
        installed = _module(owner, listeners=[listener], listens=[])
    else:
        installed = _module(owner, listens=["auth.user.deleted"])
    message = _refused(installed)
    assert "auth.user.deleted" in message
    assert "module.json" in message


def test_a_listener_to_an_event_the_kernel_doesn_t_declare_is_refused() -> None:
    listener, _ = _ear(unique_id(), "auth.user.suspended")
    message = _refused(_module(listener.owner, listeners=[listener]))
    assert "auth.user.suspended" in message


def test_a_listener_to_an_event_an_installed_module_doesn_t_declare_is_refused() -> None:
    quiet = unique_id()
    listener, _ = _ear(unique_id(), f"{quiet}.post.published")
    message = _refused(_module(quiet), _module(listener.owner, listeners=[listener]))
    assert f"{quiet}.post.published" in message


def test_a_listener_to_a_module_that_isn_t_installed_is_allowed() -> None:
    listener, _ = _ear(unique_id(), "absent.post.published")
    app = create_app(modules=[_module(listener.owner, listeners=[listener])], config=make_config())
    assert listener.name in app.state.worker.names


def test_a_listener_s_name_is_checked_with_its_module_s_jobs() -> None:
    owner = unique_id()
    stranger, _ = _ear("other", "auth.user.deleted")
    message = _refused(_module(owner, listeners=[stranger]))
    assert f"{owner} may only declare {owner}.* listeners, not other.heard" in message

    listener, _ = _ear(owner, "auth.user.deleted", "send")
    twin = jobs.handler(f"{owner}.send")(_nothing)  # type: ignore[arg-type]
    message = _refused(_module(owner, listeners=[listener], declared_jobs=[twin]))
    assert f"{owner}.send" in message
    assert "twice" in message


def test_a_module_s_listeners_reach_the_app_s_worker() -> None:
    owner = unique_id()
    listener, _ = _ear(owner, "auth.user.deleted")
    app = create_app(modules=[_module(owner, listeners=[listener])], config=make_config())
    assert listener.name in app.state.worker.names


# --- emitting ---------------------------------------------------------------------------


async def test_emit_refuses_an_undeclared_event_and_a_payload_of_another_kind(
    db: AsyncSession,
) -> None:
    gone = events.UserDeleted(user_id=uuid.uuid4())
    with pytest.raises(ValueError, match=r"blog\.post\.published"):
        await events.emit(db, "blog.post.published", gone)
    with pytest.raises(TypeError, match=r"auth\.user\.created"):
        await events.emit(db, "auth.user.created", gone)
    with pytest.raises(TypeError, match=r"auth\.user\.deleted"):
        await events.emit(db, "auth.user.deleted", {"user_id": str(gone.user_id)})  # type: ignore[arg-type]
    await db.rollback()


async def test_a_payload_over_64_kib_is_refused_even_with_no_listener(migrated_url: str) -> None:
    owner = unique_id()

    @events.payload(f"{owner}.note.written", v=1)
    class Written(events.Payload):
        text: str

    async with (
        _site(migrated_url, _module(owner, payloads=[Written])) as app,
        _sessions(app) as db,
    ):
        assert await events.emit(db, f"{owner}.note.written", Written(text="x" * 60_000)) == 0
        with pytest.raises(ValueError, match="64 KiB"):
            await events.emit(db, f"{owner}.note.written", Written(text="x" * 66_000))
        await db.rollback()


async def test_with_no_listener_emit_writes_nothing(migrated_url: str) -> None:
    owner = unique_id()
    published = _payload(owner)
    async with (
        _site(migrated_url, _module(owner, payloads=[published])) as app,
        _sessions(app) as db,
    ):
        before = await db.scalar(select(func.count()).select_from(JobRow))
        assert await events.emit(db, f"{owner}.post.published", published(post_id=1)) == 0
        assert await db.scalar(select(func.count()).select_from(JobRow)) == before
        await db.rollback()


async def test_a_rolled_back_emit_delivers_nothing(migrated_url: str) -> None:
    owner, ear = unique_id(), unique_id()
    published = _payload(owner)
    listener, heard = _ear(ear, f"{owner}.post.published")
    async with _site(
        migrated_url, _module(owner, payloads=[published]), _module(ear, listeners=[listener])
    ) as app:
        async with _sessions(app) as db:
            assert await events.emit(db, f"{owner}.post.published", published(post_id=7)) == 1
            await db.rollback()
        assert await app.state.worker.run_due() == 0
        assert heard == []
        assert await _deliveries(app, listener) == []


async def test_a_committed_event_reaches_each_listener_once_with_one_id(migrated_url: str) -> None:
    owner, first, second = unique_id(), unique_id(), unique_id()
    published = _payload(owner)
    one, heard_one = _ear(first, f"{owner}.post.published")
    two, heard_two = _ear(second, f"{owner}.post.published")
    async with _site(
        migrated_url,
        _module(owner, payloads=[published]),
        _module(first, listeners=[one]),
        _module(second, listeners=[two]),
    ) as app:
        before = clock.now()
        assert await _emit(app, f"{owner}.post.published", published(post_id=7)) == 2
        after = clock.now()
        assert await app.state.worker.run_due() == 2
        assert await app.state.worker.run_due() == 0

    assert [try_number for try_number, _ in heard_one + heard_two] == [1, 1]
    (_, a), (_, b) = heard_one[0], heard_two[0]
    assert a == b
    assert (a.name, a.v, a.payload) == (f"{owner}.post.published", 1, {"post_id": 7})
    assert isinstance(a.id, uuid.UUID)
    assert before <= a.emitted_at <= after


async def test_a_failing_listener_retries_alone(migrated_url: str) -> None:
    owner, shaky, steady = unique_id(), unique_id(), unique_id()
    published = _payload(owner)
    failing, heard_failing = _ear(shaky, f"{owner}.post.published", failing=1)
    working, heard_working = _ear(steady, f"{owner}.post.published")
    async with _site(
        migrated_url,
        _module(owner, payloads=[published]),
        _module(shaky, listeners=[failing]),
        _module(steady, listeners=[working]),
    ) as app:
        await _emit(app, f"{owner}.post.published", published(post_id=7))
        assert await app.state.worker.run_due() == 2
        [row] = await _deliveries(app, failing)
        assert (row.state, row.last_error) == ("queued", "ValueError")
        assert [r.state for r in await _deliveries(app, working)] == ["done"]

        clock.advance(60)  # past the first wait, 30 s give or take 10 %
        assert await app.state.worker.run_due() == 1
        assert [r.state for r in await _deliveries(app, failing)] == ["done"]

    assert [try_number for try_number, _ in heard_failing] == [1, 2]
    assert heard_failing[0][1].id == heard_failing[1][1].id == heard_working[0][1].id
    assert len(heard_working) == 1


async def test_a_delivery_is_dead_after_8_failed_tries(migrated_url: str) -> None:
    owner, ear = unique_id(), unique_id()
    published = _payload(owner)
    listener, heard = _ear(ear, f"{owner}.post.published", failing=99)
    async with _site(
        migrated_url, _module(owner, payloads=[published]), _module(ear, listeners=[listener])
    ) as app:
        await _emit(app, f"{owner}.post.published", published(post_id=7))
        for _ in range(9):
            await app.state.worker.run_due()
            clock.advance(4000)  # past the longest wait, an hour give or take 10 %
        [row] = await _deliveries(app, listener)

    assert (row.state, row.tries, row.last_error) == ("dead", 8, "ValueError")
    assert row.finished_at is not None
    assert [try_number for try_number, _ in heard] == list(range(1, 9))
    assert len({event.id for _, event in heard}) == 1


async def test_a_switched_off_module_s_delivery_waits_until_it_is_back_on(
    migrated_url: str,
) -> None:
    owner, ear = unique_id(), unique_id()
    published = _payload(owner)
    listener, heard = _ear(ear, f"{owner}.post.published")
    async with _site(
        migrated_url, _module(owner, payloads=[published]), _module(ear, listeners=[listener])
    ) as app:
        async with _sessions(app) as db:
            db.add(ModuleState(module_id=ear, enabled=False))
            await db.commit()
        assert await _emit(app, f"{owner}.post.published", published(post_id=7)) == 1
        assert await app.state.worker.run_due() == 0
        assert heard == []

        async with _sessions(app) as db:
            await db.execute(delete(ModuleState).where(ModuleState.module_id == ear))
            await db.commit()
        assert await app.state.worker.run_due() == 1
    assert len(heard) == 1


async def test_a_module_modules_leaves_out_gets_no_delivery(migrated_url: str) -> None:
    owner, ear = unique_id(), unique_id()
    published = _payload(owner)
    listener, heard = _ear(ear, f"{owner}.post.published")
    async with _site(
        migrated_url,
        _module(owner, payloads=[published]),
        _module(ear, listeners=[listener]),
        modules=owner,
    ) as app:
        assert await _emit(app, f"{owner}.post.published", published(post_id=7)) == 0
        assert await _deliveries(app, listener) == []
    assert heard == []


@pytest.mark.parametrize("kind", ["not an event", "another event"])
async def test_a_delivery_that_isn_t_its_listener_s_event_is_abandoned(
    migrated_url: str, kind: str
) -> None:
    ear = unique_id()
    listener, heard = _ear(ear, "auth.user.deleted")
    body: dict[str, Any] = {"nonsense": 1}
    if kind == "another event":
        body = {
            "id": str(uuid.uuid4()),
            "name": "auth.user.created",
            "v": 1,
            "emitted_at": clock.now().isoformat(),
            "payload": {"user_id": str(uuid.uuid4())},
        }
    async with _site(migrated_url, _module(ear, listeners=[listener])) as app:
        async with _sessions(app) as db:
            await jobs.enqueue(db, listener.name, body)
            await db.commit()
        assert await app.state.worker.run_due() == 1
        [row] = await _deliveries(app, listener)
    assert (row.state, row.last_error) == ("dead", "Abandon")
    assert heard == []


# --- the K3 gate: delivered once, and safe to run twice ---------------------------------

_notes_metadata = MetaData()
_notes = Table(
    "test_event_note",
    _notes_metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("text", String(50), nullable=False),
)


@pytest_asyncio.fixture(loop_scope="session")
async def notes(migrated_url: str) -> AsyncIterator[Database]:
    """A table of a test module's own, holding notes by person, made and
    dropped here; no foreign key, as a module's data on a person has none."""
    database = Database(migrated_url, pool_size=3, max_overflow=3)
    async with database.engine.begin() as connection:
        await connection.run_sync(_notes_metadata.create_all)
    yield database
    async with database.engine.begin() as connection:
        await connection.run_sync(_notes_metadata.drop_all)
    await database.dispose()


async def _unverified_account(database: Database) -> uuid.UUID:
    email = f"Kim.{uuid.uuid4().hex[:10]}@Site.test"
    async with database.sessions() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            created_at=clock.now() - timedelta(days=8),
            email_set_at=clock.now() - timedelta(days=8),
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id="member"))
        await db.commit()
        return user.id


async def _note_texts(database: Database, user_ids: Sequence[uuid.UUID]) -> list[str]:
    async with database.sessions() as db:
        rows = await db.scalars(
            select(_notes.c.text).where(_notes.c.user_id.in_(user_ids)).order_by(_notes.c.text)
        )
        return list(rows)


async def _deliveries_for(
    app: FastAPI, listener: events.Listener, user_id: uuid.UUID
) -> list[JobRow]:
    """The listener's deliveries about one person: the sweep may also remove
    accounts other tests left behind."""
    return [row for row in await _deliveries(app, listener) if str(user_id) in (row.payload or "")]


async def test_an_event_reaches_its_listener_once_and_a_second_run_changes_nothing(
    migrated_url: str, notes: Database
) -> None:
    ear = unique_id()
    removed = await _unverified_account(notes)
    kept = await _unverified_account(notes)
    async with notes.sessions() as db:
        await db.execute(
            insert(_notes),
            [
                {"id": uuid.uuid4(), "user_id": removed, "text": "removed's 1"},
                {"id": uuid.uuid4(), "user_id": removed, "text": "removed's 2"},
                {"id": uuid.uuid4(), "user_id": kept, "text": "kept's"},
            ],
        )
        account = await db.get(User, kept)
        assert account is not None
        account.email_verified_at = clock.now()  # verified: never removed
        await db.commit()

    tries: list[tuple[int, uuid.UUID]] = []

    async def forget_user(ctx: jobs.Context, event: events.Event) -> None:
        gone = event.parse(events.UserDeleted)
        async with ctx.sessions() as db:
            await db.execute(delete(_notes).where(_notes.c.user_id == gone.user_id))
            await db.commit()
        if gone.user_id != removed:
            return
        tries.append((ctx.try_number, event.id))
        if ctx.try_number == 1:
            # Its work committed, then the try failed: as if the worker died
            # before it could mark the delivery done. It runs again.
            raise ConnectionError("gone before the outcome was written")

    listener = events.on("auth.user.deleted", f"{ear}.forget_user")(forget_user)
    async with _site(migrated_url, _module(ear, listeners=[listener])) as app:
        context = jobs.Context(uuid.uuid4(), unverified.REMOVE.name, 1, notes, LogMailer())
        await unverified.REMOVE.run(context, {})
        [delivery] = await _deliveries_for(app, listener, removed)  # one event, one delivery
        assert delivery.state == "queued"

        await app.state.worker.run_due()
        after_first = await _note_texts(notes, [removed, kept])
        clock.advance(60)  # past the first wait
        await app.state.worker.run_due()
        await app.state.worker.run_due()
        [delivery] = await _deliveries_for(app, listener, removed)

    assert after_first == ["kept's"]
    assert await _note_texts(notes, [removed, kept]) == after_first
    assert (delivery.state, delivery.tries) == ("done", 2)
    assert [try_number for try_number, _ in tries] == [1, 2]
    assert tries[0][1] == tries[1][1]


# --- discovery --------------------------------------------------------------------------


def test_a_module_s_events_py_is_found_by_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harness.registry import module_events

    owner = unique_id()
    package = f"discovered_{uuid.uuid4().hex[:8]}"
    (tmp_path / package).mkdir()
    (tmp_path / package / "__init__.py").write_text("")
    (tmp_path / package / "events.py").write_text(
        "from kernel import events, jobs\n"
        "from kernel.events import UserDeleted\n\n"
        f"@events.payload('{owner}.post.published', v=1)\n"
        "class Published(events.Payload):\n"
        "    post_id: int\n\n"
        f"@events.on('auth.user.deleted', '{owner}.forget_user')\n"
        "async def forget_user(ctx: jobs.Context, event: events.Event) -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    payloads, listeners = module_events(f"{package}.events")
    assert [events.declaration(model) for model in payloads] == [(f"{owner}.post.published", 1)]
    assert [(listener.event, listener.name) for listener in listeners] == [
        ("auth.user.deleted", f"{owner}.forget_user")
    ]
    assert module_events(f"{package}.missing") == ((), ())


def test_the_module_template_s_events_py_matches_its_module_json() -> None:
    folder = Path(__file__).resolve().parents[2] / "modules" / "_template"
    listed = json.loads((folder / "module.json").read_text("utf-8"))
    spec = importlib.util.spec_from_file_location(
        f"template_events_{uuid.uuid4().hex[:8]}", folder / "backend" / "my_module" / "events.py"
    )
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    listeners = [value for value in vars(loaded).values() if isinstance(value, events.Listener)]
    assert [(listener.event, listener.name) for listener in listeners] == [
        ("auth.user.deleted", "my-module.forget_user")
    ]
    events.build(
        [
            ("kernel", events.KERNEL_PAYLOADS, (), None),
            (listed["id"], (), listeners, listed["events"]),
        ],
        allowed=[listed["id"]],
    )

"""The content lifecycle hook (decision 0052, hook 1; contract `dev plans/contracts/hooks.md`):
`lifecycle.Publishable`, publish, schedule and unpublish, the one public
WHERE, the publishing job, and the start's checks."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, String, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kernel import clock, jobs, lifecycle
from kernel.db import NAMING, Database
from kernel.email import LogMailer
from kernel.errors import Problem
from kernel.modules import InstalledModule, Manifest

from .conftest import Heard, manifest


class _Base(DeclarativeBase):
    """The tests' own tables, apart from the kernel's metadata, so the
    migrations check never sees them."""

    metadata = MetaData(naming_convention=NAMING)


class Note(lifecycle.Publishable, _Base):
    __tablename__ = "lifecycle_test_note"
    __content_type__ = "notes.note"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(80), default="A note")


class Plain(_Base):
    """Not publishable: no lifecycle columns."""

    __tablename__ = "lifecycle_test_plain"
    __content_type__ = "notes.plain"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


@pytest_asyncio.fixture(loop_scope="session")
async def notes(database: Database) -> AsyncIterator[Database]:
    async with database.engine.begin() as connection:
        await connection.run_sync(_Base.metadata.create_all)
    try:
        yield database
    finally:
        async with database.engine.begin() as connection:
            await connection.run_sync(_Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _installed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The test's types, and the app's back after it: the contract suite's
    app, built once, reads the same module global."""
    monkeypatch.setattr(lifecycle, "_publishable", {"notes.note": Note})
    clock.reset()
    try:
        yield
    finally:
        clock.reset()


async def _visible(db: AsyncSession) -> list[uuid.UUID]:
    return list((await db.scalars(select(Note.id).where(lifecycle.visible(Note)))).all())


async def _new(db: AsyncSession) -> Note:
    note = Note()
    db.add(note)
    await db.flush()
    return note


# --- the columns ----------------------------------------------------------------------


@pytest.mark.db
async def test_a_new_row_is_a_draft_nobody_sees(notes: Database) -> None:
    async with notes.sessions() as db:
        note = await _new(db)
        assert (note.status, note.publish_at, note.published_at) == ("draft", None, None)
        assert note.id not in await _visible(db)


@pytest.mark.db
async def test_the_table_refuses_a_state_the_hook_never_writes(notes: Database) -> None:
    """The CHECK holds the rules the functions keep: a known status, a
    scheduled row's time, a published row's date."""
    async with notes.sessions() as db:
        for broken in (
            "status = 'live'",
            "status = 'scheduled', publish_at = NULL",
            "status = 'published', published_at = NULL",
        ):
            note = await _new(db)
            await db.commit()
            with pytest.raises(IntegrityError):
                await db.execute(
                    text(f"UPDATE lifecycle_test_note SET {broken} WHERE id = :id"),  # noqa: S608
                    {"id": note.id},
                )
            await db.rollback()


def test_the_table_carries_the_check_and_the_due_index() -> None:
    table = Note.__table__
    names = {constraint.name for constraint in table.constraints}
    assert "ck_lifecycle_test_note_lifecycle" in names
    (due,) = [index for index in table.indexes if index.name == "ix_lifecycle_test_note_due"]
    assert [column.name for column in due.columns] == ["publish_at"]


def test_a_migration_gets_the_same_columns_and_args() -> None:
    """What a module's first migration writes (`*lifecycle.columns()`,
    `*lifecycle.table_args(table)`) is what the model declares."""
    assert [column.name for column in lifecycle.columns()] == [
        "status",
        "publish_at",
        "published_at",
    ]
    args = lifecycle.table_args("blog_post")
    assert {type(arg).__name__ for arg in args} == {"CheckConstraint", "Index"}


# --- publish, schedule, unpublish -----------------------------------------------------


@pytest.mark.db
async def test_publish_shows_the_row_and_emits_once(notes: Database, heard: Heard) -> None:
    async with notes.sessions() as db:
        note = await _new(db)
        await lifecycle.publish(db, note)
        await lifecycle.publish(db, note)  # already published: nothing more
        await db.commit()
        assert note.status == "published"
        assert note.published_at is not None
        assert note.id in await _visible(db)
    assert await heard.drain() == [
        ("kernel.content.published", {"type": "notes.note", "id": str(note.id)})
    ]


@pytest.mark.db
async def test_republishing_keeps_the_first_date(notes: Database) -> None:
    async with notes.sessions() as db:
        note = await _new(db)
        await lifecycle.publish(db, note)
        first = note.published_at
        await lifecycle.unpublish(db, note)
        clock.advance(3600)
        await lifecycle.publish(db, note)
        assert note.published_at == first


@pytest.mark.db
async def test_unpublish_hides_it_and_emits_only_for_a_published_row(
    notes: Database, heard: Heard
) -> None:
    async with notes.sessions() as db:
        shown, waiting = await _new(db), await _new(db)
        await lifecycle.publish(db, shown)
        await lifecycle.schedule(db, waiting, clock.now() + timedelta(hours=1))
        await db.commit()
        await heard.drain()
        heard.seen.clear()
        await lifecycle.unpublish(db, shown)
        await lifecycle.unpublish(db, waiting)
        await lifecycle.unpublish(db, waiting)  # a draft already: nothing
        await db.commit()
        assert (shown.status, waiting.status, waiting.publish_at) == ("draft", "draft", None)
        assert await _visible(db) == []
    assert await heard.drain() == [
        ("kernel.content.unpublished", {"type": "notes.note", "id": str(shown.id)})
    ]


@pytest.mark.db
async def test_schedule_waits_and_refuses_a_time_gone_or_a_published_row(
    notes: Database, heard: Heard
) -> None:
    async with notes.sessions() as db:
        note = await _new(db)
        with pytest.raises(Problem) as past:
            await lifecycle.schedule(db, note, clock.now())
        assert (past.value.code, past.value.status) == ("kernel.publish_at_past", 422)
        at = clock.now() + timedelta(minutes=5)
        await lifecycle.schedule(db, note, at)
        await db.commit()
        assert (note.status, note.publish_at) == ("scheduled", at)
        assert await _visible(db) == []
        await lifecycle.publish(db, note)
        await db.commit()
        with pytest.raises(Problem) as published:
            await lifecycle.schedule(db, note, clock.now() + timedelta(hours=1))
        assert (published.value.code, published.value.status) == ("kernel.content_published", 409)
    assert [name for name, _ in await heard.drain()] == ["kernel.content.published"]


@pytest.mark.db
async def test_a_time_without_a_zone_is_refused(notes: Database) -> None:
    async with notes.sessions() as db:
        note = await _new(db)
        with pytest.raises(ValueError, match="needs its zone"):
            await lifecycle.schedule(
                db, note, (clock.now() + timedelta(hours=1)).replace(tzinfo=None)
            )


@pytest.mark.db
async def test_a_row_that_isnt_publishable_is_refused(notes: Database) -> None:
    async with notes.sessions() as db:
        with pytest.raises(TypeError):
            await lifecycle.publish(db, Plain())  # type: ignore[arg-type]


# --- the publishing job ---------------------------------------------------------------


def _context(database: Database) -> jobs.Context:
    return jobs.Context(uuid.uuid4(), lifecycle.PUBLISH_DUE.name, 1, database, LogMailer())


@pytest.mark.db
async def test_the_job_publishes_what_is_due_at_its_time(notes: Database, heard: Heard) -> None:
    async with notes.sessions() as db:
        due, later = await _new(db), await _new(db)
        at = clock.now() + timedelta(minutes=2)
        await lifecycle.schedule(db, due, at)
        await lifecycle.schedule(db, later, clock.now() + timedelta(days=1))
        await db.commit()
    clock.advance(180)
    await lifecycle.PUBLISH_DUE.run(_context(notes), {})
    await lifecycle.PUBLISH_DUE.run(_context(notes), {})  # nothing new is due
    async with notes.sessions() as db:
        assert await _visible(db) == [due.id]
        found = await db.get(Note, due.id)
        assert found is not None
        assert found.published_at == at
    assert await heard.drain() == [
        ("kernel.content.published", {"type": "notes.note", "id": str(due.id)})
    ]


def test_the_job_is_the_kernels_and_runs_every_minute() -> None:
    from kernel.app import KERNEL_JOBS

    assert lifecycle.PUBLISH_DUE in KERNEL_JOBS
    assert lifecycle.PUBLISH_DUE.name == "kernel.publish_due"
    assert lifecycle.PUBLISH_DUE.schedule is not None
    assert lifecycle.PUBLISH_DUE.schedule.line == "* * * * *"


# --- the start's checks (lifecycle.build) ----------------------------------------------


def _typed(module_id: str, *types: dict[str, object]) -> Manifest:
    return Manifest.from_dict({**manifest(module_id).raw, "content_types": list(types)})


def test_build_maps_each_type_to_its_model() -> None:
    notes = InstalledModule(
        _typed("notes", {"key": "notes.note", "label": "Note", "lifecycle": True}),
        publishable=(Note,),
    )
    other = InstalledModule(manifest("other"))
    assert lifecycle.build([notes, other]) == {"notes.note": Note}


@pytest.mark.parametrize(
    ("types", "models", "words"),
    [
        ([], (Note,), "content_types doesn't list notes.note with lifecycle"),
        ([{"key": "notes.note", "label": "Note"}], (Note,), "lifecycle"),
        ([{"key": "notes.note", "label": "Note", "lifecycle": True}], (), "PUBLISHABLE"),
        ([{"key": "notes.note", "label": "Note", "lifecycle": True}], (Plain,), "Publishable"),
    ],
)
def test_build_refuses_a_manifest_and_models_that_disagree(
    types: list[dict[str, object]], models: tuple[type, ...], words: str
) -> None:
    module = InstalledModule(_typed("notes", *types), publishable=models)
    with pytest.raises(ValueError, match=words):
        lifecycle.build([module])


def test_build_refuses_a_type_outside_the_modules_id() -> None:
    module = InstalledModule(
        _typed("other", {"key": "notes.note", "label": "Note", "lifecycle": True}),
        publishable=(Note,),
    )
    with pytest.raises(ValueError, match="other may only"):
        lifecycle.build([module])


class Bare(lifecycle.Publishable, _Base):
    """Its own __table_args__ replace the mixin's: no CHECK, no due index."""

    __tablename__ = "lifecycle_test_bare"
    __content_type__ = "notes.bare"
    __table_args__ = ()

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


def test_build_refuses_a_table_without_the_check_or_the_index() -> None:
    module = InstalledModule(
        _typed("notes", {"key": "notes.bare", "label": "Bare", "lifecycle": True}),
        publishable=(Bare,),
    )
    with pytest.raises(ValueError, match="lacks the lifecycle CHECK"):
        lifecycle.build([module])


def test_build_refuses_a_type_listed_twice() -> None:
    module = InstalledModule(
        _typed("notes", {"key": "notes.note", "label": "Note", "lifecycle": True}),
        publishable=(Note, Note),
    )
    with pytest.raises(ValueError, match="publishable twice"):
        lifecycle.build([module])


@pytest.mark.db
async def test_a_row_published_before_its_first_flush_gets_its_id(
    notes: Database, heard: Heard
) -> None:
    async with notes.sessions() as db:
        note = Note()
        db.add(note)
        await lifecycle.publish(db, note)
        await db.commit()
    assert await heard.drain() == [
        ("kernel.content.published", {"type": "notes.note", "id": str(note.id)})
    ]


# --- a row another transaction changed (Codex on #97) ----------------------------------


async def _scheduled(database: Database) -> uuid.UUID:
    async with database.sessions() as db:
        note = await _new(db)
        await lifecycle.schedule(db, note, clock.now() + timedelta(minutes=1))
        await db.commit()
        return note.id


@pytest.mark.db
async def test_a_stale_row_is_judged_as_the_job_left_it(notes: Database, heard: Heard) -> None:
    """A request loaded the row while it was scheduled; the job published it
    since. Unpublishing it is then an unpublish, with its event, and
    publishing it again is nothing."""
    first, second = await _scheduled(notes), await _scheduled(notes)
    async with notes.sessions() as db:
        stale_unpublish = await db.get(Note, first)
        stale_publish = await db.get(Note, second)
        assert stale_unpublish is not None
        assert stale_publish is not None
        await db.commit()  # the rows stay loaded, as a request's would
        clock.advance(120)
        await lifecycle.PUBLISH_DUE.run(_context(notes), {})
        await lifecycle.unpublish(db, stale_unpublish)
        await lifecycle.publish(db, stale_publish)
        await db.commit()
        assert (stale_unpublish.status, stale_publish.status) == ("draft", "published")
    seen = await heard.drain()
    assert sorted(seen, key=lambda event: (event[0], event[1]["id"])) == sorted(
        [
            ("kernel.content.published", {"type": "notes.note", "id": str(first)}),
            ("kernel.content.published", {"type": "notes.note", "id": str(second)}),
            ("kernel.content.unpublished", {"type": "notes.note", "id": str(first)}),
        ],
        key=lambda event: (event[0], event[1]["id"]),
    )


@pytest.mark.db
async def test_a_change_waits_for_the_job_holding_the_row(notes: Database, heard: Heard) -> None:
    """The job holds the row while it publishes it. An unpublish that only
    re-read the row would read it as scheduled and send no event; it must
    wait for the job's commit and judge what the job committed."""
    note_id = await _scheduled(notes)
    async with notes.sessions() as request, notes.sessions() as job:
        held = await request.get(Note, note_id)
        assert held is not None
        await request.commit()
        await job.execute(
            update(Note)
            .where(Note.id == note_id)
            .values(status="published", published_at=clock.now())
        )  # holds the row's lock until it commits

        async def unpublish() -> None:
            await lifecycle.unpublish(request, held)
            await request.commit()

        waiting = asyncio.create_task(unpublish())
        await asyncio.sleep(0.5)
        await job.commit()
        await asyncio.wait_for(waiting, timeout=10)
    assert held.status == "draft"
    assert await heard.drain() == [
        ("kernel.content.unpublished", {"type": "notes.note", "id": str(note_id)})
    ]

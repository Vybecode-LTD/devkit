"""The search index hook (decision 0052, hook 3; contract `dev plans/contracts/hooks.md`):
the sources modules declare, the start's checks, `search.index` and `search.remove`,
the kernel hearing `kernel.content.*`, the reindex job, and `search.find`."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, String, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from harness.probe import MODULES as PROBES
from kernel import clock, events, jobs, lifecycle, search
from kernel.db import NAMING, Database
from kernel.email import LogMailer
from kernel.errors import Problem
from kernel.models import SearchDocument
from kernel.modules import InstalledModule, Manifest


class _Base(DeclarativeBase):
    """The tests' own tables, apart from the kernel's metadata."""

    metadata = MetaData(naming_convention=NAMING)


class Note(lifecycle.Publishable, _Base):
    __tablename__ = "search_test_note"
    __content_type__ = "notes.note"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), default="A note")
    body: Mapped[str] = mapped_column(Text, default="")


class NoteSource(search.Source):
    """The notes module's source: a published note's words, at /notes/<id>."""

    content_type = "notes.note"

    @staticmethod
    def _of(note: Note) -> search.Document:
        return search.Document("notes.note", note.id, note.title, note.body, f"/notes/{note.id}")

    async def document(self, db: AsyncSession, content_id: uuid.UUID) -> search.Document | None:
        note = await db.get(Note, content_id)
        return None if note is None else self._of(note)  # the kernel judges it public

    async def documents(self, db: AsyncSession) -> AsyncIterator[search.Document]:
        for note in await db.scalars(select(Note).order_by(Note.id)):
            yield self._of(note)


class PageSource(search.Source):
    """A module without lifecycle: it indexes its pages itself."""

    content_type = "pages.page"
    shown: ClassVar[dict[uuid.UUID, search.Document]] = {}

    async def document(self, db: AsyncSession, content_id: uuid.UUID) -> search.Document | None:
        return self.shown.get(content_id)

    async def documents(self, db: AsyncSession) -> AsyncIterator[search.Document]:
        for found in list(self.shown.values()):
            yield found


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
    """The test's sources and types, and the app's back after it: the
    contract suite's app, built once, reads the same module globals."""
    PageSource.shown = {}
    monkeypatch.setattr(
        search, "_sources", {"notes.note": NoteSource(), "pages.page": PageSource()}
    )
    monkeypatch.setattr(search, "_language", "english")
    monkeypatch.setattr(lifecycle, "_publishable", {"notes.note": Note})
    clock.reset()
    try:
        yield
    finally:
        clock.reset()


def _word() -> str:
    """A word no other test's documents hold."""
    return f"w{uuid.uuid4().hex[:12]}"


def _page(title: str, body: str = "", *, path: str | None = None) -> search.Document:
    page_id = uuid.uuid4()
    return search.Document("pages.page", page_id, title, body, path or f"/pages/{page_id}")


async def _find(db: AsyncSession, q: str, **more: Any) -> dict[str, Any]:
    options: dict[str, Any] = {"types": ["notes.note", "pages.page"], "cursor": None, "limit": 20}
    options.update(more)
    return await search.find(db, q, **options)


async def _ids(db: AsyncSession, q: str, **more: Any) -> list[str]:
    return [item["id"] for item in (await _find(db, q, **more))["items"]]


def _module(module_id: str, **more: Any) -> InstalledModule:
    fields = {key: value for key, value in more.items() if key == "searchable"}
    raw = {key: value for key, value in more.items() if key != "searchable"}
    return InstalledModule(
        Manifest.from_dict(
            {
                "id": module_id,
                "name": module_id.title(),
                "version": "0.1.0",
                "requires": {"modules": {}},
                **raw,
            }
        ),
        **fields,
    )


def _searched(module_id: str, entity: str) -> list[dict[str, Any]]:
    return [{"key": f"{module_id}.{entity}", "label": entity.title(), "search": True}]


class _Of(search.Source):
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    async def document(self, db: AsyncSession, content_id: uuid.UUID) -> search.Document | None:
        return None

    async def documents(self, db: AsyncSession) -> AsyncIterator[search.Document]:
        for _ in ():
            yield _


# --- the start's checks ------------------------------------------------------------------


def test_only_the_module_that_takes_part_shows() -> None:
    found = search.build(PROBES)
    assert sorted(found) == ["probe.note"]
    assert isinstance(found["probe.note"], search.Source)


def test_build_maps_each_type_to_its_source() -> None:
    source = _Of("blog.post")
    found = search.build(
        [_module("blog", content_types=_searched("blog", "post"), searchable=(source,))]
    )
    assert found == {"blog.post": source}


@pytest.mark.parametrize(
    ("content_types", "sources", "problem"),
    [
        ([], (_Of("blog.post"),), "blog's search.py answers for blog.post, but its module.json"),
        (_searched("blog", "post"), (), "blog's content_types lists blog.post with search"),
    ],
)
def test_build_refuses_a_manifest_and_sources_that_disagree(
    content_types: list[dict[str, Any]], sources: tuple[search.Source, ...], problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        search.build([_module("blog", content_types=content_types, searchable=sources)])


def test_build_refuses_a_type_outside_the_modules_id() -> None:
    with pytest.raises(ValueError, match=r"blog may only search blog\.\* content types"):
        search.build([_module("blog", content_types=[], searchable=(_Of("shop.product"),))])


def test_build_refuses_what_isnt_a_source_and_a_type_listed_twice() -> None:
    with pytest.raises(ValueError, match=r"isn't a search\.Source"):
        search.build([_module("blog", searchable=("blog.post",))])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"blog\.post is searched twice"):
        search.build(
            [
                _module(
                    "blog",
                    content_types=_searched("blog", "post"),
                    searchable=(_Of("blog.post"), _Of("blog.post")),
                )
            ]
        )


@pytest.mark.parametrize("name", ["english", "simple", "french", "spanish"])
def test_the_search_language_is_a_postgres_text_search_configuration(name: str) -> None:
    from kernel.config import KernelConfig

    assert KernelConfig(search_language=name).search_language == name


@pytest.mark.parametrize("name", ["klingon", "English", "english; drop table", ""])
def test_the_config_refuses_a_language_postgres_lacks(name: str) -> None:
    from pydantic import ValidationError

    from kernel.config import KernelConfig

    with pytest.raises(ValidationError, match="search_language"):
        KernelConfig(search_language=name)


# --- index, remove and find --------------------------------------------------------------


@pytest.mark.db
async def test_an_indexed_page_is_found_and_a_removed_one_isnt(notes: Database) -> None:
    word = _word()
    page = _page(f"Mixing {word}", f"How we record and mix {word} in a small room.")
    async with notes.sessions() as db:
        await search.index(db, page)
        await db.commit()
        found = await _find(db, word)
    (item,) = found["items"]
    assert item == {
        "type": "pages.page",
        "id": str(page.id),
        "title": page.title,
        "snippet": item["snippet"],
        "path": page.path,
    }
    assert word in item["snippet"]
    assert "<" not in item["snippet"]
    assert found["next_cursor"] is None
    async with notes.sessions() as db:
        await search.remove(db, "pages.page", page.id)
        await db.commit()
        assert await _ids(db, word) == []


@pytest.mark.db
async def test_indexing_again_replaces_the_document(notes: Database) -> None:
    old, new = _word(), _word()
    page = _page(f"About {old}")
    async with notes.sessions() as db:
        await search.index(db, page)
        await search.index(db, search.Document(page.type, page.id, f"About {new}", "", page.path))
        await db.commit()
        assert await _ids(db, old) == []
        assert await _ids(db, new) == [str(page.id)]
        stored = await db.scalar(
            select(func.count())
            .select_from(SearchDocument)
            .where(SearchDocument.content_id == page.id)
        )
    assert stored == 1


@pytest.mark.db
async def test_a_word_in_the_title_ranks_above_one_in_the_body(notes: Database) -> None:
    word = _word()
    in_body = _page("Something else", f"A paragraph that mentions {word} once.")
    in_title = _page(f"All about {word}", "A paragraph about other things.")
    async with notes.sessions() as db:
        await search.index(db, in_body)
        await search.index(db, in_title)
        await db.commit()
        assert await _ids(db, word) == [str(in_title.id), str(in_body.id)]


@pytest.mark.db
async def test_words_are_stemmed_in_the_site_language(notes: Database) -> None:
    word = _word()
    page = _page(f"Recording {word}", "We mixed the drums.")
    async with notes.sessions() as db:
        await search.index(db, page)
        await db.commit()
        assert await _ids(db, f"{word} mixing") == [str(page.id)]
        assert await _ids(db, f'"{word} drums" -mixed') == []  # websearch syntax
        assert await _ids(db, "the") == []  # nothing but a stop word finds nothing


@pytest.mark.db
async def test_find_keeps_to_the_types_asked(notes: Database) -> None:
    word = _word()
    page = _page(f"Page {word}")
    async with notes.sessions() as db:
        await search.index(db, page)
        await db.commit()
        assert await _ids(db, word, types=["notes.note"]) == []
        assert await _ids(db, word, types=[]) == []
        assert await _ids(db, word, types=["pages.page"]) == [str(page.id)]


@pytest.mark.db
async def test_find_pages_by_rank_with_a_cursor(notes: Database) -> None:
    word = _word()
    pages = [_page(f"{word} " * count, "") for count in (1, 2, 3, 4)]  # more than a page and one
    async with notes.sessions() as db:
        for page in pages:
            await search.index(db, page)
        await db.commit()
        first = await _find(db, word, limit=2)
        assert first["next_cursor"] is not None
        second = await _find(db, word, limit=2, cursor=first["next_cursor"])
    seen = [item["id"] for item in (*first["items"], *second["items"])]
    assert seen == [str(page.id) for page in reversed(pages)]
    assert second["next_cursor"] is None


@pytest.mark.db
async def test_find_pages_through_documents_ranked_the_same(notes: Database) -> None:
    word = _word()
    pages = [_page(f"Same {word}") for _ in range(5)]
    async with notes.sessions() as db:
        for page in pages:
            await search.index(db, page)
        await db.commit()
        seen: list[str] = []
        cursor = None
        for _ in range(5):
            found = await _find(db, word, limit=2, cursor=cursor)
            seen.extend(item["id"] for item in found["items"])
            cursor = found["next_cursor"]
            if cursor is None:
                break
    assert sorted(seen) == sorted(str(page.id) for page in pages)
    assert len(seen) == len(set(seen))


@pytest.mark.db
@pytest.mark.parametrize(
    ("q", "cursor", "field"),
    [
        ("   ", None, "q"),
        ("a\x00b", None, "q"),
        ("x" * (search.MAX_QUERY + 1), None, "q"),
        ("word", "nonsense", "cursor"),
        ("word", "nan:pages.page:" + str(uuid.uuid4()), "cursor"),
        ("word", "0.5:Pages:" + str(uuid.uuid4()), "cursor"),
        ("word", "0.5:pages.page:not-an-id", "cursor"),
    ],
)
async def test_find_refuses_a_bad_query_or_cursor(
    notes: Database, q: str, cursor: str | None, field: str
) -> None:
    async with notes.sessions() as db:
        with pytest.raises(Problem) as refused:
            await _find(db, q, cursor=cursor)
    assert (refused.value.code, refused.value.status) == ("kernel.invalid_request", 422)
    assert field in (refused.value.errors or {})


@pytest.mark.db
async def test_a_document_is_trimmed_and_cleaned_before_it_is_stored(notes: Database) -> None:
    word = _word()
    long = _page(f"{word}\x00 title " + "t" * search.MAX_TITLE, "b\x00" * search.MAX_BODY)
    async with notes.sessions() as db:
        await search.index(db, long)
        await db.commit()
        stored = await db.get(SearchDocument, ("pages.page", long.id))
    assert stored is not None
    assert len(stored.title) == search.MAX_TITLE
    assert "\x00" not in stored.title
    assert len(stored.body) <= search.MAX_BODY
    assert "\x00" not in stored.body
    assert stored.language == "english"


@pytest.mark.db
@pytest.mark.parametrize(
    "path", ["notes/1", "//elsewhere.test/x", "https://elsewhere.test/", "/" + "p" * 500]
)
async def test_index_refuses_a_path_off_the_site(notes: Database, path: str) -> None:
    async with notes.sessions() as db:
        with pytest.raises(ValueError, match="path"):
            await search.index(db, _page("A page", path=path))


@pytest.mark.db
async def test_index_and_remove_refuse_a_type_nobody_searches(notes: Database) -> None:
    async with notes.sessions() as db:
        with pytest.raises(ValueError, match=r"shop\.product isn't searched"):
            await search.index(db, search.Document("shop.product", uuid.uuid4(), "A", "", "/a"))
        with pytest.raises(ValueError, match=r"shop\.product isn't searched"):
            await search.remove(db, "shop.product", uuid.uuid4())


# --- public documents only: the kernel judges a lifecycle type's rows itself ------------


async def _note(db: AsyncSession, words: str) -> Note:
    note = Note(title=words, body=f"The body of {words}.")
    db.add(note)
    await db.flush()
    return note


@pytest.mark.db
async def test_indexing_a_draft_keeps_it_out(notes: Database) -> None:
    word = _word()
    async with notes.sessions() as db:
        note = await _note(db, word)
        await search.index(db, NoteSource._of(note))
        await db.commit()
        assert await _ids(db, word) == []
        await lifecycle.publish(db, note)
        await search.index(db, NoteSource._of(note))
        await db.commit()
        assert await _ids(db, word) == [str(note.id)]
        await lifecycle.unpublish(db, note)
        await search.index(db, NoteSource._of(note))  # an edit of a note gone back to a draft
        await db.commit()
        assert await _ids(db, word) == []


def _context(database: Database, name: str) -> jobs.Context:
    return jobs.Context(uuid.uuid4(), name, 1, database, LogMailer())


async def _hear(
    database: Database, listener: events.Listener, content_type: str, ident: uuid.UUID
) -> None:
    """Delivers the event to the kernel's listener, as its job would."""
    body = {
        "id": str(uuid.uuid4()),
        "name": listener.event,
        "v": 1,
        "emitted_at": datetime.now(UTC).isoformat(),
        "payload": {"type": content_type, "id": str(ident)},
    }
    await listener.job.run(_context(database, listener.name), body)


def test_the_kernel_hears_the_content_events_with_jobs_of_its_own() -> None:
    from kernel.app import KERNEL_JOBS, KERNEL_LISTENERS

    assert {(listener.event, listener.name) for listener in KERNEL_LISTENERS} == {
        ("kernel.content.published", "kernel.search_published"),
        ("kernel.content.unpublished", "kernel.search_unpublished"),
    }
    assert search.REINDEX in KERNEL_JOBS
    assert search.REINDEX.name == "kernel.search_reindex"
    assert search.REINDEX.schedule is None  # on demand


@pytest.mark.db
async def test_a_published_note_is_indexed_and_an_unpublished_one_removed(
    notes: Database,
) -> None:
    word = _word()
    async with notes.sessions() as db:
        note = await _note(db, word)
        await lifecycle.publish(db, note)
        await db.commit()
    await _hear(notes, search.ON_PUBLISHED, "notes.note", note.id)
    async with notes.sessions() as db:
        assert await _ids(db, word) == [str(note.id)]
        await lifecycle.unpublish(db, await db.get_one(Note, note.id))
        await db.commit()
    await _hear(notes, search.ON_UNPUBLISHED, "notes.note", note.id)
    async with notes.sessions() as db:
        assert await _ids(db, word) == []


@pytest.mark.db
async def test_each_event_indexes_the_row_as_it_is_now_whatever_their_order(
    notes: Database,
) -> None:
    """Deliveries can run out of order: published, unpublished and published
    again leave the note found, whichever is delivered last."""
    word = _word()
    async with notes.sessions() as db:
        note = await _note(db, word)
        await lifecycle.publish(db, note)
        await db.commit()
    await _hear(notes, search.ON_UNPUBLISHED, "notes.note", note.id)  # the first publish's twin
    async with notes.sessions() as db:
        assert await _ids(db, word) == [str(note.id)]
        await lifecycle.unpublish(db, await db.get_one(Note, note.id))
        await db.commit()
    await _hear(notes, search.ON_PUBLISHED, "notes.note", note.id)  # late, the row is a draft
    async with notes.sessions() as db:
        assert await _ids(db, word) == []


@pytest.mark.db
async def test_an_event_for_a_type_nobody_searches_is_left(notes: Database) -> None:
    await _hear(notes, search.ON_PUBLISHED, "shop.product", uuid.uuid4())  # no error


@pytest.mark.db
async def test_a_source_answering_none_removes_the_document(notes: Database) -> None:
    word = _word()
    page = _page(f"Page {word}")
    async with notes.sessions() as db:
        await search.index(db, page)
        await db.commit()
    await _hear(notes, search.ON_PUBLISHED, "pages.page", page.id)  # PageSource answers None
    async with notes.sessions() as db:
        assert await _ids(db, word) == []


# --- the reindex job ---------------------------------------------------------------------


@pytest.mark.db
async def test_the_reindex_rebuilds_every_type_from_its_source(notes: Database) -> None:
    shown, draft, stale, gone = _word(), _word(), _word(), _word()
    async with notes.sessions() as db:
        published = await _note(db, shown)
        await lifecycle.publish(db, published)
        await _note(db, draft)
        page = _page(f"Kept {shown}")
        PageSource.shown[page.id] = page
        await search.index(db, _page(f"Stale {stale}"))  # PageSource no longer answers it
        orphan = search.Document("shop.product", uuid.uuid4(), f"Orphan {gone}", "", "/shop/1")
        await search._write(db, orphan)  # a type whose module has gone
        await db.commit()
    await search.REINDEX.run(_context(notes, search.REINDEX.name), {})
    async with notes.sessions() as db:
        assert sorted(await _ids(db, shown)) == sorted([str(published.id), str(page.id)])
        assert await _ids(db, draft) == []
        assert await _ids(db, stale) == []
        left = await db.scalar(
            select(func.count())
            .select_from(SearchDocument)
            .where(SearchDocument.content_type == "shop.product")
        )
    assert left == 0


# --- one change of a type's documents at a time ----------------------------------------


@pytest.mark.db
async def test_an_index_waits_for_a_reindex_of_its_type(notes: Database) -> None:
    word = _word()
    page = _page(f"Waiting {word}")
    async with notes.sessions() as holding:
        await holding.execute(
            text("SELECT pg_advisory_xact_lock(:kind, :key)"),
            {"kind": search.TYPE_LOCK, "key": search.lock_key("pages.page")},
        )

        async def index() -> None:
            async with notes.sessions() as db:
                await search.index(db, page)
                await db.commit()

        waiting = asyncio.create_task(index())
        await asyncio.sleep(0.5)
        assert not waiting.done(), "index() didn't wait for the type's lock"
        await holding.commit()
    await asyncio.wait_for(waiting, 10)
    async with notes.sessions() as db:
        assert await _ids(db, word) == [str(page.id)]


# --- what a module gets wrong, and the snippet's reach -------------------------------


@pytest.mark.db
async def test_index_refuses_a_document_without_a_title(notes: Database) -> None:
    async with notes.sessions() as db:
        with pytest.raises(ValueError, match="needs a title"):
            await search.index(db, _page(" \t "))


@pytest.mark.db
async def test_a_source_answering_for_another_thing_is_refused(
    notes: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _page("Somewhere else")
    PageSource.shown[uuid.uuid4()] = page  # the source answers this page for another id
    asked = next(ident for ident in PageSource.shown if ident != page.id)
    with pytest.raises(ValueError, match="source answered"):
        await _hear(notes, search.ON_PUBLISHED, "pages.page", asked)


@pytest.mark.db
async def test_the_reindex_refuses_a_document_of_another_type(
    notes: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    stray = search.Document("notes.note", uuid.uuid4(), "Stray", "", "/notes/stray")
    PageSource.shown[stray.id] = stray
    with pytest.raises(ValueError, match=r"gave a document of notes[.]note"):
        await search.REINDEX.run(_context(notes, search.REINDEX.name), {})


@pytest.mark.db
async def test_the_reindex_writes_in_batches(
    notes: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search, "BATCH", 1)  # a flush for each, and an empty one last
    word = _word()
    pages = [_page(f"Batched {word}") for _ in range(3)]
    PageSource.shown.update((page.id, page) for page in pages)
    await search.REINDEX.run(_context(notes, search.REINDEX.name), {})
    async with notes.sessions() as db:
        assert sorted(await _ids(db, word)) == sorted(str(page.id) for page in pages)


@pytest.mark.db
async def test_a_match_far_into_a_long_body_is_found_with_its_opening_as_snippet(
    notes: Database,
) -> None:
    word = _word()
    opening = "An opening paragraph about other things entirely."
    body = opening + " filler" * (search.SNIPPET_FROM // 7) + f" {word}"
    page = _page("A long page", body)
    async with notes.sessions() as db:
        await search.index(db, page)
        await db.commit()
        (item,) = (await _find(db, word))["items"]
    assert item["id"] == str(page.id)
    assert item["snippet"].startswith("An opening paragraph")
    assert word not in item["snippet"]

"""Search index: what site search finds (decision 0052, hook 3;
`dev plans/contracts/hooks.md`; SPEC.md sections 5, 6, 7 and 10).

A module that takes part lists each kind of content site search finds in
module.json, `content_types[].search: true`, and gives each a source in its
`search.py`:

    class Posts(search.Source):
        content_type = "blog.post"

        async def document(self, db, content_id):
            post = await db.get(Post, content_id)
            return None if post is None else search.Document(
                "blog.post", post.id, post.title, post.text, f"/blog/{post.slug}"
            )

        async def documents(self, db):
            for post in await db.scalars(select(Post).where(lifecycle.visible(Post))):
                yield search.Document(...)

    SEARCH = (Posts(),)

The start refuses either one without the other. A module that doesn't take
part declares neither and loses nothing.

- **Content with lifecycle is the kernel's to index.** It hears
  `kernel.content.published` and `kernel.content.unpublished` (its jobs
  `kernel.search_published` and `kernel.search_unpublished`) and asks the
  source for the thing as it is now: there and published, it's indexed;
  otherwise it's removed. Either event does the same, so deliveries in any
  order leave the index as the content is.
- **Content without lifecycle, and an edit of what's published, is the
  module's:** `index(db, doc)` and `remove(db, type, id)`, in the caller's
  transaction. `index` keeps out a lifecycle type's row that isn't
  published, so search holds public documents only.
- **The job `kernel.search_reindex`**, run on demand
  (`jobs.enqueue(db, "kernel.search_reindex", {})`), rebuilds each type from
  its source's `documents()` and drops the rows of types no module searches
  now: after SEARCH_LANGUAGE changes, or once a module is removed.
- **`find`** answers `GET /api/kernel/search`: the types of the modules that
  are on, ranked by `websearch_to_tsquery` in SEARCH_LANGUAGE, the title
  weighted above the body, each with a plain-text snippet.

**One change of a type's documents at a time.** A change of one document
holds its type's advisory lock shared and the document's alone, until its
transaction ends; a reindex holds its type's alone. So two changes of one
document take turns, and a document changed during a reindex is changed
after it, as it is then.
"""

from __future__ import annotations

import math
import re
import uuid
import zlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, String, cast, delete, func, literal, select, text, tuple_
from sqlalchemy.dialects.postgresql import REGCONFIG, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, events, jobs, lifecycle
from kernel.errors import Problem
from kernel.models import SearchDocument as _Row

if TYPE_CHECKING:
    from kernel.modules import InstalledModule

#: A content type, `<id>.<entity>`, as module.json's `content_types` names it.
CONTENT_TYPE = re.compile(r"[a-z][a-z0-9-]*\.[a-z][a-z0-9_]*")
MAX_TITLE = 300
#: The characters of a body that are indexed: the rest is cut.
MAX_BODY = 100_000
MAX_PATH = 500
#: The characters of a search.
MAX_QUERY = 200
#: How often one address may search.
PER_MINUTE = "30/1m"
#: The documents a reindex writes at once.
BATCH = 500
#: The first keys of the advisory locks: (TYPE_LOCK, the type), shared by a
#: change of one document and held alone by a reindex; (ITEM_LOCK, the type
#: and the id), held alone by a change of that document.
TYPE_LOCK = 84712034
ITEM_LOCK = 84712035
#: ts_headline's options: plain text, no marks, two fragments at most.
SNIPPET = (
    'StartSel="", StopSel="", MaxWords=30, MinWords=12, MaxFragments=2, FragmentDelimiter=" … "'
)
#: The characters of a body a snippet is drawn from: ts_headline reads its
#: text again for each hit, about 17 ms for 100,000 characters and 2 ms for
#: these. A match further in gets the body's opening words.
SNIPPET_FROM = 20_000


@dataclass(frozen=True)
class Document:
    """One public thing as site search finds it: its words, and `path`, where
    the site shows it (such as /blog/jazz). The body is plain text."""

    type: str
    id: uuid.UUID
    title: str
    body: str
    path: str


class Source(ABC):
    """A module's documents of one content type, `content_type`."""

    content_type: str

    @abstractmethod
    async def document(self, db: AsyncSession, content_id: uuid.UUID) -> Document | None:
        """The thing as search should show it now, or None when it's gone or
        not for the public. The kernel keeps out a lifecycle type's row that
        isn't published either way."""

    @abstractmethod
    def documents(self, db: AsyncSession) -> AsyncIterator[Document]:
        """Every public thing of the type, for a reindex: an async generator
        (`async def documents(self, db): ... yield`)."""


def _invalid(name: str, message: str) -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={name: [message]},
    )


# --- the start's checks ------------------------------------------------------------------


def build(installed: Iterable[InstalledModule]) -> dict[str, Source]:
    """Every searched content type and its source. ValueError, naming the
    module, when its `search.py` and its module.json disagree."""
    found: dict[str, Source] = {}
    for module in installed:
        declared = {
            str(entry.get("key"))
            for entry in module.manifest.raw.get("content_types") or []
            if entry.get("search") is True
        }
        own: dict[str, Source] = {}
        for source in module.searchable:
            if not isinstance(source, Source):
                raise ValueError(f"{module.id}'s {source!r} in SEARCH isn't a search.Source.")
            kind = getattr(source, "content_type", None)
            if not isinstance(kind, str) or kind.partition(".")[0] != module.id:
                raise ValueError(
                    f"{module.id} may only search {module.id}.* content types, not {kind}."
                )
            if kind in own or kind in found:
                raise ValueError(f"The content type {kind} is searched twice.")
            own[kind] = source
        for kind in sorted(declared - set(own)):
            raise ValueError(
                f"{module.id}'s content_types lists {kind} with search, but its search.py's "
                "SEARCH has no source of that type."
            )
        for kind in sorted(set(own) - declared):
            raise ValueError(
                f"{module.id}'s search.py answers for {kind}, but its module.json's "
                f"content_types doesn't list {kind} with search: true."
            )
        found.update(own)
    return found


_sources: dict[str, Source] = {}
_language = "english"


def install(sources: Mapping[str, Source], *, language: str) -> None:
    """Sets the sources and the language search reads: `assemble` calls it."""
    global _sources, _language
    _sources = dict(sources)
    _language = language


def searched() -> list[str]:
    """Every content type site search finds, whether its module is on or off."""
    return sorted(_sources)


# --- index and remove, in the caller's transaction --------------------------------------


def lock_key(*parts: object) -> int:
    """The second key of an advisory lock on `parts`."""
    return zlib.crc32(":".join(map(str, parts)).encode()) - 2**31


async def _hold(db: AsyncSession, content_type: str, content_id: uuid.UUID) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock_shared(:kind, :key)"),
        {"kind": TYPE_LOCK, "key": lock_key(content_type)},
    )
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:kind, :key)"),
        {"kind": ITEM_LOCK, "key": lock_key(content_type, content_id)},
    )


def _searched(content_type: str) -> Source:
    source = _sources.get(content_type)
    if source is None:
        raise ValueError(
            f"{content_type} isn't searched: no module.json lists it with search: true "
            "beside a source in its search.py."
        )
    return source


def _clean(value: str) -> str:
    return value.replace(chr(0), "")


def _checked(doc: Document) -> Document:
    """The document as it's stored: no NUL, the title on one line, both cut
    to their length. ValueError for no title or a path off the site."""
    path = doc.path
    if not (
        isinstance(path, str)
        and path.startswith("/")
        and not path.startswith("//")
        and len(path) <= MAX_PATH
        and not any(ord(character) < 32 or character == chr(92) for character in path)
    ):
        raise ValueError(
            f"A document's path is the site's own, such as /blog/jazz, at most {MAX_PATH} "
            f"characters: not {path!r}."
        )
    title = " ".join(_clean(doc.title).split())[:MAX_TITLE]
    if not title:
        raise ValueError(f"{doc.type} {doc.id}: a document needs a title.")
    return replace(doc, title=title, body=_clean(doc.body)[:MAX_BODY])


async def _public(db: AsyncSession, content_type: str, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """Those of `ids` the public may see: all of them for a type without
    lifecycle, the published rows for one with it."""
    model = lifecycle.model_of(content_type)
    if model is None or not ids:
        return set(ids)
    column = getattr(model, "id")  # noqa: B009 - the mixin declares no id
    shown = await db.scalars(select(column).where(column.in_(ids), lifecycle.visible(model)))
    return set(shown.all())


async def _write(db: AsyncSession, *docs: Document) -> None:
    """Stores the documents, replacing any row they had, in SEARCH_LANGUAGE."""
    rows = {
        (doc.type, doc.id): {
            "content_type": doc.type,
            "content_id": doc.id,
            "title": doc.title,
            "body": doc.body,
            "path": doc.path,
            "language": _language,
            "updated_at": clock.now(),
        }
        for doc in docs
    }
    if not rows:
        return
    statement = insert(_Row).values(list(rows.values()))
    changed = ("title", "body", "path", "language", "updated_at")
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=["content_type", "content_id"],
            set_={name: statement.excluded[name] for name in changed},
        )
    )


async def _drop(db: AsyncSession, content_type: str, content_id: uuid.UUID) -> None:
    await db.execute(
        delete(_Row).where(_Row.content_type == content_type, _Row.content_id == content_id)
    )


async def index(db: AsyncSession, doc: Document) -> None:
    """Adds or replaces the document in the caller's transaction; a lifecycle
    type's row that isn't published is removed instead. ValueError for a type
    nobody searches, no title, or a path off the site."""
    _searched(doc.type)
    checked = _checked(doc)
    await _hold(db, checked.type, checked.id)
    if checked.id in await _public(db, checked.type, [checked.id]):
        await _write(db, checked)
    else:
        await _drop(db, checked.type, checked.id)


async def remove(db: AsyncSession, content_type: str, content_id: uuid.UUID) -> None:
    """Takes the thing out of search in the caller's transaction, for a module
    hiding or deleting it. ValueError for a type nobody searches."""
    _searched(content_type)
    await _hold(db, content_type, content_id)
    await _drop(db, content_type, content_id)


# --- the kernel hearing kernel.content.*, and the reindex ------------------------------


async def _sync(db: AsyncSession, source: Source, content_id: uuid.UUID) -> None:
    """The document as the content is now: its source's answer while the
    thing is there and public, else no row."""
    kind = source.content_type
    await _hold(db, kind, content_id)
    found = await source.document(db, content_id)
    if found is not None and (found.type, found.id) != (kind, content_id):
        raise ValueError(f"{kind}'s source answered {found.type} {found.id} for {content_id}.")
    if found is not None and content_id in await _public(db, kind, [content_id]):
        await _write(db, _checked(found))
    else:
        await _drop(db, kind, content_id)


async def _heard(ctx: jobs.Context, event: events.Event) -> None:
    said: events.ContentPublished | events.ContentUnpublished = (
        event.parse(events.ContentPublished)
        if event.name == "kernel.content.published"
        else event.parse(events.ContentUnpublished)
    )
    source = _sources.get(said.type)
    if source is None:  # a type nobody searches
        return
    async with ctx.sessions() as db:
        await _sync(db, source, said.id)
        await db.commit()


#: The kernel's listeners: published or unpublished, the thing as it is now.
ON_PUBLISHED = events.on("kernel.content.published", "kernel.search_published")(_heard)
ON_UNPUBLISHED = events.on("kernel.content.unpublished", "kernel.search_unpublished")(_heard)


async def _rebuild(writing: AsyncSession, reading: AsyncSession, kind: str, source: Source) -> None:
    await writing.execute(
        text("SELECT pg_advisory_xact_lock(:kind, :key)"),
        {"kind": TYPE_LOCK, "key": lock_key(kind)},
    )
    await writing.execute(delete(_Row).where(_Row.content_type == kind))
    batch: list[Document] = []

    async def flush() -> None:
        shown = await _public(writing, kind, [doc.id for doc in batch])
        await _write(writing, *(doc for doc in batch if doc.id in shown))
        batch.clear()

    async for found in source.documents(reading):
        if found.type != kind:
            raise ValueError(f"{kind}'s source gave a document of {found.type}.")
        batch.append(_checked(found))
        if len(batch) >= BATCH:
            await flush()
    await flush()


async def _reindex(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    """Rebuilds each searched type from its source, a type to a transaction,
    then drops the rows of types no module searches now."""
    for kind, source in sorted(_sources.items()):
        async with ctx.sessions() as writing, ctx.sessions() as reading:
            await _rebuild(writing, reading, kind, source)
            await writing.commit()
    async with ctx.sessions() as db:
        await db.execute(delete(_Row).where(_Row.content_type.not_in(sorted(_sources))))
        await db.commit()


#: The kernel's reindex, run on demand.
REINDEX = jobs.handler("kernel.search_reindex", tries=3, timeout=3600)(_reindex)


# --- find: what GET /api/kernel/search answers ---------------------------------------


def _words(q: str) -> str:
    if chr(0) in q:
        raise _invalid("q", "A search has no NUL in it.")
    words = " ".join(q.split())
    if not words:
        raise _invalid("q", "Search for some words.")
    if len(words) > MAX_QUERY:
        raise _invalid("q", f"A search is at most {MAX_QUERY} characters.")
    return words


def _cursor_of(rank: float, content_type: str, content_id: uuid.UUID) -> str:
    return f"{rank!r}:{content_type}:{content_id}"


def _after(cursor: str) -> tuple[float, str, uuid.UUID]:
    rank, _, rest = cursor.partition(":")
    kind, _, ident = rest.partition(":")
    try:
        value, found = float(rank), uuid.UUID(ident)
    except ValueError:
        raise _invalid("cursor", "Not a page of these results.") from None
    if not (math.isfinite(value) and value >= 0 and CONTENT_TYPE.fullmatch(kind)):
        raise _invalid("cursor", "Not a page of these results.")
    return value, kind, found


async def find(
    db: AsyncSession, q: str, *, types: Sequence[str], cursor: str | None, limit: int
) -> dict[str, Any]:
    """A page of the documents of `types` matching `q`, read as
    websearch_to_tsquery reads it ("quoted phrases", or, -not), the best
    first. 422 `kernel.invalid_request` for no words, or a bad cursor."""
    words = _words(q)
    after = _after(cursor) if cursor is not None else None
    if not types:
        return {"items": [], "next_cursor": None}
    query = func.websearch_to_tsquery(cast(literal(_language), REGCONFIG), words)
    rank = cast(func.ts_rank(_Row.tsv, query), Float).label("rank")
    hits = (
        select(
            _Row.content_type,
            _Row.content_id,
            _Row.title,
            _Row.path,
            _Row.body,
            _Row.language,
            rank,
        )
        .where(_Row.tsv.op("@@")(query), _Row.content_type.in_(list(types)))
        .subquery()
    )
    page = select(hits)
    if after is not None:
        value, kind, ident = after
        page = page.where(
            (hits.c.rank < literal(value, Float))
            | (
                (hits.c.rank == literal(value, Float))
                & (
                    tuple_(hits.c.content_type, hits.c.content_id)
                    > tuple_(literal(kind, String), literal(ident, UUID(as_uuid=True)))
                )
            )
        )
    order = (hits.c.rank.desc(), hits.c.content_type, hits.c.content_id)
    limited = page.order_by(*order).limit(limit + 1).subquery()
    snippet = func.ts_headline(
        limited.c.language, func.left(limited.c.body, SNIPPET_FROM), query, SNIPPET
    )
    rows = list(
        await db.execute(
            select(
                limited.c.content_type,
                limited.c.content_id,
                limited.c.title,
                limited.c.path,
                limited.c.rank,
                snippet.label("snippet"),
            ).order_by(limited.c.rank.desc(), limited.c.content_type, limited.c.content_id)
        )
    )
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {
                "type": row.content_type,
                "id": str(row.content_id),
                "title": row.title,
                "snippet": row.snippet,
                "path": row.path,
            }
            for row in rows
        ],
        "next_cursor": (
            _cursor_of(rows[-1].rank, rows[-1].content_type, rows[-1].content_id) if more else None
        ),
    }

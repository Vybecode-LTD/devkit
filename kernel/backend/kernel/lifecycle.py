"""Content lifecycle: draft, scheduled and published (decision 0052, hook 1;
`dev plans/contracts/hooks.md`; SPEC.md sections 5, 6, 7, 10 and 11).

A module's public content takes part by subclassing `Publishable`, naming
its type, and listing the model in its `lifecycle.py`:

    class Post(lifecycle.Publishable, Base):
        __tablename__ = "blog_post"
        __content_type__ = "blog.post"
        ...

    PUBLISHABLE = (Post,)  # blog/lifecycle.py

module.json names the type too, in `content_types` with `"lifecycle": true`.
The start refuses either one without the other. A module that doesn't take
part declares neither and loses nothing.

- `publish(db, row)`, `schedule(db, row, at)` and `unpublish(db, row)` change
  the columns in the caller's transaction. Publish and unpublish emit
  `kernel.content.published` and `kernel.content.unpublished` (`{type, id}`)
  in the same transaction, so a listener (search, notices) hears exactly
  what committed. Each first locks a stored row and reads its three columns
  again, so it judges the row as committed, not as the request loaded it:
  an unpublish racing the publishing job waits for it, then sends its
  event (Codex on #97).
- The kernel's job `kernel.publish_due` runs every minute and publishes each
  scheduled row whose time has passed, dated at that time, so a scheduled
  post shows within a minute of it. A module switched off keeps its
  schedule; its pages stay 404 while it's off.
- `visible(Model)` is the one WHERE for what the public sees: the API's
  reads, the server copy and the sitemap.

**The table** gets `status` (`draft`, `scheduled` or `published`),
`publish_at` and `published_at`, the CHECK `ck_<table>_lifecycle` (a known
status, a scheduled row's time, a published row's date) and the partial
index `ix_<table>_due` the job reads. A module's first migration writes the
same with `*lifecycle.columns()` and `*lifecycle.table_args("<table>")`. The
mixin gives the model its `__table_args__`; a model that needs its own adds
`*lifecycle.table_args(__tablename__)` to them, and the start refuses a table
without the CHECK or the index.

`published_at` is when the row first went public: it's kept when the row is
unpublished and published again. When it last changed is the module's own
column.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from kernel import clock, events, jobs
from kernel.errors import Problem

if TYPE_CHECKING:
    from kernel.modules import InstalledModule

DRAFT = "draft"
SCHEDULED = "scheduled"
PUBLISHED = "published"
STATES = (DRAFT, SCHEDULED, PUBLISHED)

#: What the table holds every row to.
RULE = (
    "status IN ('draft', 'scheduled', 'published')"
    " AND (status <> 'scheduled' OR publish_at IS NOT NULL)"
    " AND (status <> 'published' OR published_at IS NOT NULL)"
)

#: The rows the publishing job takes in one transaction.
BATCH = 200


def columns() -> list[Column[Any]]:
    """The three columns, new each call, for a module's migration:
    `op.create_table("blog_post", ..., *lifecycle.columns(),
    *lifecycle.table_args("blog_post"))`."""
    return [
        Column("status", String(16), nullable=False, server_default=DRAFT),
        Column("publish_at", DateTime(timezone=True), nullable=True),
        Column("published_at", DateTime(timezone=True), nullable=True),
    ]


def table_args(table: str) -> tuple[Any, ...]:
    """The CHECK and the publishing job's index for `table`, new each call."""
    return (
        CheckConstraint(RULE, name="lifecycle"),
        Index(f"ix_{table}_due", "publish_at", postgresql_where=text("status = 'scheduled'")),
    )


class Publishable:
    """The mixin for a module's publishable model. The model sets
    `__content_type__`, `<id>.<entity>`, and has a UUID `id` (SPEC 7)."""

    __content_type__: ClassVar[str]

    status: Mapped[str] = mapped_column(String(16), default=DRAFT, server_default=DRAFT)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The mixin can't declare `id`, `__tablename__` or `__table__` without
    # SQLAlchemy mapping them, so it reads them with getattr (B009).
    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return table_args(str(getattr(cls, "__tablename__")))  # noqa: B009


def _kind(row: object) -> str:
    if not isinstance(row, Publishable):
        raise TypeError(f"{type(row).__name__} isn't a lifecycle.Publishable.")
    return type(row).__content_type__


async def _id(db: AsyncSession, row: Publishable) -> uuid.UUID:
    if getattr(row, "id", None) is None:
        await db.flush()  # a new row gets its id
    found: uuid.UUID = getattr(row, "id")  # noqa: B009
    return found


#: The columns a change judges, read again under the row's lock.
_STATE = ["status", "publish_at", "published_at"]


async def _current(db: AsyncSession, row: Publishable) -> None:
    """Locks a stored row (FOR UPDATE) and reads its lifecycle columns
    again, after writing what the caller changed on it. Another
    transaction holding the row, such as the publishing job's, is waited
    for. A row not stored yet needs neither."""
    if inspect(row).persistent:
        await db.flush()
        await db.refresh(row, attribute_names=_STATE, with_for_update=True)


async def _published(db: AsyncSession, row: Publishable, kind: str, at: datetime) -> None:
    row.status = PUBLISHED
    if row.published_at is None:
        row.published_at = at
    payload = events.ContentPublished(type=kind, id=await _id(db, row))
    await events.emit(db, "kernel.content.published", payload)


async def publish(db: AsyncSession, row: Publishable) -> None:
    """Shows `row` now, in the caller's transaction, and emits
    `kernel.content.published`. A row already published is left as it is."""
    kind = _kind(row)
    await _current(db, row)
    if row.status != PUBLISHED:
        await _published(db, row, kind, clock.now())


async def schedule(db: AsyncSession, row: Publishable, at: datetime) -> None:
    """Publishes `row` at `at`, a time with its zone, still to come:
    `kernel.publish_due` shows it within a minute of then. Refuses a
    published row (409 `kernel.content_published`) and a time gone (422
    `kernel.publish_at_past`); ValueError for a time without a zone."""
    _kind(row)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("A publishing time needs its zone, such as 2026-12-01T09:00:00+00:00.")
    await _current(db, row)
    if row.status == PUBLISHED:
        raise Problem(
            "kernel.content_published",
            409,
            "It's published already: unpublish it before you schedule it.",
        )
    if at <= clock.now():
        raise Problem(
            "kernel.publish_at_past",
            422,
            "That time has passed: choose one still to come, or publish it now.",
        )
    row.status = SCHEDULED
    row.publish_at = at


async def unpublish(db: AsyncSession, row: Publishable) -> None:
    """Back to a draft, in the caller's transaction: a published row is
    hidden and `kernel.content.unpublished` emitted; a scheduled one loses its
    time. A draft is left as it is."""
    kind = _kind(row)
    await _current(db, row)
    was = row.status
    row.status = DRAFT
    row.publish_at = None
    if was == PUBLISHED:
        payload = events.ContentUnpublished(type=kind, id=await _id(db, row))
        await events.emit(db, "kernel.content.unpublished", payload)


def visible(model: type[Publishable]) -> ColumnElement[bool]:
    """The WHERE for what the public sees of `model`: its published rows."""
    return model.status == PUBLISHED


# --- the start's checks, and the publishing job ---------------------------------------


def _carries_the_rules(model: type[Publishable], module_id: str) -> None:
    table = getattr(model, "__table__")  # noqa: B009
    names = {str(item.name) for item in (*table.constraints, *table.indexes)}
    if f"ck_{table.name}_lifecycle" not in names or f"ix_{table.name}_due" not in names:
        raise ValueError(
            f"{module_id}'s {model.__name__}: the table {table.name} lacks the lifecycle "
            f"CHECK or its due index; a model with __table_args__ of its own adds "
            f"*lifecycle.table_args({table.name!r}) to them."
        )


def build(installed: Iterable[InstalledModule]) -> dict[str, type[Publishable]]:
    """Every publishable content type and its model. ValueError, naming the
    module, when its `lifecycle.py` and its module.json disagree."""
    found: dict[str, type[Publishable]] = {}
    for module in installed:
        declared = {
            str(entry.get("key"))
            for entry in module.manifest.raw.get("content_types") or []
            if entry.get("lifecycle") is True
        }
        models: dict[str, type[Publishable]] = {}
        for model in module.publishable:
            if not (isinstance(model, type) and issubclass(model, Publishable)):
                raise ValueError(
                    f"{module.id}'s {getattr(model, '__name__', model)} in PUBLISHABLE isn't a "
                    "lifecycle.Publishable."
                )
            kind = getattr(model, "__content_type__", None)
            if not isinstance(kind, str) or kind.partition(".")[0] != module.id:
                raise ValueError(
                    f"{module.id} may only publish {module.id}.* content types, not {kind}."
                )
            if kind in models or kind in found:
                raise ValueError(f"The content type {kind} is publishable twice.")
            _carries_the_rules(model, module.id)
            models[kind] = model
        for kind in sorted(declared - set(models)):
            raise ValueError(
                f"{module.id}'s content_types lists {kind} with lifecycle, but its "
                "lifecycle.py's PUBLISHABLE has no model of that type."
            )
        for kind in sorted(set(models) - declared):
            raise ValueError(
                f"{module.id}'s lifecycle.py publishes {kind}, but its module.json's "
                f"content_types doesn't list {kind} with lifecycle: true."
            )
        found.update(models)
    return found


_publishable: dict[str, type[Publishable]] = {}


def install(publishable: Mapping[str, type[Publishable]]) -> None:
    """Sets the types the publishing job reads: `create_app` and
    `create_worker` call it."""
    global _publishable
    _publishable = dict(publishable)


async def _publish_due(ctx: jobs.Context) -> None:
    """Publishes every scheduled row whose time has passed, dated at that time,
    a batch to a transaction; a row another worker holds is left to it."""
    for kind, model in sorted(_publishable.items()):
        while True:
            async with ctx.sessions() as db:
                statement = (
                    select(model)
                    .where(model.status == SCHEDULED, model.publish_at <= clock.now())
                    .order_by(model.publish_at)
                    .limit(BATCH)
                    .with_for_update(skip_locked=True)
                )
                rows = list((await db.scalars(statement)).all())
                for row in rows:
                    await _published(db, row, kind, row.publish_at or clock.now())
                await db.commit()
            if len(rows) < BATCH:
                break


#: The kernel's publishing job, every minute.
PUBLISH_DUE = jobs.scheduled("* * * * *", "kernel.publish_due", timeout=300)(_publish_due)

"""The harness's probe modules, mounted by its test support only
(docs/contracts/auth-api.md, "The harness's test support"; K4 contract
change 19).

The repo's real modules wait as `modules/_<id>/` scaffolds, so without these
the contract suite would have nothing to switch off and no job that fails.
`probe` has a route, a settings section with a secret, and two jobs: one
that fails on its one try and one that does nothing. `probe-addon` requires
`probe`, so switching `probe` off turns it off too.

The contract hooks (decision 0052, `dev plans/contracts/hooks.md`) are
tested on them: `probe` fills each hook and `probe-addon` doesn't. Its notes,
`probe.note`, are publishable (hook 1), with a public page at
`/probe/notes/:slug`. Their table, `probe_note`, lives on a metadata of its
own (`TABLES`), which the test support makes when its app starts, so the
migrations never see it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import MetaData, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kernel import jobs, lifecycle, server_copy
from kernel.access import public
from kernel.answers import Answer, Id, When
from kernel.db import NAMING, get_db
from kernel.errors import Problem
from kernel.modules import InstalledModule, Manifest


class ProbeFailure(Exception):
    """What `probe.fail` raises: its name is the job's last error."""


@jobs.handler("probe.fail", tries=1)
async def _fail(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    raise ProbeFailure


@jobs.handler("probe.ok", tries=1)
async def _ok(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    return None


@jobs.handler("probe-addon.ok", tries=1)
async def _addon_ok(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    return None


class ProbeSettings(BaseModel):
    """The settings section `probe`: a word, a number and a secret."""

    model_config = ConfigDict(extra="forbid")

    greeting: str = Field(default="hello", max_length=200)
    count: int = Field(default=1, ge=0, le=100)
    token: SecretStr | None = None


class Pong(Answer):
    """The probe's answer while it's on."""


router = APIRouter()


@router.get("/ping", dependencies=[Depends(public)], response_model=Pong)
async def ping() -> dict[str, Any]:
    return {}


# --- hook 1, content lifecycle: the probe's notes ----------------------------------------


class _Tables(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


#: The probe's tables, made by the test support when its app starts.
TABLES = _Tables.metadata


class ProbeNote(lifecycle.Publishable, _Tables):
    __tablename__ = "probe_note"
    __content_type__ = "probe.note"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))


class NewNote(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    title: str = Field(min_length=1, max_length=200)


class Schedule(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    #: An ISO 8601 time with its zone.
    at: str


class NoteMade(Answer):
    id: Id


class NoteShown(Answer):
    slug: str
    title: str
    published_at: When


async def _note(db: AsyncSession, note_id: uuid.UUID) -> ProbeNote:
    found = await db.get(ProbeNote, note_id)
    if found is None:
        raise Problem("probe.note_not_found", 404, "There's no such note.")
    return found


async def _shown(db: AsyncSession, slug: str) -> ProbeNote | None:
    statement = select(ProbeNote).where(ProbeNote.slug == slug, lifecycle.visible(ProbeNote))
    found: ProbeNote | None = await db.scalar(statement)
    return found


@router.post("/notes", dependencies=[Depends(public)], status_code=201, response_model=NoteMade)
async def new_note(body: NewNote, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    note = ProbeNote(slug=body.slug, title=body.title)
    db.add(note)
    await db.commit()
    return {"id": str(note.id)}


@router.post("/notes/{note_id}/publish", dependencies=[Depends(public)], status_code=204)
async def publish_note(note_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await lifecycle.publish(db, await _note(db, note_id))
    await db.commit()
    return Response(status_code=204)


@router.post("/notes/{note_id}/schedule", dependencies=[Depends(public)], status_code=204)
async def schedule_note(
    note_id: uuid.UUID, body: Schedule, db: AsyncSession = Depends(get_db)
) -> Response:
    try:
        at = datetime.fromisoformat(body.at)
        if at.utcoffset() is None:
            raise ValueError("The time needs its zone, such as 2026-12-01T09:00:00+00:00.")
    except ValueError as error:
        raise Problem("probe.bad_time", 422, str(error)) from None
    await lifecycle.schedule(db, await _note(db, note_id), at)
    await db.commit()
    return Response(status_code=204)


@router.post("/notes/{note_id}/unpublish", dependencies=[Depends(public)], status_code=204)
async def unpublish_note(note_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    await lifecycle.unpublish(db, await _note(db, note_id))
    await db.commit()
    return Response(status_code=204)


@router.get("/notes/{slug}", dependencies=[Depends(public)], response_model=NoteShown)
async def show_note(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    note = await _shown(db, slug)
    if note is None or note.published_at is None:
        raise Problem("probe.note_not_found", 404, "There's no such note.")
    return {"slug": note.slug, "title": note.title, "published_at": note.published_at.isoformat()}


class ProbePages(server_copy.Pages):
    async def page(
        self, db: AsyncSession, path: str, params: Mapping[str, str]
    ) -> server_copy.Page | None:
        note = await _shown(db, params["slug"])
        if note is None:
            return None
        return server_copy.Page(note.title, "A probe note.", server_copy.h1(note.title))

    async def sitemap(self, db: AsyncSession) -> list[server_copy.Entry]:
        found = await db.scalars(select(ProbeNote).where(lifecycle.visible(ProbeNote)))
        return [server_copy.Entry(f"/probe/notes/{note.slug}", title=note.title) for note in found]


def _manifest(
    module_id: str, name: str, summary: str, requires: dict[str, str], **more: Any
) -> Manifest:
    return Manifest.from_dict(
        {
            "id": module_id,
            "name": name,
            "version": "0.1.0",
            "summary": summary,
            "category": "admin",
            "requires": {"modules": requires},
            **more,
        }
    )


MODULES = (
    InstalledModule(
        _manifest(
            "probe",
            "Probe",
            "The test support's module: a route, settings, jobs and the hooks",
            {},
            routes={"api": "/api/probe", "public": ["/probe/notes/:slug"]},
            content_types=[{"key": "probe.note", "label": "Note", "lifecycle": True}],
        ),
        router=router,
        settings=ProbeSettings,
        jobs=(_fail, _ok),
        pages=ProbePages(),
        publishable=(ProbeNote,),
    ),
    InstalledModule(
        _manifest(
            "probe-addon",
            "Probe add-on",
            "Needs the probe, to show a switch-off spreading",
            {"probe": "^0.1"},
        ),
        jobs=(_addon_ok,),
    ),
)

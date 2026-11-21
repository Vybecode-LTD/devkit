"""Hook 1, content lifecycle (decision 0052; `dev plans/contracts/hooks.md` §7, test 1),
over HTTP only, on the probe module's notes: a draft is a 404 and missing
from the sitemap; once it's scheduled and the clock passes its time, the
publishing job shows it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from .conftest import UNCHECKED, Api

pytestmark = pytest.mark.db


async def _note(api: Api) -> tuple[str, str]:
    slug = f"note-{uuid.uuid4().hex[:12]}"
    made = await api.http.post("/api/probe/notes", json={"slug": slug, "title": f"Note {slug}"})
    assert made.status_code == 201, made.text
    return made.json()["id"], slug


async def _seen(api: Api, slug: str) -> tuple[int, int, bool]:
    """The note's API answer, its public page, and whether the sitemap lists it."""
    answer = await api.http.get(f"/api/probe/notes/{slug}")
    page = await api.http.get(f"/probe/notes/{slug}", extensions=UNCHECKED)
    sitemap = await api.http.get("/sitemap.xml", extensions=UNCHECKED)
    assert sitemap.status_code == 200
    return answer.status_code, page.status_code, f"/probe/notes/{slug}<" in sitemap.text


async def test_a_draft_is_hidden_until_it_is_published(api: Api) -> None:
    note, slug = await _note(api)
    assert await _seen(api, slug) == (404, 404, False)
    published = await api.http.post(f"/api/probe/notes/{note}/publish")
    assert published.status_code == 204, published.text
    assert await _seen(api, slug) == (200, 200, True)
    unpublished = await api.http.post(f"/api/probe/notes/{note}/unpublish")
    assert unpublished.status_code == 204, unpublished.text
    assert await _seen(api, slug) == (404, 404, False)


async def test_a_scheduled_note_shows_once_its_time_has_passed(api: Api) -> None:
    note, slug = await _note(api)
    at = datetime.now(UTC) + timedelta(seconds=60)
    scheduled = await api.http.post(
        f"/api/probe/notes/{note}/schedule", json={"at": at.isoformat()}
    )
    assert scheduled.status_code == 204, scheduled.text
    await api.run_jobs()
    assert await _seen(api, slug) == (404, 404, False)
    await api.advance(120)
    queued = await api.http.post("/api/_test/jobs", json={"name": "kernel.publish_due"})
    assert queued.status_code == 201, queued.text
    await api.run_jobs()
    assert await _seen(api, slug) == (200, 200, True)
    shown = (await api.http.get(f"/api/probe/notes/{slug}")).json()
    assert datetime.fromisoformat(shown["published_at"]) == at


async def test_a_time_gone_or_a_published_note_cant_be_scheduled(api: Api) -> None:
    note, _ = await _note(api)
    gone = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
    past = await api.http.post(f"/api/probe/notes/{note}/schedule", json={"at": gone})
    assert (past.status_code, past.json()["code"]) == (422, "kernel.publish_at_past")
    assert (await api.http.post(f"/api/probe/notes/{note}/publish")).status_code == 204
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    published = await api.http.post(f"/api/probe/notes/{note}/schedule", json={"at": later})
    assert (published.status_code, published.json()["code"]) == (409, "kernel.content_published")

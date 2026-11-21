"""Hook 3, search index (decision 0052; `dev plans/contracts/hooks.md` §7, test 3),
over HTTP only, on the probe module's notes: a published note is found by
`GET /api/kernel/search`, and unpublished, it isn't; a module switched off
shows nothing; the reindex keeps what's published."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from .conftest import Api

pytestmark = pytest.mark.db

SEARCH = "/api/kernel/search"


def _word() -> str:
    """A word no other test's notes hold."""
    return f"w{uuid.uuid4().hex[:12]}"


async def _note(api: Api, title: str, body: str = "") -> tuple[str, str]:
    slug = f"note-{uuid.uuid4().hex[:12]}"
    made = await api.http.post(
        "/api/probe/notes", json={"slug": slug, "title": title, "body": body}
    )
    assert made.status_code == 201, made.text
    return made.json()["id"], slug


async def _publish(api: Api, note: str, *, back: bool = False) -> None:
    done = await api.http.post(f"/api/probe/notes/{note}/{'unpublish' if back else 'publish'}")
    assert done.status_code == 204, done.text
    await api.run_jobs()  # the kernel hears kernel.content.* on the jobs queue


async def _search(api: Api, q: str, **params: Any) -> dict[str, Any]:
    found = await api.http.get(SEARCH, params={"q": q, **params})
    assert found.status_code == 200, found.text
    body: dict[str, Any] = found.json()
    return body


async def _ids(api: Api, q: str, **params: Any) -> list[str]:
    return [item["id"] for item in (await _search(api, q, **params))["items"]]


async def test_a_published_note_is_found_and_unpublished_it_isnt(api: Api) -> None:
    word = _word()
    note, slug = await _note(api, f"Mixing {word}", f"How we record and mix {word} live.")
    await api.run_jobs()
    assert await _ids(api, word) == []  # a draft

    await _publish(api, note)
    found = await _search(api, word)
    (item,) = found["items"]
    assert item == {
        "type": "probe.note",
        "id": note,
        "title": f"Mixing {word}",
        "snippet": item["snippet"],
        "path": f"/probe/notes/{slug}",
    }
    assert word in item["snippet"]
    assert found["next_cursor"] is None

    await _publish(api, note, back=True)
    assert await _ids(api, word) == []


async def test_the_type_narrows_the_search_and_an_unknown_one_is_refused(api: Api) -> None:
    word = _word()
    note, _ = await _note(api, f"Typed {word}")
    await _publish(api, note)
    assert await _ids(api, word, type="probe.note") == [note]
    for wrong in ("probe-addon.note", "nothing"):
        refused = await api.http.get(SEARCH, params={"q": word, "type": wrong})
        assert (refused.status_code, refused.json()["code"]) == (422, "kernel.invalid_request")
        assert "type" in refused.json()["errors"]


async def test_a_switched_off_modules_notes_arent_found(api: Api) -> None:
    word = _word()
    note, _ = await _note(api, f"Hidden {word}")
    await _publish(api, note)
    person = await api.make_user(roles=["owner"], totp=True)
    owner = api.another_browser()
    await owner.signed_in_as(person)
    off = await owner.http.put("/api/kernel/admin/modules/probe", json={"on": False})
    assert off.status_code == 200, off.text
    try:
        assert await _ids(api, word) == []
        refused = await api.http.get(SEARCH, params={"q": word, "type": "probe.note"})
        assert refused.status_code == 422
    finally:
        back = await owner.http.put("/api/kernel/admin/modules/probe", json={"on": True})
        assert back.status_code == 200, back.text
    assert await _ids(api, word) == [note]


async def test_the_reindex_keeps_what_is_published_and_only_that(api: Api) -> None:
    word = _word()
    shown, _ = await _note(api, f"Shown {word}")
    draft, _ = await _note(api, f"Draft {word}")
    await _publish(api, shown)
    queued = await api.http.post("/api/_test/jobs", json={"name": "kernel.search_reindex"})
    assert queued.status_code == 201, queued.text
    await api.run_jobs()
    assert await _ids(api, word) == [shown]
    assert draft not in await _ids(api, word)


async def test_the_results_come_a_page_at_a_time(api: Api) -> None:
    word = _word()
    notes = []
    for count in (1, 2, 3, 4):  # more than a page and one
        note, _ = await _note(api, " ".join([word] * count))
        await _publish(api, note)
        notes.append(note)
    first = await _search(api, word, limit=2)
    assert first["next_cursor"] is not None
    second = await _search(api, word, limit=2, cursor=first["next_cursor"])
    assert second["next_cursor"] is None
    seen = [item["id"] for item in (*first["items"], *second["items"])]
    assert seen == list(reversed(notes))  # the most matches first


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "   "},
        {"q": "x" * 201},
        {"q": "jazz", "limit": 0},
        {"q": "jazz", "limit": 51},
        {"q": "jazz", "cursor": "nonsense"},
    ],
)
async def test_what_is_asked_is_checked(api: Api, params: dict[str, Any]) -> None:
    refused = await api.http.get(SEARCH, params=params)
    assert (refused.status_code, refused.json()["code"]) == (422, "kernel.invalid_request")


async def test_search_is_rate_limited(api: Api) -> None:
    for _ in range(30):
        assert (await api.http.get(SEARCH, params={"q": "jazz"})).status_code == 200
    limited = await api.http.get(SEARCH, params={"q": "jazz"})
    assert (limited.status_code, limited.json()["code"]) == (429, "kernel.rate_limited")

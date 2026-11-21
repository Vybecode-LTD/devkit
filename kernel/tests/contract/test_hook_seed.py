"""Hook 4, seed data (decision 0052; `dev plans/contracts/hooks.md` §7, test 4),
over HTTP only: without the permission seeding refuses; with it, the probe
module's seed runs (and `probe-addon`, which has none, doesn't), and seeding
twice leaves the same rows: the same notes, the same term and one seeded
person."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import Api

pytestmark = pytest.mark.db

SEED = "/api/_test/seed"
SEEDED = ["seed-note-1", "seed-note-2"]  # published; seed-note-3 stays a draft
EDITOR = "seed-editor@example.com"


async def _seed(api: Api, **body: Any) -> dict[str, Any]:
    response = await api.http.post(SEED, json=body)
    assert response.status_code == 200, response.text
    answer: dict[str, Any] = response.json()
    return answer


async def _rows(api: Api) -> dict[str, Any]:
    """What the probe's seed made, as a visitor and an owner read it."""
    notes = await api.http.get(
        "/api/probe/notes", params={"vocabulary": "topics", "term": "seeded"}
    )
    assert notes.status_code == 200, notes.text
    shown = []
    for slug in [*notes.json()["items"], "seed-note-3"]:
        page = await api.http.get(f"/api/probe/notes/{slug}")
        shown.append((slug, page.status_code, page.json().get("title")))
    terms = await api.http.get("/api/kernel/terms", params={"vocabulary": "topics"})
    assert terms.status_code == 200, terms.text
    seeded_terms = [term for term in terms.json()["items"] if term["slug"] == "seeded"]
    people = await api.http.get("/api/auth/admin/users", params={"q": EDITOR})
    assert people.status_code == 200, people.text
    return {
        "notes": notes.json()["items"],
        "shown": shown,
        "terms": [(term["slug"], term["label"]) for term in seeded_terms],
        "people": [
            (person["email"], person["roles"], person["verified"])
            for person in people.json()["items"]
        ],
    }


async def test_without_the_permission_seeding_refuses(api: Api) -> None:
    for body in ({}, {"allow": False}):
        refused = await api.http.post(SEED, json=body)
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "harness.seed_refused"
        assert "MECHFRAME_ALLOW_SEED=1" in refused.json()["detail"]


async def test_seeding_twice_leaves_the_same_rows(api: Api) -> None:
    owner = await api.make_user(roles=["owner"], totp=True)
    await api.signed_in_as(owner)

    assert await _seed(api, allow=True) == {"seeded": ["probe"]}  # probe-addon has no seed
    once = await _rows(api)
    assert once["notes"] == SEEDED
    assert [(slug, status) for slug, status, _ in once["shown"]] == [
        ("seed-note-1", 200),
        ("seed-note-2", 200),
        ("seed-note-3", 404),  # a draft
    ]
    assert once["terms"] == [("seeded", "Seeded")]
    assert once["people"] == [(EDITOR, ["editor", "member"], True)]

    assert await _seed(api, allow=True) == {"seeded": ["probe"]}
    assert await _rows(api) == once

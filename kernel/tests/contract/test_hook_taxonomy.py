"""Hook 2, taxonomy (decision 0052; `dev plans/contracts/hooks.md` §7, test 2),
over HTTP only, on the probe module's notes: tagging shows in
`GET /api/kernel/terms`, the terms are managed under `kernel.taxonomy.manage`,
and a vocabulary only modules that are off declare isn't there."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from .conftest import Api

pytestmark = pytest.mark.db

TERMS = "/api/kernel/terms"
ADMIN = "/api/kernel/admin/terms"


def _word(stem: str) -> str:
    return f"{stem}-{uuid.uuid4().hex[:8]}"


async def _note(api: Api) -> tuple[str, str]:
    slug = _word("note")
    made = await api.http.post("/api/probe/notes", json={"slug": slug, "title": f"Note {slug}"})
    assert made.status_code == 201, made.text
    return made.json()["id"], slug


async def _terms(api: Api, vocabulary: str) -> dict[str, Any]:
    listed = await api.http.get(TERMS, params={"vocabulary": vocabulary, "limit": 500})
    assert listed.status_code == 200, listed.text
    body: dict[str, Any] = listed.json()
    return body


async def _staff(api: Api, role: str) -> Api:
    person = await api.make_user(roles=[role], totp=True)
    staff = api.another_browser()
    await staff.signed_in_as(person)
    return staff


async def test_tagging_shows_in_the_terms_and_the_notes(api: Api) -> None:
    note, slug = await _note(api)
    jazz, mixing = _word("jazz"), _word("mixing")
    tagged = await api.http.put(
        f"/api/probe/notes/{note}/terms", json={"vocabulary": "topics", "slugs": [jazz, mixing]}
    )
    assert tagged.status_code == 200, tagged.text
    assert [term["slug"] for term in tagged.json()["terms"]] == sorted([jazz, mixing])

    listed = await _terms(api, "topics")
    assert listed["vocabulary"] == {"key": "topics", "label": "Topics", "hierarchical": True}
    by_slug = {term["slug"]: term for term in listed["items"]}
    assert by_slug[jazz]["label"] == jazz.replace("-", " ").capitalize()
    assert by_slug[jazz]["parent_id"] is None

    # A draft isn't listed under its term; published, it is.
    found = {"vocabulary": "topics", "term": jazz}
    assert (await api.http.get("/api/probe/notes", params=found)).json() == {"items": []}
    assert (await api.http.post(f"/api/probe/notes/{note}/publish")).status_code == 204
    assert (await api.http.get("/api/probe/notes", params=found)).json() == {"items": [slug]}
    shown = (await api.http.get(f"/api/probe/notes/{slug}")).json()
    assert [(term["vocabulary"], term["slug"]) for term in shown["terms"]] == [
        ("topics", jazz),
        ("topics", mixing),
    ]

    # Deleting the note takes its links with it; the terms stay.
    assert (await api.http.delete(f"/api/probe/notes/{note}")).status_code == 204
    assert jazz in {term["slug"] for term in (await _terms(api, "topics"))["items"]}


async def test_a_term_is_managed_only_with_kernel_taxonomy_manage(api: Api) -> None:
    note, _ = await _note(api)
    word = _word("ambient")
    await api.http.put(
        f"/api/probe/notes/{note}/terms", json={"vocabulary": "tags", "slugs": [word]}
    )
    term = {item["slug"]: item for item in (await _terms(api, "tags"))["items"]}[word]

    member = await _staff(api, "member")
    refused = await member.http.delete(f"{ADMIN}/{term['id']}")
    assert refused.status_code == 403, refused.text
    signed_out = await api.http.delete(f"{ADMIN}/{term['id']}")
    assert signed_out.status_code == 401, signed_out.text

    editor = await _staff(api, "editor")
    renamed = await editor.http.patch(f"{ADMIN}/{term['id']}", json={"label": "Ambient music"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["label"] == "Ambient music"
    deleted = await editor.http.delete(f"{ADMIN}/{term['id']}")
    assert deleted.status_code == 204, deleted.text
    assert word not in {item["slug"] for item in (await _terms(api, "tags"))["items"]}
    gone = await editor.http.delete(f"{ADMIN}/{term['id']}")
    assert (gone.status_code, gone.json()["code"]) == (404, "kernel.term_not_found")


async def test_terms_nest_only_in_a_hierarchical_vocabulary(api: Api) -> None:
    editor = await _staff(api, "editor")
    music, genre = _word("music"), _word("genre")
    parent = await editor.http.post(
        ADMIN, json={"vocabulary": "topics", "slug": music, "label": "Music"}
    )
    assert parent.status_code == 201, parent.text
    child = await editor.http.post(
        ADMIN,
        json={
            "vocabulary": "topics",
            "slug": genre,
            "label": "Genre",
            "parent_id": parent.json()["id"],
            "position": 2,
        },
    )
    assert child.status_code == 201, child.text
    assert (child.json()["parent_id"], child.json()["position"]) == (parent.json()["id"], 2)

    taken = await editor.http.post(
        ADMIN, json={"vocabulary": "topics", "slug": music, "label": "Again"}
    )
    assert (taken.status_code, taken.json()["code"]) == (409, "kernel.term_exists")
    elsewhere = await editor.http.post(
        ADMIN,
        json={
            "vocabulary": "tags",
            "slug": _word("x"),
            "label": "X",
            "parent_id": child.json()["id"],
        },
    )
    assert (elsewhere.status_code, elsewhere.json()["code"]) == (422, "kernel.invalid_request")
    tag = await editor.http.post(
        ADMIN, json={"vocabulary": "tags", "slug": _word("t"), "label": "T"}
    )
    assert tag.status_code == 201, tag.text
    flat = await editor.http.post(
        ADMIN,
        json={
            "vocabulary": "tags",
            "slug": _word("y"),
            "label": "Y",
            "parent_id": tag.json()["id"],
        },
    )
    assert (flat.status_code, flat.json()["code"]) == (422, "kernel.invalid_request")
    assert "flat" in flat.json()["errors"]["parent_id"][0]
    circle = await editor.http.patch(
        f"{ADMIN}/{parent.json()['id']}", json={"parent_id": child.json()["id"]}
    )
    assert (circle.status_code, circle.json()["code"]) == (422, "kernel.invalid_request")
    with_children = await editor.http.delete(f"{ADMIN}/{parent.json()['id']}")
    assert (with_children.status_code, with_children.json()["code"]) == (
        409,
        "kernel.term_has_children",
    )
    moved = await editor.http.patch(f"{ADMIN}/{child.json()['id']}", json={"parent_id": None})
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_id"] is None
    assert (await editor.http.delete(f"{ADMIN}/{parent.json()['id']}")).status_code == 204

    owner = await _staff(api, "owner")
    log = await owner.http.get(
        "/api/kernel/admin/audit", params={"action": "kernel.term.", "limit": 100}
    )
    assert log.status_code == 200, log.text
    actions = {
        entry["action"]
        for entry in log.json()["items"]
        if entry["target"] and entry["target"]["id"] in {parent.json()["id"], child.json()["id"]}
    }
    assert actions == {"kernel.term.created", "kernel.term.changed", "kernel.term.deleted"}


async def test_an_unknown_vocabulary_or_one_only_modules_off_declare_isnt_there(api: Api) -> None:
    unknown = await api.http.get(TERMS, params={"vocabulary": "moods"})
    assert (unknown.status_code, unknown.json()["code"]) == (404, "kernel.vocabulary_not_found")

    owner = await _staff(api, "owner")
    off = await owner.http.put("/api/kernel/admin/modules/probe", json={"on": False})
    assert off.status_code == 200, off.text
    try:
        hidden = await api.http.get(TERMS, params={"vocabulary": "topics"})
        assert (hidden.status_code, hidden.json()["code"]) == (404, "kernel.vocabulary_not_found")
    finally:
        back = await owner.http.put("/api/kernel/admin/modules/probe", json={"on": True})
        assert back.status_code == 200, back.text
    assert (await api.http.get(TERMS, params={"vocabulary": "topics"})).status_code == 200


async def test_what_staff_send_is_checked(api: Api) -> None:
    editor = await _staff(api, "editor")
    made = await editor.http.post(
        ADMIN, json={"vocabulary": "tags", "slug": _word("checked"), "label": "Checked"}
    )
    assert made.status_code == 201, made.text
    refused = [
        await editor.http.post(
            ADMIN, json={"vocabulary": "tags", "slug": _word("a"), "label": " "}
        ),
        await editor.http.post(
            ADMIN,
            json={"vocabulary": "topics", "slug": _word("b"), "label": "B", "parent_id": "nope"},
        ),
        await editor.http.post(
            ADMIN, json={"vocabulary": "moods", "slug": _word("c"), "label": "C"}
        ),
        await editor.http.patch(f"{ADMIN}/{made.json()['id']}", json={"slug": None}),
    ]
    assert [(answer.status_code, sorted(answer.json()["errors"])) for answer in refused] == [
        (422, ["label"]),
        (422, ["parent_id"]),
        (422, ["vocabulary"]),
        (422, ["slug"]),
    ]

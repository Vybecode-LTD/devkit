"""The taxonomy hook (decision 0052, hook 2; contract `dev plans/contracts/hooks.md`):
the vocabularies modules declare, the start's checks, and `taxonomy.tag`,
`terms_for`, `tagged` and `untag_all` on the kernel's term tables."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from harness.probe import MODULES as PROBES
from kernel import taxonomy
from kernel.db import Database
from kernel.errors import Problem
from kernel.models import TaxonomyTerm, TaxonomyTermLink, TaxonomyVocabulary
from kernel.modules import InstalledModule, Manifest


def _module(module_id: str, **more: Any) -> InstalledModule:
    return InstalledModule(
        Manifest.from_dict(
            {
                "id": module_id,
                "name": module_id.title(),
                "version": "0.1.0",
                "requires": {"modules": {}},
                **more,
            }
        )
    )


TOPICS = {"key": "topics", "label": "Topics", "hierarchical": True}
TAGS = {"key": "tags", "label": "Tags"}


@pytest.fixture(autouse=True)
def _installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test's vocabularies, and the app's back after it: the contract
    suite's app, built once, reads the same module global."""
    monkeypatch.setattr(
        taxonomy,
        "_declared",
        taxonomy.build(
            [
                _module(
                    "notes",
                    vocabularies=[TOPICS, TAGS],
                    content_types=[
                        {"key": "notes.note", "label": "Note", "taxonomy": ["topics", "tags"]},
                        {"key": "notes.plain", "label": "Plain"},
                    ],
                )
            ]
        ),
    )


def _slug(word: str) -> str:
    return f"{word}-{uuid.uuid4().hex[:8]}"


# --- the start's checks ------------------------------------------------------------------


def test_only_the_module_that_takes_part_shows() -> None:
    found = taxonomy.build(PROBES)
    assert sorted(found.vocabularies) == ["tags", "topics"]
    assert found.vocabularies["topics"] == taxonomy.Vocabulary("topics", "Topics", True, ("probe",))
    assert found.vocabularies["tags"].hierarchical is False
    assert found.content_types == {"probe.note": frozenset({"topics", "tags"})}


def test_two_modules_naming_one_key_share_the_vocabulary() -> None:
    found = taxonomy.build(
        [_module("blog", vocabularies=[TOPICS]), _module("docs", vocabularies=[TOPICS])]
    )
    assert found.vocabularies["topics"].modules == ("blog", "docs")


def test_the_start_refuses_two_modules_disagreeing_on_hierarchical() -> None:
    with pytest.raises(ValueError, match="docs's vocabulary topics isn't hierarchical, but blog's"):
        taxonomy.build(
            [
                _module("blog", vocabularies=[TOPICS]),
                _module("docs", vocabularies=[{**TOPICS, "hierarchical": False}]),
            ]
        )


def test_the_start_refuses_a_content_type_taking_a_vocabulary_its_module_lacks() -> None:
    with pytest.raises(ValueError, match=r"blog's content type blog\.post takes tags"):
        taxonomy.build(
            [
                _module(
                    "blog",
                    vocabularies=[TOPICS],
                    content_types=[{"key": "blog.post", "label": "Post", "taxonomy": ["tags"]}],
                )
            ]
        )


def test_the_start_refuses_a_vocabulary_listed_twice() -> None:
    with pytest.raises(ValueError, match="blog lists the vocabulary topics twice"):
        taxonomy.build([_module("blog", vocabularies=[TOPICS, TOPICS])])


def test_labels_are_made_from_slugs() -> None:
    assert taxonomy.label_of("music-production") == "Music production"
    assert taxonomy.label_of("r-and-b") == "R and b"


# --- tag, terms_for, tagged, untag_all --------------------------------------------------


@pytest.mark.db
async def test_tag_makes_missing_terms_and_sets_exactly_those(database: Database) -> None:
    note = uuid.uuid4()
    jazz, mixing, live = _slug("jazz"), _slug("mixing"), _slug("live")
    async with database.sessions() as db:
        made = await taxonomy.tag(db, "notes.note", note, "topics", [jazz, mixing])
        await db.commit()
    assert [term.slug for term in made] == sorted([jazz, mixing])
    assert {term.label for term in made} == {taxonomy.label_of(jazz), taxonomy.label_of(mixing)}
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", note, "tags", [live])
        await taxonomy.tag(db, "notes.note", note, "topics", [mixing])
        await db.commit()
        found = await taxonomy.terms_for(db, "notes.note", [note])
    assert sorted((term.vocabulary, term.slug) for term in found[note]) == [
        ("tags", live),
        ("topics", mixing),
    ]
    # A term untagged stays: only the link goes.
    async with database.sessions() as db:
        left = await db.scalar(select(func.count()).where(TaxonomyTerm.slug == jazz))
    assert left == 1


@pytest.mark.db
async def test_terms_for_answers_every_id_asked(database: Database) -> None:
    tagged, bare = uuid.uuid4(), uuid.uuid4()
    word = _slug("folk")
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", tagged, "tags", [word])
        await db.commit()
        found = await taxonomy.terms_for(db, "notes.note", [tagged, bare])
    assert [term.slug for term in found[tagged]] == [word]
    assert found[bare] == []


@pytest.mark.db
async def test_tagged_selects_the_content_holding_a_term(database: Database) -> None:
    first, second, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    word, elsewhere = _slug("soul"), _slug("funk")
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", first, "topics", [word])
        await taxonomy.tag(db, "notes.note", second, "topics", [word, elsewhere])
        await taxonomy.tag(db, "notes.note", other, "topics", [elsewhere])
        await db.commit()
        ids = set((await db.scalars(taxonomy.tagged("notes.note", "topics", word))).all())
        in_tags = list((await db.scalars(taxonomy.tagged("notes.note", "tags", word))).all())
    assert ids == {first, second}
    assert in_tags == []


@pytest.mark.db
async def test_untag_all_removes_the_contents_links(database: Database) -> None:
    note = uuid.uuid4()
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", note, "topics", [_slug("blues")])
        await taxonomy.tag(db, "notes.note", note, "tags", [_slug("rock")])
        await db.commit()
        await taxonomy.untag_all(db, "notes.note", note)
        await db.commit()
        links = await db.scalar(select(func.count()).where(TaxonomyTermLink.content_id == note))
    assert links == 0


@pytest.mark.db
@pytest.mark.parametrize(
    "slugs",
    [["Has Capitals"], ["-leading"], ["two--dashes"], ["x" * 81], [f"t-{n}" for n in range(51)]],
)
async def test_tag_refuses_a_bad_slug_or_too_many(database: Database, slugs: list[str]) -> None:
    async with database.sessions() as db:
        with pytest.raises(Problem) as refused:
            await taxonomy.tag(db, "notes.note", uuid.uuid4(), "topics", slugs)
    assert (refused.value.code, refused.value.status) == ("kernel.invalid_request", 422)
    assert "slugs" in (refused.value.errors or {})


@pytest.mark.db
@pytest.mark.parametrize(
    ("content_type", "vocabulary"), [("notes.plain", "topics"), ("notes.note", "moods")]
)
async def test_tag_refuses_what_no_manifest_declares(
    database: Database, content_type: str, vocabulary: str
) -> None:
    async with database.sessions() as db:
        with pytest.raises(ValueError, match="doesn't take"):
            await taxonomy.tag(db, content_type, uuid.uuid4(), vocabulary, ["x"])


@pytest.mark.db
async def test_two_tags_making_one_term_at_once_share_it(database: Database) -> None:
    """The second waits on the first's uncommitted term, then uses it."""
    word = _slug("gospel")
    first, second = uuid.uuid4(), uuid.uuid4()
    async with database.sessions() as db:  # the vocabulary's row, so they race on the term
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), "topics", [_slug("warm-up")])
        await db.commit()
    async with database.sessions() as holding, database.sessions() as other:
        await taxonomy.tag(holding, "notes.note", first, "topics", [word])
        racing = asyncio.create_task(taxonomy.tag(other, "notes.note", second, "topics", [word]))
        await asyncio.sleep(0.3)
        assert not racing.done()  # it waits for the first's term
        await holding.commit()
        (term,) = await asyncio.wait_for(racing, timeout=5)
        await other.commit()
    async with database.sessions() as db:
        found = await taxonomy.terms_for(db, "notes.note", [first, second])
    assert found[first][0].id == found[second][0].id == term.id


def test_the_start_refuses_tagging_another_modules_content_type() -> None:
    with pytest.raises(ValueError, match=r"blog may only tag blog\.\* content types"):
        taxonomy.build(
            [
                _module(
                    "blog",
                    vocabularies=[TOPICS],
                    content_types=[{"key": "shop.item", "label": "Item", "taxonomy": ["topics"]}],
                )
            ]
        )


def test_the_start_refuses_a_bad_vocabulary_key() -> None:
    with pytest.raises(ValueError, match="isn't a vocabulary key"):
        taxonomy.build([_module("blog", vocabularies=[{"key": "Topics", "label": "Topics"}])])


# --- more of tagging, and staff's changes -----------------------------------------------

ACTOR = uuid.uuid4()


def _fresh(monkeypatch: pytest.MonkeyPatch, *, label: str = "Fresh") -> taxonomy.Vocabulary:
    """A vocabulary of the test's own, so its terms are only the test's."""
    key = f"v_{uuid.uuid4().hex[:10]}"
    found = taxonomy.build(
        [
            _module(
                "notes",
                vocabularies=[{"key": key, "label": label, "hierarchical": True}],
                content_types=[{"key": "notes.note", "label": "Note", "taxonomy": [key]}],
            )
        ]
    )
    monkeypatch.setattr(taxonomy, "_declared", found)
    return found.vocabularies[key]


async def _made(database: Database, found: taxonomy.Vocabulary, slug: str, **more: Any) -> Any:
    fields = {"label": slug.title(), "parent_id": None, "position": 0, **more}
    async with database.sessions() as db:
        term = await taxonomy.create(db, found, slug=slug, actor=ACTOR, **fields)
        await db.commit()
    return term


@pytest.mark.db
async def test_no_slugs_clears_that_vocabulary_alone(database: Database) -> None:
    note = uuid.uuid4()
    kept = _slug("kept")
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", note, "topics", [_slug("gone")])
        await taxonomy.tag(db, "notes.note", note, "tags", [kept])
        assert await taxonomy.tag(db, "notes.note", note, "topics", []) == []
        await db.commit()
        found = await taxonomy.terms_for(db, "notes.note", [note])
        assert await taxonomy.terms_for(db, "notes.note", []) == {}
    assert [term.slug for term in found[note]] == [kept]


@pytest.mark.db
async def test_a_vocabularys_row_follows_its_manifest(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fresh(monkeypatch, label="Before")
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), found.key, ["one"])
        await db.commit()
    renamed = taxonomy.Vocabulary(found.key, "After", True, ("notes",))
    monkeypatch.setattr(
        taxonomy,
        "_declared",
        taxonomy.Declared({found.key: renamed}, {"notes.note": frozenset({found.key})}),
    )
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), found.key, ["two"])
        await db.commit()
        label = await db.scalar(
            select(TaxonomyVocabulary.label).where(TaxonomyVocabulary.key == found.key)
        )
    assert label == "After"


@pytest.mark.db
async def test_terms_come_in_pages_by_position_then_slug(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fresh(monkeypatch)
    for slug, position in [("c", 0), ("a", 0), ("b", 1), ("d", 2)]:
        await _made(database, found, slug, position=position)
    async with database.sessions() as db:
        first = await taxonomy.listed(db, found, cursor=None, limit=2)
        rest = await taxonomy.listed(db, found, cursor=first["next_cursor"], limit=2)
        with pytest.raises(Problem) as bad:
            await taxonomy.listed(db, found, cursor="x.y.z", limit=2)
    assert [term["slug"] for term in first["items"]] == ["a", "c"]
    assert [term["slug"] for term in rest["items"]] == ["b", "d"]
    assert rest["next_cursor"] is None
    assert bad.value.errors == {"cursor": ["Not a page of these terms."]}


@pytest.mark.db
async def test_a_parent_must_be_in_the_vocabulary(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fresh(monkeypatch)
    with pytest.raises(Problem) as refused:
        await _made(database, found, "orphan", parent_id=uuid.uuid4())
    assert refused.value.errors == {"parent_id": ["There's no such term in this vocabulary."]}


@pytest.mark.db
async def test_a_change_to_a_taken_slug_or_to_nothing(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fresh(monkeypatch)
    await _made(database, found, "first")
    second = await _made(database, found, "second")
    async with database.sessions() as db:
        with pytest.raises(Problem) as taken:
            await taxonomy.change(db, second.id, {"slug": "first"}, actor=ACTOR)
    assert (taken.value.code, taken.value.status) == ("kernel.term_exists", 409)
    async with database.sessions() as db:
        same = await taxonomy.change(db, second.id, {"label": "Second"}, actor=ACTOR)
        await db.commit()
    assert same == second


@pytest.mark.db
async def test_a_change_waiting_on_a_deletion_finds_the_term_gone(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = _fresh(monkeypatch)
    term = await _made(database, found, "gone")
    async with database.sessions() as deleting, database.sessions() as changing:
        await taxonomy.remove(deleting, term.id, actor=ACTOR)
        racing = asyncio.create_task(
            taxonomy.change(changing, term.id, {"label": "Back"}, actor=ACTOR)
        )
        await asyncio.sleep(0.3)
        assert not racing.done()  # it waits for the vocabulary's lock
        await deleting.commit()
        with pytest.raises(Problem) as missing:
            await asyncio.wait_for(racing, timeout=5)
    assert missing.value.code == "kernel.term_not_found"


@pytest.mark.db
async def test_two_tags_of_one_thing_at_once_leave_one_of_them(database: Database) -> None:
    """The second waits for the first, then replaces its terms: never the
    union of both (Codex on #98)."""
    note = uuid.uuid4()
    first, second = _slug("first"), _slug("second")
    async with database.sessions() as db:  # both terms exist, so neither waits on the other's
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), "topics", [first, second])
        await db.commit()
    async with database.sessions() as holding, database.sessions() as other:
        await taxonomy.tag(holding, "notes.note", note, "topics", [first])
        racing = asyncio.create_task(taxonomy.tag(other, "notes.note", note, "topics", [second]))
        await asyncio.sleep(0.3)
        assert not racing.done()  # it waits for the first's tagging of the same thing
        await holding.commit()
        await asyncio.wait_for(racing, timeout=5)
        await other.commit()
    async with database.sessions() as db:
        found = await taxonomy.terms_for(db, "notes.note", [note])
    assert [term.slug for term in found[note]] == [second]


@pytest.mark.parametrize("label", ["x" * 61, "Top" + chr(0) + "ics", ""])
def test_the_start_refuses_a_vocabulary_label_it_couldnt_store(label: str) -> None:
    with pytest.raises(ValueError, match="label"):
        taxonomy.build([_module("blog", vocabularies=[{"key": "topics", "label": label}])])


@pytest.mark.db
async def test_two_taggings_making_new_terms_in_any_order_dont_deadlock(
    database: Database,
) -> None:
    """New terms are made in slug order, so neither holds what the other waits
    for (CodeRabbit on #98)."""
    x, y = _slug("x"), _slug("y")
    async with database.sessions() as db:  # the vocabulary's row, so they race on the terms
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), "topics", [_slug("warm-up")])
        await db.commit()
    async with database.sessions() as holding, database.sessions() as other:
        await taxonomy.tag(holding, "notes.note", uuid.uuid4(), "topics", [x])
        racing = asyncio.create_task(
            taxonomy.tag(other, "notes.note", uuid.uuid4(), "topics", [y, x])
        )
        await asyncio.sleep(0.3)
        assert not racing.done()  # it waits on x
        await asyncio.wait_for(
            taxonomy.tag(holding, "notes.note", uuid.uuid4(), "topics", [y]), timeout=5
        )
        await holding.commit()
        await asyncio.wait_for(racing, timeout=5)
        await other.commit()


@pytest.mark.db
async def test_staff_deleting_a_term_being_tagged_dont_deadlock(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staff's lock on the vocabulary lets a tagging's new term check its
    vocabulary (CodeRabbit on #98)."""
    found = _fresh(monkeypatch)
    term = await _made(database, found, "held")
    async with database.sessions() as tagging, database.sessions() as staff:
        await taxonomy.tag(tagging, "notes.note", uuid.uuid4(), found.key, ["held"])
        removing = asyncio.create_task(taxonomy.remove(staff, term.id, actor=ACTOR))
        await asyncio.sleep(0.3)
        assert not removing.done()  # it waits for the tagging's hold on the term
        await asyncio.wait_for(
            taxonomy.tag(tagging, "notes.note", uuid.uuid4(), found.key, ["new-one"]), timeout=5
        )
        await tagging.commit()
        await asyncio.wait_for(removing, timeout=5)
        await staff.commit()


@pytest.mark.db
async def test_a_vocabulary_made_flat_shows_no_parents_and_loses_them(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answers show it flat at once; its first write makes it so (CodeRabbit on #98)."""
    found = _fresh(monkeypatch)
    parent = await _made(database, found, "parent")
    child = await _made(database, found, "child", parent_id=parent.id)
    flat = taxonomy.Vocabulary(found.key, found.label, False, ("notes",))
    monkeypatch.setattr(
        taxonomy,
        "_declared",
        taxonomy.Declared({found.key: flat}, {"notes.note": frozenset({found.key})}),
    )
    async with database.sessions() as db:
        page = await taxonomy.listed(db, flat, cursor=None, limit=10)
        assert [term["parent_id"] for term in page["items"]] == [None, None]
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), found.key, ["child"])
        await db.commit()
        stored = await db.scalar(select(TaxonomyTerm.parent_id).where(TaxonomyTerm.id == child.id))
    assert stored is None


@pytest.mark.db
async def test_an_empty_tagging_of_a_vocabulary_made_flat_drops_its_parents(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Untagging is a write too (CodeRabbit on #98)."""
    found = _fresh(monkeypatch)
    parent = await _made(database, found, "parent")
    child = await _made(database, found, "child", parent_id=parent.id)
    flat = taxonomy.Vocabulary(found.key, found.label, False, ("notes",))
    monkeypatch.setattr(
        taxonomy,
        "_declared",
        taxonomy.Declared({found.key: flat}, {"notes.note": frozenset({found.key})}),
    )
    async with database.sessions() as db:
        await taxonomy.tag(db, "notes.note", uuid.uuid4(), found.key, [])
        await db.commit()
        stored = await db.scalar(select(TaxonomyTerm.parent_id).where(TaxonomyTerm.id == child.id))
    assert stored is None

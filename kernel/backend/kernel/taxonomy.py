"""Taxonomy: the vocabularies a module's content is tagged from (decision 0052,
hook 2; `dev plans/contracts/hooks.md`; SPEC.md sections 5, 6, 7 and 10).

A module that takes part declares, in module.json:

    "vocabularies": [{"key": "topics", "label": "Topics", "hierarchical": true}],
    "content_types": [{"key": "blog.post", "label": "Post", "taxonomy": ["topics"]}]

Modules naming the same key share one vocabulary. The start refuses two that
disagree on `hierarchical`, and a content type taking a vocabulary its own
module doesn't declare. A module that doesn't take part declares neither.

- `tag(db, type, id, vocabulary, slugs)` sets the thing's terms in that
  vocabulary to exactly `slugs`, in the caller's transaction, making any term
  missing (its label from its slug, which staff can change).
- `terms_for(db, type, ids)` answers each id's terms, `[]` for none.
- `tagged(type, vocabulary, slug)` is a select of the ids holding a term, for
  `Model.id.in_(...)` beside `lifecycle.visible(Model)`. It matches the term
  itself, not the terms under it.
- `untag_all(db, type, id)` is for a module deleting the thing: links have no
  foreign key to a module's rows.

Terms are public. `GET /api/kernel/terms?vocabulary=` lists a vocabulary's
while a module declaring it is on, and a term made by tagging a draft shows at
once. Staff holding `kernel.taxonomy.manage` add, rename, move and delete
them (`create`, `change` and `remove`, at `/api/kernel/admin/terms`), each
audited. A term with children isn't deleted until they're moved or deleted.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit
from kernel.errors import Problem
from kernel.models import TaxonomyTerm as _Term
from kernel.models import TaxonomyTermLink as _Link
from kernel.models import TaxonomyVocabulary as _Vocabulary

if TYPE_CHECKING:
    from kernel.modules import InstalledModule

#: A vocabulary's key: shared across modules, so not prefixed.
KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
#: A term's slug: lowercase letters and digits joined by single hyphens.
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_SLUG = 80
MAX_LABEL = 80
#: The terms one thing takes from one vocabulary.
MAX_TERMS = 50
#: Where a term sits among its siblings: lower first, then by slug.
MAX_POSITION = 100_000


@dataclass(frozen=True)
class Vocabulary:
    """A vocabulary as the manifests declare it, and the modules declaring it."""

    key: str
    label: str
    hierarchical: bool
    modules: tuple[str, ...]


@dataclass(frozen=True)
class Declared:
    """Every vocabulary, and the vocabularies each content type takes."""

    vocabularies: Mapping[str, Vocabulary]
    content_types: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class Term:
    id: uuid.UUID
    vocabulary: str
    slug: str
    label: str
    parent_id: uuid.UUID | None
    position: int


def label_of(slug: str) -> str:
    """A new term's label: `music-production` is "Music production"."""
    return slug.replace("-", " ").capitalize()


def _invalid(name: str, message: str) -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={name: [message]},
    )


def _is(hierarchical: bool) -> str:
    return "is" if hierarchical else "isn't"


# --- the start's checks ------------------------------------------------------------------


def build(installed: Iterable[InstalledModule]) -> Declared:
    """Every vocabulary the modules declare, and what each content type
    takes. ValueError, naming the module, for one the start refuses."""
    vocabularies: dict[str, Vocabulary] = {}
    content_types: dict[str, frozenset[str]] = {}
    for module in installed:
        raw = module.manifest.raw
        own: set[str] = set()
        for entry in raw.get("vocabularies") or []:
            key, hierarchical = str(entry.get("key")), entry.get("hierarchical") is True
            if not KEY.fullmatch(key):
                raise ValueError(
                    f"{module.id}'s {key!r} isn't a vocabulary key: lowercase letters, digits "
                    "and underscores, up to 40."
                )
            if key in own:
                raise ValueError(f"{module.id} lists the vocabulary {key} twice.")
            own.add(key)
            known = vocabularies.get(key)
            if known is None:
                label = str(entry.get("label") or key)
                vocabularies[key] = Vocabulary(key, label, hierarchical, (module.id,))
            elif known.hierarchical != hierarchical:
                raise ValueError(
                    f"{module.id}'s vocabulary {key} {_is(hierarchical)} hierarchical, but "
                    f"{known.modules[0]}'s {_is(known.hierarchical)}."
                )
            else:
                vocabularies[key] = replace(known, modules=(*known.modules, module.id))
        for entry in raw.get("content_types") or []:
            kind, taken = str(entry.get("key")), [str(key) for key in entry.get("taxonomy") or []]
            if taken and kind.partition(".")[0] != module.id:
                raise ValueError(
                    f"{module.id} may only tag {module.id}.* content types, not {kind}."
                )
            for key in taken:
                if key not in own:
                    raise ValueError(
                        f"{module.id}'s content type {kind} takes {key}, a vocabulary its "
                        "module.json doesn't declare."
                    )
            if taken:
                content_types[kind] = frozenset(taken)
    return Declared(vocabularies, content_types)


_declared = Declared({}, {})


def install(declared: Declared) -> None:
    """Sets what tagging and the terms routes read: `assemble` calls it."""
    global _declared
    _declared = declared


def vocabulary(key: str) -> Vocabulary | None:
    return _declared.vocabularies.get(key)


# --- tagging ------------------------------------------------------------------------------


def _takes(content_type: str, key: str) -> Vocabulary:
    if key not in _declared.content_types.get(content_type, frozenset()):
        raise ValueError(
            f"{content_type} doesn't take {key}: no module.json lists that content type "
            "with it in its taxonomy."
        )
    return _declared.vocabularies[key]


def _slugs(slugs: Iterable[str]) -> list[str]:
    found = list(dict.fromkeys(slugs))
    if len(found) > MAX_TERMS:
        raise _invalid("slugs", f"At most {MAX_TERMS} terms from one vocabulary.")
    for slug in found:
        if not (isinstance(slug, str) and len(slug) <= MAX_SLUG and SLUG.fullmatch(slug)):
            raise _invalid(
                "slugs",
                "Each is lowercase letters and digits joined by single hyphens, "
                f"at most {MAX_SLUG} characters.",
            )
    return found


async def _vocabulary_id(db: AsyncSession, found: Vocabulary) -> uuid.UUID:
    """The vocabulary's row, made the first time it's used and kept in step
    with the manifests' label and `hierarchical`."""
    asked = select(_Vocabulary.id, _Vocabulary.label, _Vocabulary.hierarchical).where(
        _Vocabulary.key == found.key
    )
    row = (await db.execute(asked)).one_or_none()
    if row is None:
        await db.execute(
            insert(_Vocabulary)
            .values(
                id=uuid.uuid4(), key=found.key, label=found.label, hierarchical=found.hierarchical
            )
            .on_conflict_do_nothing(index_elements=["key"])
        )
        row = (await db.execute(asked)).one()
    if (row.label, row.hierarchical) != (found.label, found.hierarchical):
        await db.execute(
            update(_Vocabulary)
            .where(_Vocabulary.id == row.id)
            .values(label=found.label, hierarchical=found.hierarchical)
        )
    found_id: uuid.UUID = row.id
    return found_id


_COLUMNS = (_Term.id, _Term.slug, _Term.label, _Term.parent_id, _Term.position)


def _term(key: str, row: Any) -> Term:
    return Term(row.id, key, row.slug, row.label, row.parent_id, row.position)


async def _terms(db: AsyncSession, found: Vocabulary, slugs: Sequence[str]) -> list[Term]:
    """The terms with these slugs, made where missing, each held against
    deletion (FOR KEY SHARE) until the caller's transaction ends. A term
    another transaction is making is waited for, then used."""
    vocabulary_id = await _vocabulary_id(db, found)
    terms: dict[str, Term] = {}
    for _ in range(5):
        missing = [slug for slug in slugs if slug not in terms]
        if not missing:
            break
        held = await db.execute(
            select(*_COLUMNS)
            .where(_Term.vocabulary_id == vocabulary_id, _Term.slug.in_(missing))
            .with_for_update(read=True, key_share=True)
        )
        terms.update((row.slug, _term(found.key, row)) for row in held)
        new = [slug for slug in missing if slug not in terms]
        if new:
            made = await db.execute(
                insert(_Term)
                .values(
                    [
                        {
                            "id": uuid.uuid4(),
                            "vocabulary_id": vocabulary_id,
                            "slug": slug,
                            "label": label_of(slug),
                        }
                        for slug in new
                    ]
                )
                .on_conflict_do_nothing(index_elements=["vocabulary_id", "slug"])
                .returning(*_COLUMNS)
            )
            terms.update((row.slug, _term(found.key, row)) for row in made)
    else:  # pragma: no cover - only a term deleted again between every making and reading
        raise Problem(
            "kernel.terms_changed", 409, "The terms changed while this was saved: try again."
        )
    return sorted(terms.values(), key=lambda term: (term.position, term.slug))


async def tag(
    db: AsyncSession,
    content_type: str,
    content_id: uuid.UUID,
    vocabulary: str,
    slugs: Iterable[str],
) -> list[Term]:
    """Sets the thing's terms in `vocabulary` to exactly `slugs`, in the
    caller's transaction, making any missing; answers them. ValueError for a
    content type its module.json doesn't list with that vocabulary; 422
    `kernel.invalid_request` for a bad slug or more than 50."""
    found = _takes(content_type, vocabulary)
    wanted = _slugs(slugs)
    terms = await _terms(db, found, wanted) if wanted else []
    kept = [term.id for term in terms]
    in_vocabulary = select(_Term.id).join(_Vocabulary).where(_Vocabulary.key == vocabulary)
    unlinked = delete(_Link).where(
        _Link.content_type == content_type,
        _Link.content_id == content_id,
        _Link.term_id.in_(in_vocabulary),
    )
    if kept:
        unlinked = unlinked.where(_Link.term_id.not_in(kept))
    await db.execute(unlinked)
    if wanted:
        await db.execute(
            insert(_Link)
            .values(
                [
                    {"term_id": ident, "content_type": content_type, "content_id": content_id}
                    for ident in kept
                ]
            )
            .on_conflict_do_nothing()
        )
    return terms


async def terms_for(
    db: AsyncSession, content_type: str, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[Term]]:
    """Each id's terms, by vocabulary, then position and slug; `[]` for an
    id with none."""
    wanted = list(dict.fromkeys(ids))
    found: dict[uuid.UUID, list[Term]] = {ident: [] for ident in wanted}
    if not wanted:
        return found
    rows = await db.execute(
        select(_Link.content_id, _Vocabulary.key, *_COLUMNS)
        .join(_Term, _Term.id == _Link.term_id)
        .join(_Vocabulary, _Vocabulary.id == _Term.vocabulary_id)
        .where(_Link.content_type == content_type, _Link.content_id.in_(wanted))
        .order_by(_Vocabulary.key, _Term.position, _Term.slug)
    )
    for row in rows:
        found[row.content_id].append(_term(row.key, row))
    return found


def tagged(content_type: str, vocabulary: str, slug: str) -> Select[uuid.UUID]:
    """The ids of the `content_type` things holding the term: a select for
    `Model.id.in_(...)`."""
    return (
        select(_Link.content_id)
        .join(_Term, _Term.id == _Link.term_id)
        .join(_Vocabulary, _Vocabulary.id == _Term.vocabulary_id)
        .where(
            _Link.content_type == content_type, _Vocabulary.key == vocabulary, _Term.slug == slug
        )
    )


async def untag_all(db: AsyncSession, content_type: str, content_id: uuid.UUID) -> None:
    """Removes every term from the thing, for a module deleting it."""
    await db.execute(
        delete(_Link).where(_Link.content_type == content_type, _Link.content_id == content_id)
    )


# --- the terms routes: the public list, and staff's changes -----------------------------

_DIGITS = re.compile(r"[0-9]{1,6}")


def _cursor_of(term: Term) -> str:
    return f"{term.position}.{term.slug}"


def _after(cursor: str) -> tuple[int, str]:
    position, dot, slug = cursor.partition(".")
    if not (dot and _DIGITS.fullmatch(position) and SLUG.fullmatch(slug) and len(slug) <= MAX_SLUG):
        raise _invalid("cursor", "Not a page of these terms.")
    return int(position), slug


async def listed(
    db: AsyncSession, found: Vocabulary, *, cursor: str | None, limit: int
) -> dict[str, Any]:
    """A page of the vocabulary's terms, by position and then slug."""
    statement = (
        select(*_COLUMNS)
        .join(_Vocabulary, _Vocabulary.id == _Term.vocabulary_id)
        .where(_Vocabulary.key == found.key)
        .order_by(_Term.position, _Term.slug)
        .limit(limit + 1)
    )
    if cursor is not None:
        position, slug = _after(cursor)
        statement = statement.where(
            (_Term.position > position) | ((_Term.position == position) & (_Term.slug > slug))
        )
    terms = [_term(found.key, row) for row in await db.execute(statement)]
    more = len(terms) > limit
    terms = terms[:limit]
    return {
        "vocabulary": {"key": found.key, "label": found.label, "hierarchical": found.hierarchical},
        "items": [view(term) for term in terms],
        "next_cursor": _cursor_of(terms[-1]) if more else None,
    }


def view(term: Term) -> dict[str, Any]:
    return {
        "id": str(term.id),
        "vocabulary": term.vocabulary,
        "slug": term.slug,
        "label": term.label,
        "parent_id": str(term.parent_id) if term.parent_id else None,
        "position": term.position,
    }


def not_found() -> Problem:
    return Problem("kernel.term_not_found", 404, "There's no such term.")


def _taken(slug: str) -> Problem:
    return Problem("kernel.term_exists", 409, f"This vocabulary has a term {slug} already.")


async def _locked(db: AsyncSession, found: Vocabulary) -> uuid.UUID:
    """The vocabulary's row, locked (FOR UPDATE) for one change of staff's at a
    time: no two moves make a circle, and no term gains a child while it's
    deleted."""
    vocabulary_id = await _vocabulary_id(db, found)
    await db.execute(
        select(_Vocabulary.id).where(_Vocabulary.id == vocabulary_id).with_for_update()
    )
    return vocabulary_id


async def _check_parent(
    db: AsyncSession,
    found: Vocabulary,
    vocabulary_id: uuid.UUID,
    parent_id: uuid.UUID,
    moving: uuid.UUID | None = None,
) -> None:
    if not found.hierarchical:
        raise _invalid("parent_id", f"{found.label} is flat: its terms have no parents.")
    above = (
        select(_Term.id, _Term.parent_id)
        .where(_Term.id == parent_id, _Term.vocabulary_id == vocabulary_id)
        .cte("above", recursive=True)
    )
    above = above.union_all(
        select(_Term.id, _Term.parent_id).join(above, _Term.id == above.c.parent_id)
    )
    chain = set((await db.scalars(select(above.c.id))).all())
    if parent_id not in chain:
        raise _invalid("parent_id", "There's no such term in this vocabulary.")
    if moving is not None and moving in chain:
        raise _invalid("parent_id", "A term can't sit under itself or a term under it.")


async def _one(db: AsyncSession, term_id: uuid.UUID) -> tuple[Vocabulary, Any]:
    """The term's vocabulary, locked, and the term read under that lock."""
    key = await db.scalar(
        select(_Vocabulary.key)
        .join(_Term, _Term.vocabulary_id == _Vocabulary.id)
        .where(_Term.id == term_id)
    )
    found = vocabulary(key) if key is not None else None
    if found is None:
        raise not_found()
    vocabulary_id = await _locked(db, found)
    row = (
        await db.execute(
            select(_Term.vocabulary_id, *_COLUMNS).where(
                _Term.id == term_id, _Term.vocabulary_id == vocabulary_id
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    return found, row


async def create(
    db: AsyncSession,
    found: Vocabulary,
    *,
    slug: str,
    label: str,
    parent_id: uuid.UUID | None,
    position: int,
    actor: uuid.UUID,
) -> Term:
    """Adds a term, audited as `kernel.term.created`. 409 `kernel.term_exists`
    for a slug taken; 422 for a parent in a flat vocabulary or elsewhere."""
    vocabulary_id = await _locked(db, found)
    if parent_id is not None:
        await _check_parent(db, found, vocabulary_id, parent_id)
    term = Term(uuid.uuid4(), found.key, slug, label, parent_id, position)
    try:
        async with db.begin_nested():
            await db.execute(
                insert(_Term).values(
                    id=term.id,
                    vocabulary_id=vocabulary_id,
                    slug=slug,
                    label=label,
                    parent_id=parent_id,
                    position=position,
                )
            )
    except IntegrityError:
        raise _taken(slug) from None
    audit.record(
        db,
        "kernel.term.created",
        actor=actor,
        target=("kernel.term", term.id),
        details={"vocabulary": found.key, "slug": slug},
    )
    return term


#: The fields staff may change, as a PATCH names them.
FIELDS = ("slug", "label", "parent_id", "position")


async def change(
    db: AsyncSession, term_id: uuid.UUID, changes: Mapping[str, Any], *, actor: uuid.UUID
) -> Term:
    """Changes the fields named, audited as `kernel.term.changed` with their
    names. 404 `kernel.term_not_found`; 409 `kernel.term_exists`; 422 for a
    parent in a flat vocabulary, elsewhere, or under the term itself."""
    found, row = await _one(db, term_id)
    if changes.get("parent_id") is not None:
        await _check_parent(db, found, row.vocabulary_id, changes["parent_id"], moving=term_id)
    changed = {field: value for field, value in changes.items() if getattr(row, field) != value}
    if changed:
        try:
            async with db.begin_nested():
                await db.execute(update(_Term).where(_Term.id == term_id).values(**changed))
        except IntegrityError:
            raise _taken(str(changes.get("slug"))) from None
        audit.record(
            db,
            "kernel.term.changed",
            actor=actor,
            target=("kernel.term", term_id),
            details={
                "vocabulary": found.key,
                "slug": changed.get("slug", row.slug),
                "fields": sorted(changed),
            },
        )
    merged = {field: changed.get(field, getattr(row, field)) for field in FIELDS}
    return Term(term_id, found.key, **merged)


async def remove(db: AsyncSession, term_id: uuid.UUID, *, actor: uuid.UUID) -> None:
    """Deletes a term and its links, audited as `kernel.term.deleted`. 404
    `kernel.term_not_found`; 409 `kernel.term_has_children` while terms sit
    under it."""
    found, row = await _one(db, term_id)
    if await db.scalar(select(_Term.id).where(_Term.parent_id == term_id).limit(1)) is not None:
        raise Problem(
            "kernel.term_has_children",
            409,
            "Terms sit under this one: move or delete them first.",
        )
    await db.execute(delete(_Term).where(_Term.id == term_id))
    audit.record(
        db,
        "kernel.term.deleted",
        actor=actor,
        target=("kernel.term", term_id),
        details={"vocabulary": found.key, "slug": row.slug},
    )

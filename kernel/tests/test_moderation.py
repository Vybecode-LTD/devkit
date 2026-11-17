"""kernel.moderation: reports, the staff queue, word and link filters,
actions and suspension (SPEC.md 6 and 14.7; decision 0039; contract
dev plans/contracts/k3-moderation.md).

Each test's people, things and cases are its own, and every read filters on
them: the run's database is shared.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, clock, jobs, moderation, notifications
from kernel.app import create_app
from kernel.auth import sessions
from kernel.auth.models import Role, RolePermission, Totp, User, UserRole
from kernel.db import Database
from kernel.email import CapturingMailer, LogMailer
from kernel.errors import Problem
from kernel.models import AuditEvent, ModerationCase, ModerationReport, ModuleState
from kernel.modules import InstalledModule, Manifest
from kernel.settings import settings

from .conftest import Client, Heard, make_config, unique_id


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


# --- a module with things to report ---------------------------------------------------


@dataclass
class Store:
    """The test module's things: id to what `describe` says of it."""

    items: dict[str, moderation.Item] = field(default_factory=dict)
    fail: bool = False


def _kinds(module_id: str, store: Store) -> tuple[type[moderation.Kind], ...]:
    @moderation.kind(f"{module_id}.post", actions=("hide", "delete"))
    class Post(moderation.Kind):
        async def describe(self, db: AsyncSession, id: str) -> moderation.Item | None:
            return store.items.get(id)

        async def apply(self, db: AsyncSession, id: str, action: str) -> None:
            if store.fail:
                raise RuntimeError("the module's apply failed")
            done = "post_hidden" if action == "hide" else "post_deleted"
            audit.record(db, f"{module_id}.{done}", actor=None, target=(f"{module_id}.post", id))

        async def dismissed(self, db: AsyncSession, id: str) -> None:
            if store.fail:
                raise RuntimeError("the module's release failed")
            audit.record(
                db, f"{module_id}.post_released", actor=None, target=(f"{module_id}.post", id)
            )

    @moderation.kind(f"{module_id}.profile")
    class Profile(moderation.Kind):
        async def describe(self, db: AsyncSession, id: str) -> moderation.Item | None:
            return store.items.get(id)

        async def apply(self, db: AsyncSession, id: str, action: str) -> None:
            raise AssertionError("a profile has no actions of its own")

    return Post, Profile


def _router() -> APIRouter:
    router = APIRouter()

    @router.post("/posts")
    async def post(user: User = Depends(moderation.can_post)) -> dict[str, str]:
        return {"by": str(user.id)}

    return router


@dataclass
class Site:
    app: FastAPI
    module: str
    store: Store
    mailer: CapturingMailer

    @property
    def post(self) -> str:
        return f"{self.module}.post"

    @property
    def profile(self) -> str:
        return f"{self.module}.profile"

    def thing(self, author: User | None, text: str = "Buy cheap watches") -> str:
        ident = uuid.uuid4().hex[:12]
        self.store.items[ident] = moderation.Item(
            author.id if author else None, text, f"/talk/{ident}"
        )
        return ident

    async def mail(self, address: str) -> list[str]:
        await self.app.state.worker.run_due(wait=0)
        return [message.subject for message in self.mailer.to(address)]


@pytest_asyncio.fixture(loop_scope="session")
async def site(migrated_url: str) -> AsyncIterator[Site]:
    module_id = unique_id("talk")
    store = Store()
    module = InstalledModule(
        Manifest.from_dict(
            {
                "id": module_id,
                "name": "Talk",
                "version": "0.1.0",
                "requires": {"kernel": "^0.1", "modules": {}},
            }
        ),
        router=_router(),
        reportable=_kinds(module_id, store),
    )
    mailer = CapturingMailer()
    app = create_app(
        modules=[module],
        config=make_config(database_url=migrated_url, modules_cache_seconds=0),
        mailer=mailer,
    )
    yield Site(app, module_id, store, mailer)
    await app.state.database.dispose()


async def _user(
    db: AsyncSession, *roles: str, second_factor: bool = False, verified: bool = True
) -> User:
    user_id = uuid.uuid4()
    address = f"{user_id.hex[:12]}@site.test"
    user = User(
        id=user_id,
        email=address,
        email_normal=address,
        email_verified_at=clock.now() if verified else None,
        session_epoch=0,
        role_version=0,
    )
    db.add(user)
    await db.flush()
    for role in roles or ("member",):
        db.add(UserRole(user_id=user_id, role_id=role))
    if second_factor:
        db.add(Totp(user_id=user_id, secret_sealed="sealed", confirmed_at=clock.now()))
    await db.commit()
    return user


async def _as(db: AsyncSession, user: User) -> dict[str, str]:
    token, _ = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    return {"cookie": f"{sessions.SESSION_COOKIE}={token}"}


async def _case(db: AsyncSession, case_id: uuid.UUID) -> ModerationCase:
    found = await db.scalar(
        select(ModerationCase)
        .where(ModerationCase.id == case_id)
        .execution_options(populate_existing=True)
    )
    assert found is not None
    return found


async def _cases(db: AsyncSession, kind: str, ident: str) -> list[ModerationCase]:
    found = await db.scalars(
        select(ModerationCase)
        .where(ModerationCase.target_type == kind, ModerationCase.target_id == ident)
        .order_by(ModerationCase.opened_at)
        .execution_options(populate_existing=True)
    )
    return list(found.all())


async def _reports(db: AsyncSession, case_id: uuid.UUID) -> list[ModerationReport]:
    found = await db.scalars(
        select(ModerationReport)
        .where(ModerationReport.case_id == case_id)
        .order_by(ModerationReport.id)
        .execution_options(populate_existing=True)
    )
    return list(found.all())


async def _entries(db: AsyncSession, subject: uuid.UUID) -> list[tuple[str, Any]]:
    found = await db.scalars(
        select(AuditEvent).where(AuditEvent.subject_id == subject).order_by(AuditEvent.id)
    )
    return [(entry.action, entry.details) for entry in found]


async def _fresh(db: AsyncSession, user_id: uuid.UUID) -> User:
    found = await db.scalar(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    assert found is not None
    return found


def _code(response: httpx.Response) -> str:
    assert response.headers["content-type"].startswith("application/problem+json"), response.text
    code: str = response.json()["code"]
    return code


async def _reported(site: Site, db: AsyncSession, author: User | None = None) -> uuid.UUID:
    """A case on a new post, reported once."""
    reporter = await _user(db)
    ident = site.thing(author)
    case_id = await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")
    await db.commit()
    return case_id


# --- declaring what can be reported -----------------------------------------------------


def test_a_kind_is_declared_with_its_name_and_actions() -> None:
    post, profile = _kinds("talk", Store())
    assert (post.name, post.actions) == ("talk.post", frozenset({"hide", "delete"}))
    assert (profile.name, profile.actions) == ("talk.profile", frozenset())


@pytest.mark.parametrize("name", ["post", "Talk.post", "talk.", "talk.Post", "talk post"])
def test_a_kind_s_name_is_owner_dot_entity(name: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        moderation.kind(name)


@pytest.mark.parametrize("actions", [("ban",), ("hide", "time_out"), ("dismiss",)])
def test_a_kind_s_own_actions_are_hide_and_delete(actions: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="hide"):
        moderation.kind("talk.post", actions=actions)


def test_a_kind_is_a_class_of_moderation_kind() -> None:
    with pytest.raises(TypeError, match=r"moderation\.Kind"):
        moderation.kind("talk.post")(object)  # type: ignore[type-var]


def _module(module_id: str, *kinds: type[moderation.Kind]) -> InstalledModule:
    return InstalledModule(
        Manifest.from_dict(
            {
                "id": module_id,
                "name": "M",
                "version": "0.1.0",
                "requires": {"kernel": "^0.1", "modules": {}},
            }
        ),
        reportable=kinds,
    )


def test_the_start_refuses_a_kind_of_another_owner_or_twice_or_undeclared(
    migrated_url: str,
) -> None:
    config = make_config(database_url=migrated_url)
    mine, theirs = unique_id("talk"), unique_id("talk")
    stray = _kinds(theirs, Store())
    with pytest.raises(RuntimeError, match=f"{mine} may only declare"):
        create_app(modules=[_module(mine, *stray)], config=config)
    own = _kinds(mine, Store())
    with pytest.raises(RuntimeError, match="declared twice"):
        create_app(modules=[_module(mine, own[0], own[0])], config=config)

    class Bare(moderation.Kind):
        pass

    with pytest.raises(RuntimeError, match=r"@moderation\.kind"):
        create_app(modules=[_module(mine, Bare)], config=config)

    @moderation.kind(f"{mine}.half")
    class Half(moderation.Kind):
        async def describe(self, db: AsyncSession, id: str) -> moderation.Item | None:
            return None

    with pytest.raises(RuntimeError, match="needs both describe and apply"):
        create_app(modules=[_module(mine, Half)], config=config)


# --- reporting ----------------------------------------------------------------------


async def test_a_report_opens_one_case_and_more_join_it(site: Site, db: AsyncSession) -> None:
    author, ana, ben = await _user(db), await _user(db), await _user(db)
    ident = site.thing(author, "x" * 1500)
    first = await moderation.report(db, (site.post, ident), reporter=ana.id, reason="spam")
    await db.commit()
    clock.advance(5)
    again = await moderation.report(
        db, (site.post, ident), reporter=ben.id, reason="harassment", note="Rude to me"
    )
    repeat = await moderation.report(db, (site.post, ident), reporter=ana.id, reason="hate")
    await db.commit()
    assert first == again == repeat
    [case] = await _cases(db, site.post, ident)
    assert (case.status, case.source, case.author_id, case.report_count) == (
        "open",
        "report",
        author.id,
        2,
    )
    assert (case.excerpt, case.link) == ("x" * 1000, f"/talk/{ident}")
    assert case.last_report_at - case.opened_at >= timedelta(seconds=5)
    reports = await _reports(db, case.id)
    assert [(r.reporter_id, r.reason, r.note) for r in reports] == [
        (ana.id, "spam", None),
        (ben.id, "harassment", "Rude to me"),
    ]


async def test_a_rolled_back_report_leaves_nothing(site: Site, db: AsyncSession) -> None:
    reporter = await _user(db)
    ident = site.thing(None)
    await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")
    await db.rollback()
    assert await _cases(db, site.post, ident) == []


async def test_reporting_what_isn_t_there_is_404(site: Site, db: AsyncSession) -> None:
    reporter = await _user(db)
    for target in [(site.post, "nothing-here"), (f"{site.module}.page", "1"), ("blog.post", "1")]:
        with pytest.raises(Problem) as refused:
            await moderation.report(db, target, reporter=reporter.id, reason="spam")
        assert (refused.value.status, refused.value.code) == (404, "kernel.report_target_unknown")


@pytest.mark.parametrize(
    ("reason", "note"),
    [("rude", None), ("filter", None), ("spam", "x" * 1001), ("spam", "a" + chr(0))],
)
async def test_a_report_s_reason_and_note_are_checked(
    site: Site, db: AsyncSession, reason: str, note: str | None
) -> None:
    reporter = await _user(db)
    ident = site.thing(None)
    with pytest.raises(ValueError, match=r"reason|note"):
        await moderation.report(
            db, (site.post, ident), reporter=reporter.id, reason=reason, note=note
        )
    assert await _cases(db, site.post, ident) == []


@pytest.mark.parametrize("ident", ["", "x" * 65])
async def test_a_target_s_id_is_1_to_64_characters(
    site: Site, db: AsyncSession, ident: str
) -> None:
    reporter = await _user(db)
    with pytest.raises(ValueError, match="1 to 64 characters"):
        await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")


@pytest.mark.parametrize("ident", [True, 4.5, None])
async def test_a_target_s_id_is_text_a_number_or_a_uuid(
    site: Site, db: AsyncSession, ident: Any
) -> None:
    reporter = await _user(db)
    with pytest.raises(ValueError, match="text, a whole number or a UUID"):
        await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")


@pytest.mark.parametrize("link", ["https://elsewhere.test/x", "/" + "x" * 500])
async def test_a_kind_s_link_is_a_path_on_the_site(site: Site, db: AsyncSession, link: str) -> None:
    reporter = await _user(db)
    ident = uuid.uuid4().hex[:12]
    site.store.items[ident] = moderation.Item(None, "text", link)
    with pytest.raises(ValueError, match="a path on this site"):
        await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")


async def test_a_number_or_uuid_id_is_kept_as_text(site: Site, db: AsyncSession) -> None:
    reporter = await _user(db)
    thing = uuid.uuid4()
    site.store.items[str(thing)] = moderation.Item(None, "text")
    site.store.items["42"] = moderation.Item(None, "text")
    await moderation.report(db, (site.post, thing), reporter=reporter.id, reason="spam")
    await moderation.report(db, (site.post, 42), reporter=reporter.id, reason="spam")
    await db.commit()
    assert len(await _cases(db, site.post, str(thing))) == 1
    assert [c.status for c in await _cases(db, site.post, "42")][-1] == "open"


async def test_after_a_case_closes_a_new_report_opens_a_new_case(
    site: Site, db: AsyncSession
) -> None:
    moderator = await _user(db, "editor")
    reporter = await _user(db)
    ident = site.thing(None)
    first = await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")
    await db.commit()
    await moderation.act(db, first, "dismiss", actor=moderator)
    await db.commit()
    second = await moderation.report(db, (site.post, ident), reporter=reporter.id, reason="spam")
    await db.commit()
    assert second != first
    assert [c.status for c in await _cases(db, site.post, ident)] == ["dismissed", "open"]


async def test_reports_at_once_share_one_case(
    site: Site, db: AsyncSession, database: Database
) -> None:
    people = [await _user(db) for _ in range(5)]
    ident = site.thing(None)

    async def one(person: User) -> uuid.UUID:
        async with database.sessions() as session:
            found = await moderation.report(
                session, (site.post, ident), reporter=person.id, reason="spam"
            )
            await session.commit()
            return found

    found = await asyncio.gather(*(one(person) for person in people))
    [case] = await _cases(db, site.post, ident)
    assert set(found) == {case.id}
    assert case.report_count == 5


# --- the filters -------------------------------------------------------------------


def _filters(**values: Any) -> moderation.Filters:
    return moderation.Filters.model_validate(values)


def test_a_held_term_matches_whole_words_after_folding() -> None:
    filters = _filters(held_terms=["spam offer", "Class"])
    assert moderation.check(filters, "Get the SPAM   offer now").reasons == ("term",)
    fullwidth = "".join(chr(0xFEE0 + ord(c)) for c in "SPAM")
    assert moderation.check(filters, f"{fullwidth} offer").hold
    assert moderation.check(filters, "a class act").hold
    for fine in ["spamoffer", "a classic", "a subclass", "spam, offer", "classy"]:
        assert not moderation.check(filters, fine).hold, fine


def test_a_blocked_domain_and_its_subdomains_hold() -> None:
    filters = _filters(blocked_domains=["Spam.Example"], max_links=10)
    for held in [
        "see https://a.spam.example/x",
        "see spam.example",
        "write to bob@spam.example",
        "HTTP://SPAM.EXAMPLE.",
    ]:
        assert moderation.check(filters, held).reasons == ("domain",), held
    for fine in ["see notspam.example", "see spam.example.org", "spam example"]:
        assert not moderation.check(filters, fine).hold, fine


def test_more_links_than_allowed_hold() -> None:
    filters = _filters(max_links=2)
    two = "https://a.test and www.b.test"
    assert not moderation.check(filters, two).hold
    assert moderation.check(filters, two + " http://c.test/x").reasons == ("links",)
    assert moderation.check(_filters(max_links=0), "http://a.test").hold


def test_the_reasons_come_in_one_order() -> None:
    filters = _filters(held_terms=["cheap"], blocked_domains=["spam.test"], max_links=1)
    text = "cheap http://spam.test http://x.test"
    assert moderation.check(filters, text) == moderation.Screen(True, ("term", "domain", "links"))


def test_empty_filters_hold_nothing_but_too_many_links() -> None:
    assert moderation.check(moderation.Filters(), "anything at all, cheap") == moderation.Screen(
        False, ()
    )


@pytest.mark.parametrize(
    "values",
    [
        {"held_terms": [""]},
        {"held_terms": ["   "]},
        {"held_terms": ["x" * 65]},
        {"held_terms": ["x"] * 501},
        {"blocked_domains": ["not a domain"]},
        {"blocked_domains": ["https://spam.test"]},
        {"blocked_domains": ["localhost"]},
        {"max_links": -1},
        {"max_links": 101},
    ],
)
def test_the_filters_settings_are_checked(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        moderation.Filters.model_validate(values)


async def test_screen_reads_the_saved_filters(site: Site, db: AsyncSession) -> None:
    form = await settings.form(db, moderation.SECTION)
    await settings.save(
        db, moderation.SECTION, {"held_terms": ["zorblax"]}, version=form["version"]
    )
    try:
        assert await moderation.screen(db, "a zorblax deal") == moderation.Screen(True, ("term",))
    finally:
        form = await settings.form(db, moderation.SECTION)
        await settings.save(db, moderation.SECTION, {"held_terms": []}, version=form["version"])


async def test_held_text_opens_a_filter_case(site: Site, db: AsyncSession) -> None:
    author = await _user(db)
    ident = site.thing(author, "cheap cheap")
    case_id = await moderation.hold(db, (site.post, ident), reasons=("term", "links"))
    await db.commit()
    case = await _case(db, case_id)
    assert (case.source, case.status, case.report_count, case.author_id) == (
        "filter",
        "open",
        1,
        author.id,
    )
    [held] = await _reports(db, case_id)
    assert (held.reporter_id, held.reason, held.note) == (None, "filter", "term, links")


@pytest.mark.parametrize("reasons", [(), ("term", "rude")])
async def test_a_hold_needs_the_filters_reasons(
    site: Site, db: AsyncSession, reasons: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="filters' reasons"):
        await moderation.hold(db, (site.post, site.thing(None)), reasons=reasons)


# --- acting on a case ----------------------------------------------------------------


async def _released(db: AsyncSession, site: Site, ident: str) -> bool:
    found = await db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.action == f"{site.module}.post_released", AuditEvent.target_id == ident
        )
    )
    return found is not None


async def test_dismissing_closes_the_case_and_tells_the_module(
    site: Site, db: AsyncSession
) -> None:
    moderator, author = await _user(db, "editor"), await _user(db)
    case_id = await _reported(site, db, author)
    before = clock.now()
    await moderation.act(db, case_id, "dismiss", actor=moderator)
    await db.commit()
    case = await _case(db, case_id)
    assert (case.status, case.outcome, case.closed_by) == ("dismissed", "dismiss", moderator.id)
    assert case.closed_at is not None
    assert before <= case.closed_at <= clock.now()
    assert await _released(db, site, case.target_id)
    assert await _entries(db, author.id) == [
        ("kernel.moderation.dismissed", {"case": str(case_id), "reason": None})
    ]
    assert await site.mail(author.email) == []


async def test_dismissing_a_hold_releases_the_text(site: Site, db: AsyncSession) -> None:
    """CodeRabbit on #71: a held post dismissed as a false positive had no way
    back into view. The kind's `dismissed` runs with the case closing."""
    moderator = await _user(db, "editor")
    ident = site.thing(await _user(db), "a cheap deal")
    case_id = await moderation.hold(db, (site.post, ident), reasons=("term",))
    await db.commit()
    moderator_id = moderator.id
    site.store.fail = True
    try:
        with pytest.raises(RuntimeError, match="release failed"):
            await moderation.act(db, case_id, "dismiss", actor=moderator)
        await db.rollback()
    finally:
        site.store.fail = False
    assert (await _case(db, case_id)).status == "open"
    assert not await _released(db, site, ident)
    moderator = await _fresh(db, moderator_id)
    await moderation.act(db, case_id, "dismiss", actor=moderator)
    await db.commit()
    assert (await _case(db, case_id)).status == "dismissed"
    assert await _released(db, site, ident)


async def test_a_kind_need_not_release_anything(site: Site, db: AsyncSession) -> None:
    moderator, reporter = await _user(db, "editor"), await _user(db)
    ident = site.thing(await _user(db))
    case_id = await moderation.report(
        db, (site.profile, ident), reporter=reporter.id, reason="spam"
    )
    await db.commit()
    await moderation.act(db, case_id, "dismiss", actor=moderator)
    await db.commit()
    assert (await _case(db, case_id)).status == "dismissed"


@pytest.mark.parametrize(("action", "done"), [("hide", "post_hidden"), ("delete", "post_deleted")])
async def test_hide_and_delete_run_the_module_s_apply_and_tell_the_author(
    site: Site, db: AsyncSession, action: str, done: str
) -> None:
    moderator, author = await _user(db, "editor"), await _user(db)
    case_id = await _reported(site, db, author)
    ident = (await _case(db, case_id)).target_id
    await moderation.act(db, case_id, action, actor=moderator, reason="spam", note="Ad")
    await db.commit()
    case = await _case(db, case_id)
    assert (case.status, case.outcome) == ("actioned", action)
    applied = await db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.action == f"{site.module}.{done}", AuditEvent.target_id == ident
        )
    )
    assert applied is not None
    past = "hidden" if action == "hide" else "deleted"
    assert await _entries(db, author.id) == [
        (f"kernel.moderation.{past}", {"case": str(case_id), "reason": "spam"})
    ]
    assert await site.mail(author.email) == ["Something you posted was removed"]
    page = await notifications.listed(db, author.id, cursor=None, limit=5)
    assert [item["title"] for item in page["items"]] == ["Something you posted was removed"]


async def test_a_failing_apply_leaves_the_case_open(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "editor")
    case_id = await _reported(site, db, await _user(db))
    site.store.fail = True
    try:
        with pytest.raises(RuntimeError):
            await moderation.act(db, case_id, "hide", actor=moderator, reason="spam")
        await db.rollback()
    finally:
        site.store.fail = False
    case = await _case(db, case_id)
    assert (case.status, case.outcome) == ("open", None)


async def test_an_action_the_kind_doesn_t_list_is_422(site: Site, db: AsyncSession) -> None:
    moderator, reporter, author = await _user(db, "editor"), await _user(db), await _user(db)
    ident = site.thing(author)
    case_id = await moderation.report(
        db, (site.profile, ident), reporter=reporter.id, reason="spam"
    )
    await db.commit()
    for action in ["hide", "delete", "mute"]:
        with pytest.raises(Problem) as refused:
            await moderation.act(db, case_id, action, actor=moderator, reason="spam")
        assert (refused.value.status, list(refused.value.errors)) == (422, ["action"])
    await moderation.act(db, case_id, "dismiss", actor=moderator)
    await db.commit()
    assert (await _case(db, case_id)).outcome == "dismiss"


async def test_hide_delete_time_out_and_ban_need_a_reason(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "admin")
    case_id = await _reported(site, db, await _user(db))
    for action in ["hide", "delete", "time_out", "ban"]:
        for reason in [None, "filter", "rude"]:
            with pytest.raises(Problem) as refused:
                await moderation.act(
                    db, case_id, action, actor=moderator, reason=reason, minutes=60
                )
            assert (refused.value.status, list(refused.value.errors)) == (422, ["reason"])


@pytest.mark.parametrize("minutes", [None, 59, 43_201, True])
async def test_a_time_out_is_60_minutes_to_30_days(
    site: Site, db: AsyncSession, minutes: Any
) -> None:
    moderator = await _user(db, "editor")
    case_id = await _reported(site, db, await _user(db))
    with pytest.raises(Problem) as refused:
        await moderation.act(
            db, case_id, "time_out", actor=moderator, reason="spam", minutes=minutes
        )
    assert (refused.value.status, list(refused.value.errors)) == (422, ["minutes"])


async def test_a_time_out_stops_posting_until_it_ends(site: Site, db: AsyncSession) -> None:
    moderator, author = await _user(db, "editor"), await _user(db)
    case_id = await _reported(site, db, author)
    before = clock.now()
    await moderation.act(db, case_id, "time_out", actor=moderator, reason="spam", minutes=60)
    await db.commit()
    until = (await _fresh(db, author.id)).timed_out_until
    assert until is not None
    assert before + timedelta(minutes=60) <= until <= clock.now() + timedelta(minutes=60)
    assert (await _case(db, case_id)).outcome == "time_out"
    assert await _entries(db, author.id) == [
        ("kernel.moderation.timed_out", {"case": str(case_id), "reason": "spam", "minutes": 60})
    ]
    assert await site.mail(author.email) == ["You can't post for a while"]
    async with Client(site.app) as client:
        headers = await _as(db, author)
        response = await client.post(f"/api/{site.module}/posts", headers=headers)
        assert (response.status_code, _code(response)) == (403, "kernel.timed_out")
        assert response.json()["until"] == until.isoformat()
        clock.advance(3600)
        response = await client.post(f"/api/{site.module}/posts", headers=headers)
        assert response.json() == {"by": str(author.id)}


async def test_a_ban_suspends_the_author_and_signs_them_out(
    site: Site, db: AsyncSession, heard: Heard
) -> None:
    admin, author = await _user(db, "admin"), await _user(db)
    case_id = await _reported(site, db, author)
    async with Client(site.app) as client:
        headers = await _as(db, author)
        assert (await client.get("/api/auth/activity", headers=headers)).status_code == 200
        await moderation.act(db, case_id, "ban", actor=admin, reason="hate")
        await db.commit()
        response = await client.get("/api/auth/activity", headers=headers)
        assert response.status_code == 401
    person = await _fresh(db, author.id)
    assert (person.status, person.session_epoch) == ("suspended", 1)
    assert (await _case(db, case_id)).outcome == "ban"
    assert ("auth.user.suspended", {"user_id": str(author.id)}) in await heard.drain()
    assert await _entries(db, author.id) == [
        ("auth.user.suspended", {"case": str(case_id), "reason": "hate"})
    ]
    assert await site.mail(author.email) == ["Your account is suspended"]


async def test_a_ban_needs_auth_user_suspend(site: Site, db: AsyncSession) -> None:
    editor = await _user(db, "editor")
    case_id = await _reported(site, db, await _user(db))
    with pytest.raises(Problem) as refused:
        await moderation.act(db, case_id, "ban", actor=editor, reason="spam")
    assert (refused.value.status, refused.value.code) == (403, "kernel.forbidden")


async def test_nobody_acts_on_their_own_case(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "admin")
    case_id = await _reported(site, db, moderator)
    for action in ["dismiss", "hide", "time_out", "ban"]:
        with pytest.raises(Problem) as refused:
            await moderation.act(db, case_id, action, actor=moderator, reason="spam", minutes=60)
        assert (refused.value.status, refused.value.code) == (403, "kernel.moderation_refused")


async def test_staff_aren_t_timed_out_or_banned_here(site: Site, db: AsyncSession) -> None:
    owner = await _user(db, "owner")
    for role in ["editor", "admin"]:
        case_id = await _reported(site, db, await _user(db, role))
        for action in ["time_out", "ban"]:
            with pytest.raises(Problem) as refused:
                await moderation.act(db, case_id, action, actor=owner, reason="spam", minutes=60)
            assert refused.value.code == "kernel.moderation_refused"


async def test_a_thing_with_no_author_has_no_one_to_time_out(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "admin")
    case_id = await _reported(site, db, None)
    with pytest.raises(Problem) as refused:
        await moderation.act(db, case_id, "time_out", actor=moderator, reason="spam", minutes=60)
    assert refused.value.code == "kernel.moderation_refused"
    await moderation.act(db, case_id, "hide", actor=moderator, reason="spam")
    await db.commit()
    assert (await _case(db, case_id)).outcome == "hide"


async def _custom_role(db: AsyncSession, permission: str) -> str:
    role_id = unique_id("role")
    db.add(Role(id=role_id, name=role_id))
    await db.flush()
    db.add(RolePermission(role_id=role_id, permission=permission))
    await db.commit()
    return role_id


async def test_hiding_staff_content_needs_every_permission_they_hold(
    site: Site, db: AsyncSession
) -> None:
    owner, admin, editor = (
        await _user(db, "owner"),
        await _user(db, "admin"),
        await _user(db, "editor"),
    )
    artist = await _custom_role(db, f"{site.module}.post.feature")
    cases = {
        "admin's": await _reported(site, db, await _user(db, "admin")),
        "owner's": await _reported(site, db, await _user(db, "owner")),
        "artist's": await _reported(site, db, await _user(db, artist)),
    }
    for actor, whose in [(editor, "admin's"), (admin, "owner's"), (admin, "artist's")]:
        with pytest.raises(Problem) as refused:
            await moderation.act(db, cases[whose], "hide", actor=actor, reason="spam")
        assert refused.value.code == "kernel.moderation_refused", whose
    await moderation.act(db, cases["admin's"], "hide", actor=admin, reason="spam")
    await moderation.act(db, cases["owner's"], "hide", actor=owner, reason="spam")
    await moderation.act(db, cases["artist's"], "delete", actor=owner, reason="spam")
    await db.commit()
    assert [(await _case(db, c)).status for c in cases.values()] == ["actioned"] * 3


async def test_a_closed_case_is_409_and_an_unknown_one_404(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "editor")
    case_id = await _reported(site, db, await _user(db))
    await moderation.act(db, case_id, "dismiss", actor=moderator)
    await db.commit()
    with pytest.raises(Problem) as refused:
        await moderation.act(db, case_id, "hide", actor=moderator, reason="spam")
    assert (refused.value.status, refused.value.code) == (409, "kernel.case_closed")
    with pytest.raises(Problem) as refused:
        await moderation.act(db, uuid.uuid4(), "dismiss", actor=moderator)
    assert (refused.value.status, refused.value.code) == (404, "kernel.not_found")


async def test_a_case_whose_module_is_off_is_404(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "editor")
    case_id = await _reported(site, db, await _user(db))
    with pytest.raises(Problem) as refused:
        await moderation.act(db, case_id, "dismiss", actor=moderator, on=frozenset())
    assert (refused.value.status, refused.value.code) == (404, "kernel.module_off")


# --- time-outs without a case, and suspension ------------------------------------------


async def test_a_time_out_without_a_case_and_lifting_it(site: Site, db: AsyncSession) -> None:
    moderator, member = await _user(db, "editor"), await _user(db)
    before = clock.now()
    await moderation.time_out(db, member.id, actor=moderator, minutes=120, reason="harassment")
    await db.commit()
    until = (await _fresh(db, member.id)).timed_out_until
    assert until is not None
    assert before + timedelta(hours=2) <= until <= clock.now() + timedelta(hours=2)
    await moderation.lift_time_out(db, member.id, actor=moderator)
    await moderation.lift_time_out(db, member.id, actor=moderator)  # nothing left to lift
    await db.commit()
    assert (await _fresh(db, member.id)).timed_out_until is None
    assert await _entries(db, member.id) == [
        ("kernel.moderation.timed_out", {"reason": "harassment", "minutes": 120}),
        ("kernel.moderation.time_out_lifted", {}),
    ]


async def test_nobody_times_themselves_out(site: Site, db: AsyncSession) -> None:
    moderator = await _user(db, "editor")
    with pytest.raises(Problem) as refused:
        await moderation.time_out(db, moderator.id, actor=moderator, minutes=60, reason="spam")
    assert (refused.value.status, refused.value.code) == (403, "kernel.moderation_refused")


@pytest.mark.parametrize("note", ["x" * 1001, "a" + chr(0)])
async def test_an_action_s_note_is_checked(site: Site, db: AsyncSession, note: str) -> None:
    moderator = await _user(db, "editor")
    case_id = await _reported(site, db, await _user(db))
    with pytest.raises(Problem) as refused:
        await moderation.act(db, case_id, "dismiss", actor=moderator, note=note)
    assert (refused.value.status, list(refused.value.errors)) == (422, ["note"])


async def test_a_time_out_that_ended_isn_t_lifted_again(site: Site, db: AsyncSession) -> None:
    moderator, member = await _user(db, "editor"), await _user(db)
    await moderation.time_out(db, member.id, actor=moderator, minutes=60, reason="spam")
    await db.commit()
    clock.advance(3601)
    await moderation.lift_time_out(db, member.id, actor=moderator)
    await db.commit()
    assert [action for action, _ in await _entries(db, member.id)] == [
        "kernel.moderation.timed_out"
    ]


async def test_suspending_and_restoring(site: Site, db: AsyncSession, heard: Heard) -> None:
    admin, member = await _user(db, "admin"), await _user(db)
    await moderation.suspend(db, member.id, actor=admin, reason="spam")
    await moderation.suspend(db, member.id, actor=admin, reason="spam")  # already: no change
    await db.commit()
    assert ((await _fresh(db, member.id)).status, (await _fresh(db, member.id)).session_epoch) == (
        "suspended",
        1,
    )
    await moderation.restore(db, member.id, actor=admin)
    await moderation.restore(db, member.id, actor=admin)  # already: no change
    await db.commit()
    person = await _fresh(db, member.id)
    assert (person.status, person.session_epoch) == ("active", 1)
    assert await _entries(db, member.id) == [
        ("auth.user.suspended", {"reason": "spam"}),
        ("auth.user.restored", {}),
    ]
    heard_now = await heard.drain()
    assert ("auth.user.suspended", {"user_id": str(member.id)}) in heard_now
    assert ("auth.user.restored", {"user_id": str(member.id)}) in heard_now


async def test_suspension_follows_who_may_act_on_whom(site: Site, db: AsyncSession) -> None:
    owner, other_owner, admin = (
        await _user(db, "owner"),
        await _user(db, "owner"),
        await _user(db, "admin"),
    )
    artist = await _user(db, await _custom_role(db, f"{site.module}.post.feature"))
    refused_cases = [
        (admin, admin, "auth.not_yourself"),
        (owner, owner, "auth.not_yourself"),  # so never the last owner
        (admin, other_owner, "auth.role_not_yours"),  # only an owner suspends an owner
        (admin, artist, "auth.role_not_yours"),  # a permission the admin doesn't hold
    ]
    for actor, target, code in refused_cases:
        with pytest.raises(Problem) as refused:
            await moderation.suspend(db, target.id, actor=actor, reason="spam")
        assert (refused.value.status, refused.value.code) == (403, code)
        with pytest.raises(Problem) as refused:
            await moderation.restore(db, target.id, actor=actor)
        assert (refused.value.status, refused.value.code) == (403, code)
    await moderation.suspend(db, other_owner.id, actor=owner, reason="other")
    await moderation.suspend(db, artist.id, actor=owner, reason="other")
    await db.commit()
    assert (await _fresh(db, other_owner.id)).status == "suspended"


async def test_a_members_permission_doesn_t_stop_an_admin(site: Site, db: AsyncSession) -> None:
    """What every member holds is no rank (decision 0013's rule leaves `member` out)."""
    permission = f"{site.module}.post.create"
    db.add(RolePermission(role_id="member", permission=permission))
    await db.commit()
    try:
        admin, member = await _user(db, "admin"), await _user(db)
        await moderation.suspend(db, member.id, actor=admin, reason="spam")
        await db.commit()
        assert (await _fresh(db, member.id)).status == "suspended"
    finally:
        await db.delete(await db.get(RolePermission, ("member", permission)))
        await db.commit()


async def _until_blocked(database: Database, task: asyncio.Task[Any]) -> None:
    """Waits until `task` waits on a row lock (or ends): the race is real."""
    for _ in range(200):
        if task.done():
            return
        async with database.sessions() as probe:
            waiting = await probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            )
        if waiting:
            return
        await asyncio.sleep(0.025)


async def test_two_owners_can_t_suspend_each_other_at_once(
    site: Site, db: AsyncSession, database: Database
) -> None:
    """CodeRabbit on #71: each locked only its target, so both could commit and
    leave no active owner. The actor's row is locked too, and must be active."""
    ana_id, ben_id = (await _user(db, "owner")).id, (await _user(db, "owner")).id
    async with database.sessions() as first, database.sessions() as second:
        ana = await first.get(User, ana_id)
        ben = await second.get(User, ben_id)
        assert ana is not None
        assert ben is not None
        await second.commit()  # its next statement waits on the lock, not on this read
        await moderation.suspend(first, ben_id, actor=ana, reason="other")
        second_try = asyncio.create_task(
            moderation.suspend(second, ana_id, actor=ben, reason="other")
        )
        await _until_blocked(database, second_try)
        await first.commit()
        with pytest.raises(Problem) as refused:
            await second_try
        assert (refused.value.status, refused.value.code) == (409, "auth.account_not_active")
        await second.rollback()
    statuses = ((await _fresh(db, ana_id)).status, (await _fresh(db, ben_id)).status)
    assert statuses == ("active", "suspended")


async def test_a_suspended_actor_can_t_suspend_or_restore(site: Site, db: AsyncSession) -> None:
    owner, admin, member = await _user(db, "owner"), await _user(db, "admin"), await _user(db)
    admin_id, member_id = admin.id, member.id
    await moderation.suspend(db, admin_id, actor=owner, reason="other")
    await db.commit()
    with pytest.raises(Problem) as refused:
        await moderation.suspend(db, member_id, actor=admin, reason="spam")
    assert (refused.value.status, refused.value.code) == (409, "auth.account_not_active")
    await db.rollback()
    admin = await _fresh(db, admin_id)
    with pytest.raises(Problem) as refused:
        await moderation.restore(db, member_id, actor=admin)
    assert (refused.value.status, refused.value.code) == (409, "auth.account_not_active")
    await db.rollback()


async def test_suspending_someone_leaving_or_gone_is_409(site: Site, db: AsyncSession) -> None:
    admin = await _user(db, "admin")
    leaving = await _user(db)
    leaving.status = "deleting"
    await db.commit()
    with pytest.raises(Problem) as refused:
        await moderation.suspend(db, leaving.id, actor=admin, reason="spam")
    assert (refused.value.status, refused.value.code) == (409, "auth.account_not_active")
    with pytest.raises(Problem) as refused:
        await moderation.restore(db, leaving.id, actor=admin)
    assert (refused.value.status, refused.value.code) == (409, "auth.account_not_active")
    with pytest.raises(Problem) as refused:
        await moderation.suspend(db, uuid.uuid4(), actor=admin, reason="spam")
    assert (refused.value.status, refused.value.code) == (404, "kernel.not_found")


# --- the routes ---------------------------------------------------------------------

REPORTS = "/api/kernel/moderation/reports"
CASES = "/api/kernel/admin/moderation/cases"
LOG = "/api/kernel/admin/moderation/log"


def _people(user_id: uuid.UUID) -> str:
    return f"/api/kernel/admin/moderation/people/{user_id}/time-out"


def _suspend(user_id: uuid.UUID) -> str:
    return f"/api/auth/admin/users/{user_id}/suspend"


def _restore(user_id: uuid.UUID) -> str:
    return f"/api/auth/admin/users/{user_id}/restore"


async def test_reporting_needs_a_verified_signed_in_person(site: Site, db: AsyncSession) -> None:
    unverified, member = await _user(db, verified=False), await _user(db)
    body = {"target": {"type": site.post, "id": site.thing(None)}, "reason": "spam"}
    async with Client(site.app) as client:
        response = await client.post(REPORTS, json=body)
        assert (response.status_code, _code(response)) == (401, "kernel.not_signed_in")
        response = await client.post(REPORTS, json=body, headers=await _as(db, unverified))
        assert (response.status_code, _code(response)) == (403, "auth.email_unverified")
        headers = await _as(db, member)
        for _ in range(2):  # the same answer for a first report and a repeat
            response = await client.post(REPORTS, json={**body, "note": "Ads"}, headers=headers)
            assert (response.status_code, response.json()) == (202, {})
    [case] = await _cases(db, site.post, body["target"]["id"])  # type: ignore[index]
    assert case.report_count == 1


async def test_a_report_on_nothing_or_a_module_off_is_404(site: Site, db: AsyncSession) -> None:
    member = await _user(db)
    async with Client(site.app) as client:
        headers = await _as(db, member)
        for target in [{"type": site.post, "id": "gone"}, {"type": "blog.post", "id": "1"}]:
            response = await client.post(
                REPORTS, json={"target": target, "reason": "spam"}, headers=headers
            )
            assert (response.status_code, _code(response)) == (404, "kernel.report_target_unknown")
        db.add(ModuleState(module_id=site.module, enabled=False))
        await db.commit()
        try:
            target = {"type": site.post, "id": site.thing(None)}
            response = await client.post(
                REPORTS, json={"target": target, "reason": "spam"}, headers=headers
            )
            assert (response.status_code, _code(response)) == (404, "kernel.report_target_unknown")
        finally:
            await db.delete(await db.get(ModuleState, site.module))
            await db.commit()


@pytest.mark.parametrize(
    "body",
    [
        {"target": {"type": "x.post", "id": 4}, "reason": "spam"},
        {"target": {"type": "x.post", "id": "4"}, "reason": "rude"},
        {"target": {"type": "x.post", "id": "4"}, "reason": "spam", "extra": 1},
        {"target": {"type": "x.post", "id": "4"}, "reason": "spam", "note": "x" * 1001},
        {"target": {"type": "x.post", "id": ""}, "reason": "spam"},
        {"reason": "spam"},
    ],
)
async def test_a_bad_report_is_422(site: Site, db: AsyncSession, body: dict[str, Any]) -> None:
    member = await _user(db)
    async with Client(site.app) as client:
        response = await client.post(REPORTS, json=body, headers=await _as(db, member))
        assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")


@pytest.mark.parametrize("part", ["id", "note"])
async def test_a_nul_character_in_a_report_is_422_not_500(
    site: Site, db: AsyncSession, part: str
) -> None:
    """Codex on #71: the models took it and the service's ValueError became a 500."""
    member = await _user(db)
    body: dict[str, Any] = {"target": {"type": site.post, "id": site.thing(None)}, "reason": "spam"}
    if part == "id":
        body["target"]["id"] += chr(0)
    else:
        body["note"] = "Ads" + chr(0)
    async with Client(site.app) as client:
        response = await client.post(REPORTS, json=body, headers=await _as(db, member))
        assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")


async def test_reports_are_limited_to_20_an_hour(site: Site, db: AsyncSession) -> None:
    member = await _user(db)
    async with Client(site.app) as client:
        headers = await _as(db, member)
        for n in range(21):
            body = {"target": {"type": site.post, "id": site.thing(None)}, "reason": "spam"}
            response = await client.post(REPORTS, json=body, headers=headers)
            assert response.status_code == (202 if n < 20 else 429), n


async def test_the_queue_needs_moderation_act_and_a_second_factor(
    site: Site, db: AsyncSession
) -> None:
    member, bare = await _user(db), await _user(db, "editor")
    editor = await _user(db, "editor", second_factor=True)
    async with Client(site.app) as client:
        for path in [CASES, LOG, f"{CASES}/{uuid.uuid4()}"]:
            response = await client.get(path)
            assert (response.status_code, _code(response)) == (401, "kernel.not_signed_in")
            response = await client.get(path, headers=await _as(db, member))
            assert (response.status_code, _code(response)) == (403, "kernel.forbidden")
            response = await client.get(path, headers=await _as(db, bare))
            assert _code(response) == "auth.second_factor_required"
        response = await client.get(CASES, headers=await _as(db, editor))
        assert response.status_code == 200


async def test_the_queue_lists_the_latest_report_first_in_pages(
    site: Site, db: AsyncSession
) -> None:
    editor = await _user(db, "editor", second_factor=True)
    made = []
    for _ in range(3):
        made.append(await _reported(site, db, await _user(db)))
        clock.advance(1)
    async with Client(site.app) as client:
        headers = await _as(db, editor)
        seen: list[str] = []
        cursor: str | None = None
        while True:
            query = {"kind": site.post, "limit": "2", **({"cursor": cursor} if cursor else {})}
            page = (await client.get(CASES, params=query, headers=headers)).json()
            seen += [item["id"] for item in page["items"] if uuid.UUID(item["id"]) in made]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert seen == [str(case_id) for case_id in reversed(made)]


async def test_the_queue_filters_by_status_kind_and_source(site: Site, db: AsyncSession) -> None:
    editor = await _user(db, "editor", second_factor=True)
    reported = await _reported(site, db, await _user(db))
    held = await moderation.hold(db, (site.post, site.thing(None)), reasons=("links",))
    closed = await _reported(site, db, await _user(db))
    await moderation.act(db, closed, "dismiss", actor=editor)
    await db.commit()
    async with Client(site.app) as client:
        headers = await _as(db, editor)

        async def ids(**query: str) -> set[uuid.UUID]:
            response = await client.get(CASES, params={"limit": "100", **query}, headers=headers)
            assert response.status_code == 200, response.text
            return {uuid.UUID(item["id"]) for item in response.json()["items"]}

        mine = {reported, held, closed}
        assert await ids(kind=site.post) & mine == {reported, held}
        assert await ids(kind=site.post, source="filter") & mine == {held}
        assert await ids(kind=site.post, status="dismissed") & mine == {closed}
        assert await ids(kind=site.profile) & mine == set()
        for bad in [{"status": "gone"}, {"source": "x"}, {"kind": "Nope"}, {"cursor": "zz"}]:
            response = await client.get(CASES, params=bad, headers=headers)
            assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")


async def test_a_case_shows_its_reports_and_takes_actions(site: Site, db: AsyncSession) -> None:
    editor = await _user(db, "editor", second_factor=True)
    author, reporter = await _user(db), await _user(db)
    ident = site.thing(author, "Buy now")
    case_id = await moderation.report(
        db, (site.post, ident), reporter=reporter.id, reason="spam", note="An ad"
    )
    await db.commit()
    async with Client(site.app) as client:
        headers = await _as(db, editor)
        case = (await client.get(f"{CASES}/{case_id}", headers=headers)).json()
        assert {
            key: case[key] for key in ("target", "status", "source", "author_id", "excerpt")
        } == {
            "target": {"type": site.post, "id": ident},
            "status": "open",
            "source": "report",
            "author_id": str(author.id),
            "excerpt": "Buy now",
        }
        assert (case["link"], case["report_count"], case["reasons"]) == (
            f"/talk/{ident}",
            1,
            {"spam": 1},
        )
        assert [(r["reporter_id"], r["reason"], r["note"]) for r in case["reports"]] == [
            (str(reporter.id), "spam", "An ad")
        ]
        response = await client.post(
            f"{CASES}/{case_id}/actions",
            json={"action": "hide", "reason": "spam"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert (response.json()["status"], response.json()["outcome"]) == ("actioned", "hide")
        assert response.json()["closed_by"] == str(editor.id)
        response = await client.post(
            f"{CASES}/{case_id}/actions", json={"action": "hide", "reason": "spam"}, headers=headers
        )
        assert (response.status_code, _code(response)) == (409, "kernel.case_closed")
        response = await client.post(
            f"{CASES}/{case_id}/actions", json={"action": 3}, headers=headers
        )
        assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")
        response = await client.get(f"{CASES}/{uuid.uuid4()}", headers=headers)
        assert (response.status_code, _code(response)) == (404, "kernel.not_found")


async def test_acting_on_a_case_whose_module_is_off_is_404(site: Site, db: AsyncSession) -> None:
    editor = await _user(db, "editor", second_factor=True)
    case_id = await _reported(site, db, await _user(db))
    db.add(ModuleState(module_id=site.module, enabled=False))
    await db.commit()
    try:
        async with Client(site.app) as client:
            response = await client.post(
                f"{CASES}/{case_id}/actions",
                json={"action": "dismiss"},
                headers=await _as(db, editor),
            )
            assert (response.status_code, _code(response)) == (404, "kernel.module_off")
    finally:
        await db.delete(await db.get(ModuleState, site.module))
        await db.commit()


async def test_a_ban_from_the_queue_needs_a_recent_sign_in(site: Site, db: AsyncSession) -> None:
    """CodeRabbit on #71: a ban suspends, and suspending needs step-up (14.7)."""
    admin = await _user(db, "admin", second_factor=True)
    banned = await _reported(site, db, await _user(db))
    kept = await _reported(site, db, await _user(db))
    async with Client(site.app) as client:
        headers = await _as(db, admin)
        clock.advance(11 * 60)
        response = await client.post(
            f"{CASES}/{banned}/actions", json={"action": "ban", "reason": "spam"}, headers=headers
        )
        assert (response.status_code, _code(response)) == (403, "auth.step_up_required")
        response = await client.post(
            f"{CASES}/{kept}/actions", json={"action": "dismiss"}, headers=headers
        )
        assert response.status_code == 200, response.text
        response = await client.post(
            f"{CASES}/{banned}/actions",
            json={"action": "ban", "reason": "spam"},
            headers=await _as(db, admin),
        )
        assert (response.status_code, response.json()["outcome"]) == (200, "ban")


async def test_time_out_routes(site: Site, db: AsyncSession) -> None:
    editor = await _user(db, "editor", second_factor=True)
    member = await _user(db)
    async with Client(site.app) as client:
        headers = await _as(db, editor)
        response = await client.put(
            _people(member.id), json={"minutes": 90, "reason": "spam"}, headers=headers
        )
        until = (await _fresh(db, member.id)).timed_out_until
        assert until is not None
        assert (response.status_code, response.json()) == (200, {"until": until.isoformat()})
        response = await client.put(_people(member.id), json={"minutes": 30}, headers=headers)
        assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")
        response = await client.put(
            _people(uuid.uuid4()), json={"minutes": 90, "reason": "spam"}, headers=headers
        )
        assert (response.status_code, _code(response)) == (404, "kernel.not_found")
        response = await client.delete(_people(member.id), headers=headers)
        assert response.status_code == 204
    assert (await _fresh(db, member.id)).timed_out_until is None


async def test_suspension_routes_need_auth_user_suspend_and_step_up(
    site: Site, db: AsyncSession
) -> None:
    editor = await _user(db, "editor", second_factor=True)
    admin = await _user(db, "admin", second_factor=True)
    member = await _user(db)
    async with Client(site.app) as client:
        response = await client.post(
            _suspend(member.id), json={"reason": "spam"}, headers=await _as(db, editor)
        )
        assert (response.status_code, _code(response)) == (403, "kernel.forbidden")
        headers = await _as(db, admin)
        clock.advance(11 * 60)
        response = await client.post(_suspend(member.id), json={"reason": "spam"}, headers=headers)
        assert (response.status_code, _code(response)) == (403, "auth.step_up_required")
        headers = await _as(db, admin)
        response = await client.post(_suspend(member.id), json={"reason": "x"}, headers=headers)
        assert (response.status_code, _code(response)) == (422, "kernel.invalid_request")
        response = await client.post(_suspend(member.id), json={"reason": "spam"}, headers=headers)
        assert (response.status_code, response.json()) == (200, {"status": "suspended"})
        response = await client.post(_restore(member.id), headers=headers)
        assert (response.status_code, response.json()) == (200, {"status": "active"})


async def test_the_moderators_log_shows_moderation_and_suspensions_only(
    site: Site, db: AsyncSession
) -> None:
    editor = await _user(db, "editor", second_factor=True)
    admin, member = await _user(db, "admin"), await _user(db)
    await moderation.time_out(db, member.id, actor=editor, minutes=60, reason="spam")
    await moderation.suspend(db, member.id, actor=admin, reason="spam")
    audit.record(db, "kernel.settings_saved", actor=admin.id, subject=member.id)
    await db.commit()
    async with Client(site.app) as client:
        response = await client.get(
            LOG, params={"subject": str(member.id)}, headers=await _as(db, editor)
        )
        assert response.status_code == 200, response.text
        items = response.json()["items"]
    assert [item["action"] for item in items] == [
        "auth.user.suspended",
        "kernel.moderation.timed_out",
    ]
    assert all("ip" not in item and "user_agent" not in item for item in items)


# --- the kernel's notice, mails and pruning ----------------------------------------------


async def test_the_removal_notice_is_the_kernel_s_and_can_be_chosen(
    site: Site, db: AsyncSession
) -> None:
    member = await _user(db)
    async with Client(site.app) as client:
        headers = await _as(db, member)
        listed = (await client.get("/api/kernel/notifications/preferences", headers=headers)).json()
        keys = [item["key"] for item in listed["items"]]
        assert "kernel.content_removed" in keys
        response = await client.put(
            "/api/kernel/notifications/preferences",
            json={"kernel.content_removed": {"in_site": True, "email": False}},
            headers=headers,
        )
        assert response.status_code == 200


async def test_pruning_removes_only_cases_closed_past_the_keep(
    site: Site, db: AsyncSession, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    editor = await _user(db, "editor")
    old = [await _reported(site, db, await _user(db)) for _ in range(5)]
    for case_id in old:
        await moderation.act(db, case_id, "dismiss", actor=editor)
    still_open = await _reported(site, db, await _user(db))
    await db.commit()
    clock.advance(366 * 86400)
    recent = await _reported(site, db, await _user(db))
    await moderation.act(db, recent, "dismiss", actor=editor)
    await db.commit()
    monkeypatch.setattr(moderation, "BATCH", 2)
    context = jobs.Context(
        job_id=uuid.uuid4(),
        name="kernel.prune_moderation",
        try_number=1,
        _database=database,
        _mailer=LogMailer(),
    )
    await moderation.PRUNE.run(context, {})
    remaining = await db.scalars(
        select(ModerationCase.id).where(ModerationCase.id.in_([*old, still_open, recent]))
    )
    assert set(remaining) == {still_open, recent}
    assert (
        await db.scalar(select(ModerationReport.id).where(ModerationReport.case_id.in_(old)))
        is None
    )


def test_pruning_is_one_of_the_kernel_s_daily_jobs(site: Site) -> None:
    assert "kernel.prune_moderation" in site.app.state.worker.names
    assert moderation.PRUNE.schedule is not None

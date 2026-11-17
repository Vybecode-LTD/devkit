"""Password change (SPEC.md 14.4, 14.5 and 14.6; docs/contracts/auth-api.md;
decision 0025): what the contract suite can't see from outside, such as the
device cookie, the audit, what a change ends, races and lock order."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.app import create_app
from kernel.auth import sessions
from kernel.auth.accounts import normal_email
from kernel.auth.models import AuditEvent, Session, Token, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, Draining, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
NEW = "amber walrus cello 5528 dune"
OTHER = "copper heron valley 2093 tide"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


@dataclass
class Site:
    app: FastAPI
    http: httpx.AsyncClient
    mail: CapturingMailer
    breached: set[str] = field(default_factory=set)
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        transport = Draining(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    holder: list[Site] = []

    async def lookup(prefix: str) -> str | None:
        """Have I Been Pwned's range answer, for the passwords the site lists."""
        lines = []
        for password in holder[0].breached:
            digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
            if digest.startswith(prefix):
                lines.append(f"{digest[5:]}:3")
        return "\r\n".join(lines)

    mail = CapturingMailer()
    app = create_app(
        config=make_config(database_url=migrated_url), mailer=mail, breach_lookup=lookup
    )
    async with Client(app) as http:
        http.headers.update(_SAME_ORIGIN)
        made = Site(app, http, mail)
        holder.append(made)
        async with made.db() as db:
            made.audit_from = await db.scalar(select(func.max(AuditEvent.id))) or 0
        yield made


@dataclass
class Person:
    id: uuid.UUID
    email: str
    browser: httpx.AsyncClient


async def _person(site: Site, *, password: str | None = PASSWORD) -> Person:
    """A verified member, signed in a moment ago on a browser of their own
    (with a password; without one, the session is made directly)."""
    email = f"Lou.{uuid.uuid4().hex[:10]}@Site.test"
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            password_hash=await site.app.state.passwords.hash(PASSWORD),
            email_verified_at=clock.now(),
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id="member"))
        await db.commit()
    browser = site.browser()
    signed = await _sign_in(browser, email, PASSWORD)
    assert signed.json()["status"] == "signed_in", signed.text
    if password is None:
        async with site.db() as db:
            await db.execute(update(User).where(User.id == user.id).values(password_hash=None))
            await db.commit()
    return Person(user.id, email, browser)


async def _sign_in(http: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await http.post("/api/auth/sign-in", json={"email": email, "password": password})


async def _change(
    http: httpx.AsyncClient, current: str = PASSWORD, new: str = NEW
) -> httpx.Response:
    return await http.post(
        "/api/auth/password/change", json={"current_password": current, "new_password": new}
    )


def _cookie(response: httpx.Response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


async def _hash(site: Site, person: Person) -> str | None:
    async with site.db() as db:
        user = await db.get(User, person.id)
        assert user is not None
        return user.password_hash


# --- changing -------------------------------------------------------------------


async def test_a_change_keeps_this_session_and_ends_every_other(site: Site) -> None:
    person = await _person(site)
    other = site.browser()
    assert (await _sign_in(other, person.email, PASSWORD)).status_code == 200
    changed = await _change(person.browser)
    assert (changed.status_code, changed.json()) == (200, {"status": "password_changed"})
    assert (await person.browser.get("/api/auth/session")).status_code == 200
    assert (await other.get("/api/auth/session")).status_code == 401
    assert (await _sign_in(site.browser(), person.email, PASSWORD)).status_code == 401
    assert (await _sign_in(site.browser(), person.email, NEW)).status_code == 200


async def test_this_browser_gets_a_fresh_device_cookie_that_still_works(site: Site) -> None:
    """The device cookie is signed over the epoch the change raises: without
    a fresh one, this browser would be a stranger over the failure limit."""
    person = await _person(site)
    changed = await _change(person.browser)
    fresh = _cookie(changed, "__Host-dk_device")
    assert fresh
    for _ in range(5):  # strangers push the address over its failure limit
        await _sign_in(site.browser(), person.email, "a wrong password 1")
    assert (await _sign_in(site.browser(), person.email, NEW)).status_code == 429  # the control
    assert (await _sign_in(person.browser, person.email, NEW)).status_code == 200


async def test_a_wrong_current_password_is_refused_and_counts_as_a_failed_step_up(
    site: Site,
) -> None:
    person = await _person(site)
    for _ in range(4):
        refused = await _change(person.browser, current=OTHER)
        assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_credentials")
        assert (await person.browser.get("/api/auth/session")).status_code == 200
    fifth = await _change(person.browser, current=OTHER)
    assert (fifth.status_code, fifth.json()["code"]) == (401, "kernel.not_signed_in")
    assert (await person.browser.get("/api/auth/session")).status_code == 401
    assert (await _sign_in(site.browser(), person.email, PASSWORD)).status_code == 200


@pytest.mark.parametrize("new", ["too short", OTHER])
async def test_a_refused_new_password_changes_nothing(site: Site, new: str) -> None:
    site.breached.add(OTHER)
    person = await _person(site)
    other = site.browser()
    assert (await _sign_in(other, person.email, PASSWORD)).status_code == 200
    before = await _hash(site, person)
    refused = await _change(person.browser, new=new)
    assert (refused.status_code, refused.json()["code"]) == (422, "auth.password_rejected")
    assert refused.json()["detail"]
    assert await _hash(site, person) == before
    assert (await other.get("/api/auth/session")).status_code == 200


async def test_an_account_without_a_password_is_refused(site: Site) -> None:
    person = await _person(site, password=None)
    refused = await _change(person.browser)
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_credentials")
    assert await _hash(site, person) is None


async def test_a_change_voids_every_live_way_in(site: Site) -> None:
    person = await _person(site)
    await site.http.post("/api/auth/code", json={"email": person.email})
    await site.http.post("/api/auth/password/reset-request", json={"email": person.email})
    await _change(person.browser)
    async with site.db() as db:
        rows = list(
            await db.scalars(
                select(Token).where(
                    Token.user_id == person.id,
                    Token.purpose.in_(("sign_in_code", "magic_link", "reset_password")),
                )
            )
        )
    assert len(rows) == 3
    assert all(r.used_at is not None for r in rows)


async def test_a_pending_email_change_dies_with_it(site: Site) -> None:
    """Bound to the session epoch the change raises (decision 0024)."""
    person = await _person(site)
    new = f"moved.{uuid.uuid4().hex[:8]}@site.test"
    await person.browser.post("/api/auth/email/change", json={"email": new})
    [message] = site.mail.to(new)
    link = next(w for w in message.text.split() if "/auth/email?" in w)
    token = parse_qs(urlsplit(link).query)["token"][0]
    await _change(person.browser)
    refused = await site.browser().post("/api/auth/email/confirm", json={"token": token})
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


async def test_a_security_mail_follows(site: Site) -> None:
    person = await _person(site)
    before = len(site.mail.to(person.email))
    await _change(person.browser)
    [notice] = site.mail.to(person.email)[before:]
    assert "password" in notice.subject.lower()
    assert NEW not in notice.text


async def test_a_change_is_audited_without_the_password(site: Site) -> None:
    person = await _person(site)
    await _change(person.browser)
    [event] = await _audit(site, "auth.password_changed")
    assert (event.result, event.actor_id, event.subject_id) == ("success", person.id, person.id)
    assert NEW not in repr(event.details)
    assert PASSWORD not in repr(event.details)


async def test_a_failing_mailer_doesnt_fail_the_change(site: Site) -> None:
    class Broken:
        async def send(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("the mail host is down")

    person = await _person(site)
    site.app.state.mailer.inner = Broken()
    assert (await _change(person.browser)).status_code == 200


# --- races and lock order -------------------------------------------------------


async def test_a_reset_landing_mid_change_wins(site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    """The change has checked the current password and is hashing the new
    one when a reset lands. The reset ended this session, so the change is
    refused and the reset's password stands."""
    person = await _person(site)
    passwords = site.app.state.passwords
    real_hash = passwords.hash
    hashing, go_on = asyncio.Event(), asyncio.Event()

    async def held(password: str) -> str:
        if password == NEW:  # the change's hash of its new password
            hashing.set()
            await go_on.wait()
        hashed: str = await real_hash(password)
        return hashed

    monkeypatch.setattr(passwords, "hash", held)
    changing = asyncio.create_task(_change(person.browser))
    await asyncio.wait_for(hashing.wait(), 10)
    await site.http.post("/api/auth/password/reset-request", json={"email": person.email})
    reset_text = next(m.text for m in site.mail.to(person.email) if "/auth/reset?" in m.text)
    link = next(w for w in reset_text.split() if "/auth/reset?" in w)
    token = parse_qs(urlsplit(link).query)["token"][0]
    reset = await site.http.post(
        "/api/auth/password/reset", json={"token": token, "password": OTHER}
    )
    assert reset.status_code == 200
    go_on.set()
    late = await changing
    assert late.status_code == 401
    assert (await _sign_in(site.browser(), person.email, NEW)).status_code == 401
    assert (await _sign_in(site.browser(), person.email, OTHER)).status_code == 200


async def test_a_change_locks_the_account_before_the_other_sessions(site: Site) -> None:
    """A reset ends every session with the account locked; a change that
    deleted the other sessions first, then waited for the account, would
    deadlock with it."""
    person = await _person(site)
    other = site.browser()
    assert (await _sign_in(other, person.email, PASSWORD)).status_code == 200
    async with site.db() as db:
        others = list(await db.scalars(select(Session.id).where(Session.user_id == person.id)))
    assert len(others) == 2
    async with site.db() as holder, site.db() as watcher:
        await holder.execute(select(User.id).where(User.id == person.id).with_for_update())
        changing = asyncio.create_task(_change(person.browser))
        try:
            blocked = False
            for _ in range(250):
                await asyncio.sleep(0.02)
                blocked = bool(
                    await watcher.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity"
                            " WHERE wait_event_type = 'Lock' AND datname = current_database()"
                        )
                    )
                )
                await watcher.rollback()
                if blocked:
                    break
            assert blocked, "the change never waited for the account row"
            for session_id in others:
                free = await watcher.scalar(
                    text("SELECT id FROM auth_session WHERE id = :id FOR UPDATE NOWAIT"),
                    {"id": session_id},
                )
                assert free == session_id
                await watcher.rollback()
        finally:
            await watcher.rollback()
            await holder.rollback()
            answer = await changing
    assert answer.status_code == 200


async def test_a_reset_arriving_after_the_second_look_waits_for_the_change(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past its second look, the change holds the account until it commits:
    a reset arriving then waits, and finds its link voided by the change
    (400). Paused just there, a change without that lock would let the reset
    commit first (200), then write the new password over the reset's, so the
    owner's reset would seem to work and not."""
    person = await _person(site)
    await site.http.post("/api/auth/password/reset-request", json={"email": person.email})
    reset_text = next(m.text for m in site.mail.to(person.email) if "/auth/reset?" in m.text)
    link = next(w for w in reset_text.split() if "/auth/reset?" in w)
    token = parse_qs(urlsplit(link).query)["token"][0]
    real_end = sessions.end_all_but
    paused, go_on = asyncio.Event(), asyncio.Event()

    async def held(db: AsyncSession, user: User, keep: Session) -> None:
        paused.set()  # the change, just past its second look
        await go_on.wait()
        await real_end(db, user, keep)

    monkeypatch.setattr(sessions, "end_all_but", held)
    changing = asyncio.create_task(_change(person.browser))
    await asyncio.wait_for(paused.wait(), 10)
    resetting = asyncio.create_task(
        site.http.post("/api/auth/password/reset", json={"token": token, "password": OTHER})
    )
    await asyncio.wait({resetting}, timeout=1.0)  # done only if nothing held it back
    go_on.set()
    assert (await changing).status_code == 200
    reset = await resetting
    assert (reset.status_code, reset.json()["code"]) == (400, "auth.token_invalid")
    assert (await _sign_in(site.browser(), person.email, NEW)).status_code == 200


async def test_an_undo_landing_mid_change_ends_it(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An email undo ends every session without touching the password; the
    change, waiting on its hash meanwhile, finds its session gone and stops."""
    person = await _person(site)
    new = f"moved.{uuid.uuid4().hex[:8]}@site.test"
    await person.browser.post("/api/auth/email/change", json={"email": new})
    link = next(w for w in site.mail.to(new)[-1].text.split() if "/auth/email?" in w)
    await site.browser().post(
        "/api/auth/email/confirm", json={"token": parse_qs(urlsplit(link).query)["token"][0]}
    )
    undo_text = site.mail.to(person.email)[-1].text
    undo_link = next(w for w in undo_text.split() if "/auth/email/undo?" in w)
    undo = parse_qs(urlsplit(undo_link).query)["token"][0]
    before = await _hash(site, person)
    passwords = site.app.state.passwords
    real_hash = passwords.hash
    hashing, go_on = asyncio.Event(), asyncio.Event()

    async def held(password: str) -> str:
        if password == NEW:
            hashing.set()
            await go_on.wait()
        hashed: str = await real_hash(password)
        return hashed

    monkeypatch.setattr(passwords, "hash", held)
    changing = asyncio.create_task(_change(person.browser))
    await asyncio.wait_for(hashing.wait(), 10)
    assert (
        await site.browser().post("/api/auth/email/undo", json={"token": undo})
    ).status_code == 200
    go_on.set()
    late = await changing
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert await _hash(site, person) == before


async def test_two_changes_from_one_session_at_once_change_it_once(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both check the old password, then wait for each other before hashing.
    The first to commit moves this session to the new epoch with it, so a
    session check alone would let the second through with a current password
    no longer current (Codex on #46). The epoch seen at the check refuses it."""
    person = await _person(site)
    passwords = site.app.state.passwords
    real_hash = passwords.hash
    arrived: list[str] = []
    both = asyncio.Event()

    async def held(password: str) -> str:
        if password in (NEW, OTHER):
            arrived.append(password)
            if len(arrived) == 2:
                both.set()
            await both.wait()
        hashed: str = await real_hash(password)
        return hashed

    monkeypatch.setattr(passwords, "hash", held)
    first, second = await asyncio.gather(
        _change(person.browser, new=NEW), _change(person.browser, new=OTHER)
    )
    assert sorted([first.status_code, second.status_code]) == [200, 401]
    winner, loser = (NEW, OTHER) if first.status_code == 200 else (OTHER, NEW)
    refused = second if first.status_code == 200 else first
    assert refused.json()["code"] == "auth.invalid_credentials"
    assert (await _sign_in(site.browser(), person.email, loser)).status_code == 401
    assert (await _sign_in(site.browser(), person.email, winner)).status_code == 200

"""Undoing a second factor from its mail (SPEC.md 14.7; decision 0030): what
the contract suite can't see from outside, such as the link at rest, the
binding to its factor, the audit, the notice, what is voided, and lock order.
The contract suite covers passkeys; these tests use a TOTP."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta

import httpx
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.app import create_app
from kernel.auth.accounts import normal_email
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import AuditEvent, RecoveryCode, Token, Totp, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, Draining, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
UNDO = "/api/auth/second-factor/undo"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
_LINK = re.compile(r"/auth/second-factor/undo\?token=([A-Za-z0-9_-]{43})")
_TOKEN_ROW_FREE = "SELECT id FROM auth_token WHERE id = :id FOR UPDATE NOWAIT"
_ENDED = ("sign_in_code", "magic_link", "reset_password", "second_factor")


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


@dataclass
class Site:
    app: FastAPI
    mail: CapturingMailer
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        transport = Draining(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    mail = CapturingMailer()
    app = create_app(config=make_config(database_url=migrated_url), mailer=mail)
    async with Client(app):  # runs the app's start-up and shut-down
        made = Site(app, mail)
        async with made.db() as db:
            made.audit_from = await db.scalar(select(func.max(AuditEvent.id))) or 0
        yield made


@dataclass
class Person:
    id: uuid.UUID
    email: str
    browser: httpx.AsyncClient


async def _person(site: Site) -> Person:
    """A verified member, signed in a moment ago on a browser of their own."""
    email = f"Ola.{uuid.uuid4().hex[:10]}@Site.test"
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
    signed = await browser.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert signed.json()["status"] == "signed_in", signed.text
    return Person(user.id, email, browser)


async def _add_totp(site: Site, person: Person) -> str:
    """Set up and confirm a TOTP over HTTP: the undo link its mail carries."""
    before = len(site.mail.to(person.email))
    setup = await person.browser.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    code = pyotp.TOTP(setup.json()["secret"]).now()
    confirmed = await person.browser.post("/api/auth/totp/confirm", json={"code": code})
    assert confirmed.status_code == 200, confirmed.text
    [added] = site.mail.to(person.email)[before:]
    found = _LINK.search(added.text)
    assert found is not None, added.text
    return found.group(1)


async def _totp(site: Site, person: Person) -> Totp | None:
    async with site.db() as db:
        found: Totp | None = await db.get(Totp, person.id)
        return found


async def _undo_row(site: Site, person: Person) -> Token:
    async with site.db() as db:
        rows = list(
            await db.scalars(
                select(Token).where(Token.user_id == person.id, Token.purpose == "factor_undo")
            )
        )
    [row] = rows
    return row


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


# --- the link -----------------------------------------------------------------------


async def test_the_link_is_kept_as_a_keyed_hash_for_7_days(site: Site) -> None:
    person = await _person(site)
    token = await _add_totp(site, person)
    row = await _undo_row(site, person)
    assert row.token_hash == keyed_hash("factor_undo", token)
    assert token not in row.token_hash
    assert row.expires_at - row.created_at == timedelta(days=7)
    totp = await _totp(site, person)
    assert totp is not None
    assert totp.confirmed_at is not None
    assert row.data == {"method": "totp", "confirmed_at": totp.confirmed_at.isoformat()}


async def test_an_old_totp_link_leaves_a_totp_set_up_since(site: Site) -> None:
    """Bound to the TOTP it was mailed for: after the owner removed that one
    and set up their own, the old link takes nothing, though it still ends
    every session."""
    person = await _person(site)
    old = await _add_totp(site, person)
    assert (await person.browser.delete("/api/auth/totp")).status_code == 204
    await _add_totp(site, person)
    undone = await site.browser().post(UNDO, json={"token": old})
    assert undone.json() == {"status": "second_factor_undone"}
    totp = await _totp(site, person)
    assert totp is not None
    assert totp.confirmed_at is not None  # still there
    assert (await person.browser.get("/api/auth/session")).status_code == 401
    [row] = await _audit(site, "auth.second_factor_undone")
    assert row.details == {"method": "totp", "removed": False}


async def test_an_undo_is_audited_the_codes_go_and_the_owner_is_told(site: Site) -> None:
    person = await _person(site)
    token = await _add_totp(site, person)
    undone = await site.browser().post(UNDO, json={"token": token})
    assert undone.status_code == 200, undone.text
    assert await _totp(site, person) is None
    async with site.db() as db:
        codes = await db.scalar(
            select(func.count()).select_from(RecoveryCode).where(RecoveryCode.user_id == person.id)
        )
    assert codes == 0
    [row] = await _audit(site, "auth.second_factor_undone")
    assert (row.subject_id, row.result) == (person.id, "success")
    assert row.details == {"method": "totp", "removed": True}
    notice = site.mail.to(person.email)[-1]
    assert "removed" in notice.subject.lower()
    assert "reset your password" in notice.text.lower()
    assert _LINK.search(notice.text) is None


async def test_an_undo_voids_every_live_way_in_but_other_undo_links(site: Site) -> None:
    person = await _person(site)
    token = await _add_totp(site, person)
    async with site.db() as db:
        for purpose in (*_ENDED, "factor_undo"):
            db.add(
                Token(
                    purpose=purpose,
                    token_hash=keyed_hash(purpose, uuid.uuid4().hex),
                    user_id=person.id,
                    email_normal=normal_email(person.email),
                    created_at=clock.now(),
                    expires_at=clock.now() + timedelta(minutes=30),
                )
            )
        await db.commit()
    assert (await site.browser().post(UNDO, json={"token": token})).status_code == 200
    async with site.db() as db:
        live = dict(
            (
                await db.execute(
                    select(Token.purpose, func.count())
                    .where(Token.user_id == person.id, Token.used_at.is_(None))
                    .group_by(Token.purpose)
                )
            ).all()
        )
    assert live == {"factor_undo": 1}  # the other link, as a thief's second factor leaves


async def test_an_account_that_cant_sign_in_undoes_nothing(site: Site) -> None:
    person = await _person(site)
    token = await _add_totp(site, person)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(status="suspended"))
        await db.commit()
    refused = await site.browser().post(UNDO, json={"token": token})
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")
    assert await _totp(site, person) is not None
    row = await _undo_row(site, person)
    assert row.used_at is None  # left as it was


async def test_a_link_never_issued_is_refused(site: Site) -> None:
    refused = await site.browser().post(UNDO, json={"token": "x" * 43})
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


# --- lock order and races ------------------------------------------------------------


async def _with_the_account_held(
    site: Site,
    person: Person,
    requests: list[Callable[[], Awaitable[httpx.Response]]],
    probe_row: uuid.UUID | None = None,
) -> list[httpx.Response]:
    """Hold the account row, start every request, and wait until each is
    blocked on a lock, so they really overlap once it's let go. With
    `probe_row`, check with NOWAIT that none took that token row first."""
    async with site.db() as holder, site.db() as watcher:
        await holder.execute(select(User.id).where(User.id == person.id).with_for_update())
        running = [asyncio.create_task(request()) for request in requests]
        try:
            blocked = 0
            for _ in range(250):
                await asyncio.sleep(0.02)
                blocked = (
                    await watcher.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity"
                            " WHERE wait_event_type = 'Lock' AND datname = current_database()"
                        )
                    )
                    or 0
                )
                await watcher.rollback()
                if blocked >= len(requests):
                    break
            assert blocked >= len(requests), "the requests never all waited for the account row"
            if probe_row is not None:
                found = await watcher.scalar(text(_TOKEN_ROW_FREE), {"id": probe_row})
                assert found == probe_row
        finally:  # let the requests finish either way, so nothing leaks
            await watcher.rollback()
            await holder.rollback()
            answers = await asyncio.gather(*running)
    return list(answers)


async def test_an_undo_locks_the_account_before_its_link(site: Site) -> None:
    person = await _person(site)
    token = await _add_totp(site, person)
    row = await _undo_row(site, person)
    browser = site.browser()
    [undone] = await _with_the_account_held(
        site, person, [lambda: browser.post(UNDO, json={"token": token})], probe_row=row.id
    )
    assert undone.status_code == 200, undone.text


async def test_two_undos_with_one_link_at_once_succeed_once(site: Site) -> None:
    person = await _person(site)
    token = await _add_totp(site, person)
    first, second = site.browser(), site.browser()
    answers = await _with_the_account_held(
        site,
        person,
        [
            lambda: first.post(UNDO, json={"token": token}),
            lambda: second.post(UNDO, json={"token": token}),
        ],
    )
    assert sorted(answer.status_code for answer in answers) == [200, 400]
    assert len(await _audit(site, "auth.second_factor_undone")) == 1

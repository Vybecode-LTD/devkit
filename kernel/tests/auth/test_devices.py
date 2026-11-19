"""The account page's routes (docs/contracts/auth-api.md; K4.5): signed-in
devices (SPEC.md 14.5) and the summary of the account's ways in. What the
contract suite can't see from outside, such as the audit, a place the site
knows, a session past its idle limit, a token replaced on the way out, and
an account with no password."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.app import create_app
from kernel.auth.accounts import normal_email
from kernel.auth.models import AuditEvent, Session, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, Draining, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
SESSIONS = "/api/auth/sessions"
SESSION_COOKIE = "__Host-mf_session"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


@dataclass
class Site:
    app: FastAPI
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        transport = Draining(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    app = create_app(config=make_config(database_url=migrated_url), mailer=CapturingMailer())
    async with Client(app):
        made = Site(app)
        async with made.db() as db:
            made.audit_from = await db.scalar(select(func.max(AuditEvent.id))) or 0
        yield made


async def _person(site: Site) -> tuple[uuid.UUID, str]:
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
        return user.id, email


async def _signed_in(site: Site, email: str) -> httpx.AsyncClient:
    browser = site.browser()
    signed = await browser.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert signed.json()["status"] == "signed_in", signed.text
    return browser


async def _ids(browser: httpx.AsyncClient) -> tuple[str, list[str]]:
    """This browser's session id, and every other one's."""
    items = (await browser.get(SESSIONS)).json()["items"]
    (mine,) = [item["id"] for item in items if item["current"]]
    return mine, [item["id"] for item in items if not item["current"]]


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


async def test_signing_out_a_device_is_audited_with_the_session(site: Site) -> None:
    user_id, email = await _person(site)
    phone, laptop = await _signed_in(site, email), await _signed_in(site, email)
    _, (phones,) = await _ids(laptop)
    assert (await laptop.delete(f"{SESSIONS}/{phones}")).status_code == 204
    (row,) = await _audit(site, "auth.session_ended")
    assert (row.actor_id, row.subject_id) == (user_id, user_id)
    assert row.details == {"reason": "signed_out", "session": phones}
    assert (await phone.get("/api/auth/session")).status_code == 401


async def test_signing_out_everywhere_else_is_audited_with_how_many(site: Site) -> None:
    user_id, email = await _person(site)
    for _ in range(2):
        await _signed_in(site, email)
    laptop = await _signed_in(site, email)
    assert (await laptop.post(f"{SESSIONS}/sign-out-others")).status_code == 204
    (row,) = await _audit(site, "auth.session_ended")
    assert (row.subject_id, row.details) == (user_id, {"reason": "signed_out_others", "ended": 2})


async def test_signing_out_this_device_is_audited_as_a_sign_out(site: Site) -> None:
    user_id, email = await _person(site)
    laptop = await _signed_in(site, email)
    mine, _ = await _ids(laptop)
    assert (await laptop.delete(f"{SESSIONS}/{mine}")).status_code == 204
    (row,) = await _audit(site, "auth.sign_out")
    assert (row.actor_id, row.subject_id) == (user_id, user_id)
    assert await _audit(site, "auth.session_ended") == []


async def test_a_place_the_site_knows_is_shown(site: Site) -> None:
    _, email = await _person(site)
    laptop = await _signed_in(site, email)
    mine, _ = await _ids(laptop)
    async with site.db() as db:
        await db.execute(
            update(Session).where(Session.id == uuid.UUID(mine)).values(location="Boston, US")
        )
        await db.commit()
    (item,) = (await laptop.get(SESSIONS)).json()["items"]
    assert item["location"] == "Boston, US"


async def test_a_session_past_its_idle_limit_isnt_listed_or_ended(site: Site) -> None:
    _, email = await _person(site)
    await _signed_in(site, email)
    laptop = await _signed_in(site, email)
    _, (old,) = await _ids(laptop)
    async with site.db() as db:
        long_ago = clock.now() - timedelta(days=15)  # a member's idle limit is 14
        await db.execute(
            update(Session).where(Session.id == uuid.UUID(old)).values(last_seen_at=long_ago)
        )
        await db.commit()
    assert [item["id"] for item in (await laptop.get(SESSIONS)).json()["items"]] != [old]
    refused = await laptop.delete(f"{SESSIONS}/{old}")
    assert (refused.status_code, refused.json()["code"]) == (404, "auth.session_not_found")


async def test_signing_out_this_device_after_a_role_change_sets_no_new_token(site: Site) -> None:
    """A role change replaces the token at the next request (14.5). When that
    request ends the session, the new token must not go out with it."""
    user_id, email = await _person(site)
    laptop = await _signed_in(site, email)
    mine, _ = await _ids(laptop)
    async with site.db() as db:
        await db.execute(
            update(User).where(User.id == user_id).values(role_version=User.role_version + 1)
        )
        await db.commit()
    ended = await laptop.delete(f"{SESSIONS}/{mine}")
    assert ended.status_code == 204
    set_cookies = [
        header
        for header in ended.headers.get_list("set-cookie")
        if header.startswith(f"{SESSION_COOKIE}=")
    ]
    (cleared,) = set_cookies  # the clearing alone, never the replaced token
    assert cleared.startswith(f'{SESSION_COOKIE}="";')
    assert (await laptop.get("/api/auth/session")).status_code == 401


async def test_the_security_summary_says_when_there_is_no_password(site: Site) -> None:
    user_id, email = await _person(site)
    laptop = await _signed_in(site, email)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == user_id).values(password_hash=None))
        await db.commit()
    summary = (await laptop.get("/api/auth/security")).json()
    assert summary == {"password": False, "totp": None, "recovery_codes_left": 0}

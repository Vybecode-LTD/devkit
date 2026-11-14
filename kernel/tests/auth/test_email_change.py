"""Email change (SPEC.md 14.6 and 14.7; docs/contracts/auth-api.md; decision
0024): what the contract suite can't see from outside, such as the stored
rows, the audit, races, lock order and accounts that change between a mail
and its use. The contract suite covers the answers, the expiries and the
limit per account."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.app import create_app
from kernel.auth import email_change, floor
from kernel.auth.accounts import normal_email
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import AuditEvent, Token, Totp, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
_CHANGE = "email_change"


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
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


async def _no_breaches(prefix: str) -> str:
    """The breach lookup, offline: no password is breached (CodeRabbit on #45)."""
    return ""


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    mail = CapturingMailer()
    app = create_app(
        config=make_config(database_url=migrated_url), mailer=mail, breach_lookup=_no_breaches
    )
    async with Client(app) as http:
        http.headers.update(_SAME_ORIGIN)
        made = Site(app, http, mail)
        async with made.db() as db:
            made.audit_from = await db.scalar(select(func.max(AuditEvent.id))) or 0
        yield made


@dataclass
class Person:
    id: uuid.UUID
    email: str
    browser: httpx.AsyncClient


def _address(name: str = "Ana") -> str:
    return f"{name}.{uuid.uuid4().hex[:10]}@Site.test"


async def _person(site: Site, *, totp: bool = False) -> Person:
    """A verified member, signed in a moment ago on a browser of their own."""
    email = _address()
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
        secret = None
        if totp:
            secret = pyotp.random_base32()
            db.add(
                Totp(user_id=user.id, secret_sealed=crypto.seal(secret), confirmed_at=clock.now())
            )
        await db.commit()
    browser = site.browser()
    signed = await browser.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    if signed.json()["status"] == "second_factor":
        assert secret
        signed = await browser.post(
            "/api/auth/sign-in/second-factor",
            json={"challenge": signed.json()["challenge"], "totp": pyotp.TOTP(secret).now()},
        )
    assert signed.json()["status"] == "signed_in", signed.text
    return Person(user.id, email, browser)


async def _change(person: Person, email: str) -> httpx.Response:
    return await person.browser.post("/api/auth/email/change", json={"email": email})


async def _confirm(http: httpx.AsyncClient, token: str) -> httpx.Response:
    return await http.post("/api/auth/email/confirm", json={"token": token})


async def _undo(http: httpx.AsyncClient, token: str) -> httpx.Response:
    return await http.post("/api/auth/email/undo", json={"token": token})


def _links(site: Site, email: str, path: str) -> list[str]:
    """Every `path` token mailed to `email`, oldest first."""
    found = []
    for message in site.mail.to(email):
        for word in message.text.split():
            parts = urlsplit(word.rstrip(".,)"))
            if parts.path == path and "token" in parse_qs(parts.query):
                found.append(parse_qs(parts.query)["token"][0])
    return found


def _last(site: Site, email: str, path: str) -> str:
    links = _links(site, email, path)
    assert links, [m.text for m in site.mail.to(email)]
    return links[-1]


async def _account(site: Site, person: Person) -> User:
    async with site.db() as db:
        user = await db.get(User, person.id)
        assert user is not None
        return user


async def _rows(site: Site, user_id: uuid.UUID, purpose: str = _CHANGE) -> list[Token]:
    async with site.db() as db:
        found = await db.scalars(
            select(Token)
            .where(Token.user_id == user_id, Token.purpose == purpose)
            .order_by(Token.created_at)
        )
        return list(found)


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


async def _changed(site: Site, person: Person) -> tuple[str, str]:
    """Move the person to a new address, confirmed: the new address and the
    undo token mailed to the old one."""
    new = _address("Moved")
    await _change(person, new)
    assert (await _confirm(site.browser(), _last(site, new, "/auth/email"))).status_code == 200
    return new, _last(site, person.email, "/auth/email/undo")


# --- asking ---------------------------------------------------------------------


async def test_a_change_mails_a_24_hour_link_to_the_new_address(site: Site) -> None:
    person = await _person(site)
    new = _address("New")
    asked = await _change(person, f"  {new} ")
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    token = _last(site, new, "/auth/email")
    [row] = await _rows(site, person.id)
    assert row.token_hash == keyed_hash(_CHANGE, token)
    assert row.email_normal == normal_email(new)
    epoch = (await _account(site, person)).session_epoch
    assert row.data == {"kind": "confirm", "email": new, "epoch": epoch}
    assert row.expires_at - row.created_at == timedelta(hours=24)
    assert (await _account(site, person)).email == person.email  # until it's confirmed


@pytest.mark.parametrize("email", ["two@site.test, more@site.test", "nobody", ""])
async def test_anything_but_one_address_is_refused(site: Site, email: str) -> None:
    person = await _person(site)
    refused = await _change(person, email)
    assert (refused.status_code, refused.json()["code"]) == (422, "kernel.invalid_request")


async def test_the_address_the_account_has_is_refused(site: Site) -> None:
    person = await _person(site)
    refused = await _change(person, person.email.upper())
    assert (refused.status_code, refused.json()["code"]) == (422, "kernel.invalid_request")
    assert await _rows(site, person.id) == []


async def test_an_address_with_an_account_is_sent_a_notice(site: Site) -> None:
    mine, theirs = await _person(site), await _person(site)
    asked = await _change(mine, theirs.email.lower())
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    notices = [m for m in site.mail.to(theirs.email) if "change" in m.subject.lower()]
    assert len(notices) == 1  # to the account's own form of its address (not the sign-in's)
    assert _links(site, theirs.email, "/auth/email") == []
    # Only the unmailed trace the wait counts; nothing that could confirm.
    assert [r.data["kind"] for r in await _rows(site, mine.id)] == ["notice"]
    [event] = await _audit(site, "auth.email_change_requested")
    assert (event.result, event.subject_id) == ("taken", mine.id)
    assert "@" not in repr(event.details)


async def test_a_new_change_voids_the_last(site: Site) -> None:
    person = await _person(site)
    first, second = _address("First"), _address("Second")
    await _change(person, first)
    clock.advance(61)
    await _change(person, second)
    gone = await _confirm(site.browser(), _last(site, first, "/auth/email"))
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")
    assert (await _confirm(site.browser(), _last(site, second, "/auth/email"))).status_code == 200


async def test_a_change_within_60_seconds_sends_nothing(site: Site) -> None:
    person = await _person(site)
    first, second = _address("First"), _address("Second")
    await _change(person, first)
    clock.advance(59)
    asked = await _change(person, second)
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    assert site.mail.to(second) == []
    assert (await _confirm(site.browser(), _last(site, first, "/auth/email"))).status_code == 200


async def test_one_address_is_mailed_at_most_3_times_in_15_minutes(site: Site) -> None:
    """From four accounts, so no account's own budget is spent."""
    target = _address("Target")
    people = [await _person(site) for _ in range(4)]
    for person in people:
        assert (await _change(person, target)).status_code == 202
    assert len(site.mail.to(target)) == 3


async def test_changes_at_once_send_one_link(site: Site) -> None:
    """From three browsers signed in to the account (one browser's requests
    overlap only sometimes): the lock and the wait leave one live link."""
    person = await _person(site)
    browsers = [person.browser]
    for _ in range(2):
        other = site.browser()
        signed = await other.post(
            "/api/auth/sign-in", json={"email": person.email, "password": PASSWORD}
        )
        assert signed.status_code == 200
        browsers.append(other)
    await _warm(site)
    targets = [_address(f"T{i}") for i in range(3)]
    answers = await asyncio.gather(
        *(
            b.post("/api/auth/email/change", json={"email": t})
            for b, t in zip(browsers, targets, strict=True)
        )
    )
    assert [a.status_code for a in answers] == [202] * 3
    assert sum(len(_links(site, t, "/auth/email")) for t in targets) == 1
    assert len([r for r in await _rows(site, person.id) if r.used_at is None]) == 1


async def test_changes_answer_no_sooner_than_the_floor(site: Site) -> None:
    mine, theirs = await _person(site), await _person(site)
    for email in (_address("Free"), theirs.email):
        clock.advance(61)
        started = time.perf_counter()
        await _change(mine, email)
        assert time.perf_counter() - started >= floor.ANSWER_FLOOR


async def test_a_change_is_audited(site: Site) -> None:
    person = await _person(site)
    await _change(person, _address())
    [event] = await _audit(site, "auth.email_change_requested")
    assert (event.result, event.actor_id, event.subject_id) == ("success", person.id, person.id)
    assert "@" not in repr(event.details)


# --- confirming -----------------------------------------------------------------


async def test_confirming_moves_the_account_and_mails_the_old_address(site: Site) -> None:
    person = await _person(site)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(email_verified_at=None))
        await db.commit()
    new, undo = await _changed(site, person)
    user = await _account(site, person)
    assert (user.email, user.email_normal) == (new, normal_email(new))
    assert user.email_verified_at is not None
    [row] = [r for r in await _rows(site, person.id) if r.data.get("kind") == "undo"]
    assert row.token_hash == keyed_hash(_CHANGE, undo)
    assert row.email_normal == normal_email(person.email)
    assert row.data == {"kind": "undo", "email": person.email, "verified_at": None}
    assert row.expires_at - row.created_at == timedelta(days=7)
    assert (await person.browser.get("/api/auth/session")).status_code == 200  # still signed in
    [event] = await _audit(site, "auth.email_changed")
    assert (event.result, event.subject_id) == ("success", person.id)


async def test_an_undo_link_isnt_a_confirm_link(site: Site) -> None:
    person = await _person(site)
    _, undo = await _changed(site, person)
    refused = await _confirm(site.browser(), undo)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")
    assert (await _undo(site.browser(), undo)).status_code == 200  # nothing was used up


async def test_a_confirm_link_isnt_an_undo_link(site: Site) -> None:
    person = await _person(site)
    new = _address()
    await _change(person, new)
    token = _last(site, new, "/auth/email")
    refused = await _undo(site.browser(), token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")
    assert (await _confirm(site.browser(), token)).status_code == 200


async def test_an_address_taken_since_the_ask_is_refused(site: Site) -> None:
    person, other = await _person(site), await _person(site)
    new = _address()
    await _change(person, new)
    token = _last(site, new, "/auth/email")
    async with site.db() as db:  # someone else takes the address meanwhile
        await db.execute(
            update(User)
            .where(User.id == other.id)
            .values(email=new, email_normal=normal_email(new))
        )
        await db.commit()
    refused = await _confirm(site.browser(), token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")
    assert (await _account(site, person)).email == person.email


@pytest.mark.parametrize("status", ["suspended", "deleted"])
async def test_an_account_that_cant_sign_in_any_more_isnt_moved(site: Site, status: str) -> None:
    person = await _person(site)
    new = _address()
    await _change(person, new)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(status=status))
        await db.commit()
    refused = await _confirm(site.browser(), _last(site, new, "/auth/email"))
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


async def test_one_link_confirmed_twice_at_once_moves_once(site: Site) -> None:
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        new = _address()
        await _change(person, new)
        token = _last(site, new, "/auth/email")
        answers = await asyncio.gather(*(_confirm(site.browser(), token) for _ in range(3)))
        assert sorted(a.status_code for a in answers) == [200, 400, 400]
        assert len(_links(site, person.email, "/auth/email/undo")) == 1


# --- undoing --------------------------------------------------------------------


async def test_undoing_restores_the_address_and_ends_every_session(site: Site) -> None:
    person = await _person(site)
    before = (await _account(site, person)).email_verified_at
    _, undo = await _changed(site, person)
    restored = await _undo(site.browser(), undo)
    assert (restored.status_code, restored.json()) == (200, {"status": "email_restored"})
    user = await _account(site, person)
    assert (user.email, user.email_verified_at) == (person.email, before)
    assert (await person.browser.get("/api/auth/session")).status_code == 401
    notice = site.mail.to(person.email)[-1]
    assert "token=" not in notice.text
    [event] = await _audit(site, "auth.email_restored")
    assert (event.result, event.subject_id) == ("success", person.id)
    assert "@" not in repr(event.details)


async def test_a_later_change_cant_void_an_earlier_undo(site: Site) -> None:
    """Whoever changed the address can't change it again to kill the owner's
    undo link: each undo restores the address it was sent to."""
    person = await _person(site)
    first, undo_first = await _changed(site, person)
    person.email = first
    clock.advance(61)
    _, undo_second = await _changed(site, person)
    assert (await _undo(site.browser(), undo_first)).status_code == 200
    restored = await _account(site, person)
    assert restored.email != first  # back to the very first address
    # And the restore ended the other undo, sent to an address just taken back.
    gone = await _undo(site.browser(), undo_second)
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")


async def test_undoing_voids_every_way_in_sent_since(site: Site) -> None:
    person = await _person(site)
    new, undo = await _changed(site, person)
    await site.http.post("/api/auth/code", json={"email": new})
    await site.http.post("/api/auth/password/reset-request", json={"email": new})
    await _undo(site.browser(), undo)
    for purpose in ("sign_in_code", "magic_link", "reset_password", _CHANGE):
        assert all(r.used_at is not None for r in await _rows(site, person.id, purpose)), purpose


async def test_an_old_address_taken_since_is_refused(site: Site) -> None:
    person, other = await _person(site), await _person(site)
    _, undo = await _changed(site, person)
    async with site.db() as db:
        await db.execute(
            update(User)
            .where(User.id == other.id)
            .values(email=person.email, email_normal=normal_email(person.email))
        )
        await db.commit()
    refused = await _undo(site.browser(), undo)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


# --- lock order -----------------------------------------------------------------


async def _warm(site: Site) -> None:
    opened = [site.db() for _ in range(3)]
    try:
        await asyncio.gather(*(db.execute(select(1)) for db in opened))
    finally:
        for db in opened:
            await db.close()


async def _with_the_account_held(
    site: Site,
    person: Person,
    request: Callable[[], Awaitable[httpx.Response]],
    row_id: uuid.UUID,
) -> httpx.Response:
    """Hold the account row, start `request`, wait until it's blocked, and
    check it hasn't taken the token's row yet (`test_resets.py` explains)."""
    async with site.db() as holder, site.db() as watcher:
        await holder.execute(select(User.id).where(User.id == person.id).with_for_update())
        running = asyncio.create_task(request())
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
            assert blocked, "the request never waited for the account row"
            free = await watcher.scalar(
                text("SELECT id FROM auth_token WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": row_id},
            )
            assert free == row_id
        finally:
            await watcher.rollback()
            await holder.rollback()
            answer = await running
    return answer


async def test_confirming_locks_the_account_before_its_link(site: Site) -> None:
    person = await _person(site)
    new = _address()
    await _change(person, new)
    token = _last(site, new, "/auth/email")
    [row] = await _rows(site, person.id)
    answer = await _with_the_account_held(
        site, person, lambda: _confirm(site.browser(), token), row.id
    )
    assert answer.status_code == 200


async def test_undoing_locks_the_account_before_its_link(site: Site) -> None:
    person = await _person(site)
    _, undo = await _changed(site, person)
    [row] = [r for r in await _rows(site, person.id) if r.data.get("kind") == "undo"]
    answer = await _with_the_account_held(site, person, lambda: _undo(site.browser(), undo), row.id)
    assert answer.status_code == 200


# --- what follows ---------------------------------------------------------------


async def test_a_failing_mailer_changes_nothing(site: Site) -> None:
    class Broken:
        async def send(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("the mail host is down")

    person = await _person(site)
    site.app.state.mailer.inner = Broken()
    assert (await _change(person, _address())).status_code == 202
    assert len(await _rows(site, person.id)) == 1


@pytest.mark.parametrize("route", ["confirm", "undo"])
async def test_an_address_taken_after_the_check_is_a_400_not_a_500(
    site: Site, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Another account can take the address between the route's check and
    its write. The unique index then refuses the write, and the route answers
    as for a taken address. The check is made to miss, as it would in that
    race."""
    person, other = await _person(site), await _person(site)
    if route == "confirm":
        target = _address()
        await _change(person, target)
        token = _last(site, target, "/auth/email")
    else:
        _, token = await _changed(site, person)
        target = person.email
    async with site.db() as db:
        await db.execute(
            update(User)
            .where(User.id == other.id)
            .values(email=target, email_normal=normal_email(target))
        )
        await db.commit()

    async def missed(*args: object) -> bool:
        return False

    monkeypatch.setattr(email_change, "_taken", missed)
    answer = await (_confirm if route == "confirm" else _undo)(site.browser(), token)
    assert (answer.status_code, answer.json()["code"]) == (400, "auth.token_invalid")


@pytest.mark.parametrize("status", ["suspended", "deleted"])
async def test_an_undo_for_an_account_that_cant_sign_in_is_refused(site: Site, status: str) -> None:
    person = await _person(site)
    _, undo = await _changed(site, person)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(status=status))
        await db.commit()
    refused = await _undo(site.browser(), undo)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


async def test_undoing_a_later_change_keeps_the_earlier_undo(site: Site) -> None:
    """The reverse order (Codex on #45): whoever moved the address A to B to
    C uses the undo link sent to B first. That must not void the owner's undo
    link back to A, which then restores A."""
    person = await _person(site)
    first_address = person.email
    second, undo_first = await _changed(site, person)
    person.email = second
    clock.advance(61)
    _, undo_second = await _changed(site, person)
    assert (await _undo(site.browser(), undo_second)).status_code == 200
    assert (await _account(site, person)).email == second
    assert (await _undo(site.browser(), undo_first)).status_code == 200
    assert (await _account(site, person)).email == first_address


async def test_a_pending_change_dies_with_a_password_reset(site: Site) -> None:
    """Whoever asked for a change with the old password can't confirm it
    after the owner resets (Codex on #45)."""
    person = await _person(site)
    new = _address()
    await _change(person, new)
    token = _last(site, new, "/auth/email")
    await site.http.post("/api/auth/password/reset-request", json={"email": person.email})
    reset = _last(site, person.email, "/auth/reset")
    done = await site.http.post(
        "/api/auth/password/reset",
        json={"token": reset, "password": "amber walrus cello 5528 dune"},
    )
    assert done.status_code == 200
    refused = await _confirm(site.browser(), token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")
    assert (await _account(site, person)).email == person.email


async def test_a_pending_change_dies_with_any_new_session_epoch(site: Site) -> None:
    """The link is bound to the epoch it was asked under: a password change,
    a second-factor reset or a suspension raises it too."""
    person = await _person(site)
    new = _address()
    await _change(person, new)
    token = _last(site, new, "/auth/email")
    async with site.db() as db:
        await db.execute(
            update(User).where(User.id == person.id).values(session_epoch=User.session_epoch + 1)
        )
        await db.commit()
    refused = await _confirm(site.browser(), token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


@pytest.mark.parametrize("target_has_an_account", [False, True])
async def test_the_wait_follows_any_request_whatever_the_address(
    site: Site, target_has_an_account: bool
) -> None:
    """CodeRabbit on #45: after a request for an address with an account, a
    request for an inbox of one's own within 60 seconds was mailed, while after
    one for a free address it wasn't. Both now wait the same."""
    mine = await _person(site)
    target = (await _person(site)).email if target_has_an_account else _address("Free")
    await _change(mine, target)
    own = _address("Own")
    await _change(mine, own)
    assert _links(site, own, "/auth/email") == []


@pytest.mark.parametrize("target_has_an_account", [False, True])
async def test_any_request_voids_the_last_link_whatever_the_address(
    site: Site, target_has_an_account: bool
) -> None:
    """And a request for an address with an account voids the last link, as
    one for a free address does, so whether it still works tells nothing."""
    mine = await _person(site)
    own = _address("Own")
    await _change(mine, own)
    token = _last(site, own, "/auth/email")
    clock.advance(61)
    target = (await _person(site)).email if target_has_an_account else _address("Free")
    await _change(mine, target)
    refused = await _confirm(site.browser(), token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")

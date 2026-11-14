"""Password resets (SPEC.md 14.6, 14.7, 14.10 and 14.12;
docs/contracts/auth-api.md; decision 0022): what the contract suite can't
see from outside, such as the stored rows, the audit, races, what a reset
ends and accounts that change between the mail and its use. The contract
suite (`kernel/tests/contract/`) covers the answers, the expiry and the
limits."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
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
from kernel.auth import floor
from kernel.auth.accounts import normal_email
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import AuditEvent, Token, Totp, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
NEW = "amber walrus cello 5528 dune"
LEAKED = "copper heron valley 2093 tide"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
_RESET = "reset_password"


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
    #: Passwords the fake breach lookup reports.
    breached: set[str] = field(default_factory=set)
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        """Another browser: no cookies of its own yet."""
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
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
    totp_secret: str | None = None


async def _person(
    site: Site,
    *roles: str,
    status: str = "active",
    verified: bool = True,
    totp: bool = False,
) -> Person:
    email = f"Lee.{uuid.uuid4().hex[:10]}@Site.test"
    hashed = await site.app.state.passwords.hash(PASSWORD)
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            password_hash=hashed,
            status=status,
            email_verified_at=clock.now() if verified else None,
        )
        db.add(user)
        await db.flush()
        for role in roles or ("member",):
            db.add(UserRole(user_id=user.id, role_id=role))
        secret = None
        if totp:
            secret = pyotp.random_base32()
            db.add(
                Totp(user_id=user.id, secret_sealed=crypto.seal(secret), confirmed_at=clock.now())
            )
        await db.commit()
        return Person(user.id, email, secret)


async def _ask(http: httpx.AsyncClient, email: str) -> httpx.Response:
    return await http.post("/api/auth/password/reset-request", json={"email": email})


async def _reset(http: httpx.AsyncClient, token: str, password: str = NEW) -> httpx.Response:
    return await http.post("/api/auth/password/reset", json={"token": token, "password": password})


async def _sign_in(http: httpx.AsyncClient, person: Person, password: str) -> httpx.Response:
    return await http.post("/api/auth/sign-in", json={"email": person.email, "password": password})


def _link(text: str) -> str:
    links = [word for word in text.split() if "/auth/reset?" in word]
    assert len(links) == 1, text
    assert links[0].startswith(f"{SITE}/auth/reset?token="), links[0]
    return parse_qs(urlsplit(links[0].rstrip(".,)")).query)["token"][0]


def _mailed(site: Site, person: Person) -> str:
    """The token of the last reset link mailed to the person."""
    links = [m.text for m in site.mail.to(person.email) if "/auth/reset?" in m.text]
    assert links, site.mail.to(person.email)
    return _link(links[-1])


async def _rows(site: Site, user_id: uuid.UUID, purpose: str = _RESET) -> list[Token]:
    async with site.db() as db:
        found = await db.scalars(
            select(Token)
            .where(Token.user_id == user_id, Token.purpose == purpose)
            .order_by(Token.created_at)
        )
        return list(found)


async def _user(site: Site, person: Person) -> User:
    async with site.db() as db:
        user = await db.get(User, person.id)
        assert user is not None
        return user


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


async def _warm(site: Site, connections: int = 3) -> None:
    """Open the pool's connections before a race: on a cold pool requests
    never overlap (see `test_codes.py:_warm`)."""
    opened = [site.db() for _ in range(connections)]
    try:
        await asyncio.gather(*(db.execute(select(1)) for db in opened))
    finally:
        for db in opened:
            await db.close()


async def _change(site: Site, person: Person, **values: object) -> None:
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(**values))
        await db.commit()


# --- asking ---------------------------------------------------------------------


async def test_one_message_holds_a_30_minute_link(site: Site) -> None:
    person = await _person(site)
    asked = await _ask(site.http, f"  {person.email.upper()} ")
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    [message] = site.mail.to(person.email)  # the account's own form of the address
    token = _link(message.text)
    [row] = await _rows(site, person.id)
    assert row.email_normal == normal_email(person.email)
    assert row.expires_at - row.created_at == timedelta(minutes=30)
    assert row.token_hash == keyed_hash(_RESET, token)
    assert row.used_at is None


async def test_staff_are_sent_a_reset_too(site: Site) -> None:
    """A reset signs nobody in, so a staff account's second factor still
    guards it (14.4); unlike a sign-in code, staff may have one."""
    person = await _person(site, "admin", totp=True)
    await _ask(site.http, person.email)
    assert len(site.mail.to(person.email)) == 1


@pytest.mark.parametrize("status", ["suspended", "deleted"])
async def test_an_account_that_cant_sign_in_is_sent_nothing(site: Site, status: str) -> None:
    person = await _person(site, status=status)
    asked = await _ask(site.http, person.email)
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    assert site.mail.to(person.email) == []
    assert await _rows(site, person.id) == []
    [event] = await _audit(site, "auth.password_reset_requested")
    assert (event.result, event.subject_id) == ("refused", person.id)


async def test_an_unknown_address_is_sent_nothing_and_kept_nowhere(site: Site) -> None:
    unknown = f"nobody.{uuid.uuid4().hex[:10]}@site.test"
    asked = await _ask(site.http, unknown)
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    assert site.mail.to(unknown) == []
    [event] = await _audit(site, "auth.password_reset_requested")
    assert (event.result, event.subject_id) == ("refused", None)
    assert "@" not in repr(event.details)


async def test_a_resend_within_60_seconds_leaves_the_first_link_working(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)
    clock.advance(59)
    await _ask(site.http, person.email)
    assert len(site.mail.to(person.email)) == 1
    results = [e.result for e in await _audit(site, "auth.password_reset_requested")]
    assert results == ["success", "waiting"]
    assert (await _reset(site.http, token)).status_code == 200


async def test_a_new_ask_voids_the_last_link(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    old = _mailed(site, person)
    clock.advance(61)
    await _ask(site.http, person.email)
    new = _mailed(site, person)
    assert new != old
    gone = await _reset(site.http, old)
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")
    assert (await _reset(site.http, new)).status_code == 200  # the control


async def test_an_unknown_address_has_the_same_budget(site: Site) -> None:
    """Eight asks: under the IP's 10."""
    person = await _person(site)
    unknown = f"nobody.{uuid.uuid4().hex[:10]}@site.test"
    seen = {}
    for email in (person.email, unknown):
        answers = [await _ask(site.browser(), email) for _ in range(4)]
        seen[email] = [a.status_code for a in answers]
        assert answers[-1].json()["code"] == "kernel.rate_limited"
    assert seen[person.email] == seen[unknown] == [202, 202, 202, 429]


async def test_asks_answer_no_sooner_than_the_floor(site: Site) -> None:
    person = await _person(site)
    for email in (person.email, f"nobody.{uuid.uuid4().hex[:8]}@site.test"):
        started = time.perf_counter()
        await _ask(site.http, email)
        assert time.perf_counter() - started >= floor.ANSWER_FLOOR


async def test_asks_at_once_send_one_message(site: Site) -> None:
    """Three rounds of three, nine asks: under the IP's 10."""
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        answers = await asyncio.gather(*(_ask(site.browser(), person.email) for _ in range(3)))
        assert [a.status_code for a in answers] == [202] * 3
        assert len(site.mail.to(person.email)) == 1
        assert len(await _rows(site, person.id)) == 1


# --- resetting ------------------------------------------------------------------


async def test_a_reset_sets_the_password_and_signs_nobody_in(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    reset = await _reset(site.browser(), _mailed(site, person))
    assert (reset.status_code, reset.json()) == (200, {"status": "password_reset"})
    assert not any(c.startswith("__Host-dk_session=") for c in reset.headers.get_list("set-cookie"))
    assert (await _sign_in(site.browser(), person, PASSWORD)).status_code == 401
    assert (await _sign_in(site.browser(), person, NEW)).json()["status"] == "signed_in"


async def test_a_reset_ends_every_session(site: Site) -> None:
    person = await _person(site)
    signed = site.browser()
    assert (await _sign_in(signed, person, PASSWORD)).status_code == 200
    assert (await signed.get("/api/auth/session")).status_code == 200  # the control
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    assert (await signed.get("/api/auth/session")).status_code == 401


async def test_a_reset_ends_an_open_second_factor_challenge(site: Site) -> None:
    """Whoever knew the old password and stands at the second factor is
    stopped too."""
    person = await _person(site, totp=True)
    assert person.totp_secret
    started = await _sign_in(site.browser(), person, PASSWORD)
    challenge = started.json()["challenge"]
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    late = await site.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": challenge, "totp": pyotp.TOTP(person.totp_secret).now()},
    )
    assert (late.status_code, late.json()["code"]) == (401, "auth.challenge_ended")


async def test_a_reset_voids_a_live_sign_in_code_and_link(site: Site) -> None:
    person = await _person(site)
    await site.http.post("/api/auth/code", json={"email": person.email})
    assert len(await _rows(site, person.id, "sign_in_code")) == 1  # the control
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    for purpose in ("sign_in_code", "magic_link"):
        assert all(r.used_at is not None for r in await _rows(site, person.id, purpose))


async def test_a_staff_reset_keeps_the_second_factor(site: Site) -> None:
    person = await _person(site, "admin", totp=True)
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    after = await _sign_in(site.browser(), person, NEW)
    assert after.json()["status"] == "second_factor"


async def test_a_reset_marks_the_address_verified(site: Site) -> None:
    """The link proved the inbox, and the reset shut out whoever else knew
    the password: a pre-claimed address is the real owner's from here on
    (decision 0022)."""
    person = await _person(site, verified=False)
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    assert (await _user(site, person)).email_verified_at is not None


async def test_a_reset_keeps_an_earlier_verification_time(site: Site) -> None:
    person = await _person(site)
    before = (await _user(site, person)).email_verified_at
    clock.advance(120)
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    assert (await _user(site, person)).email_verified_at == before


async def test_a_refused_password_leaves_the_link_working(site: Site) -> None:
    site.breached.add(LEAKED)
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)
    short = await _reset(site.http, token, "too short")
    assert (short.status_code, short.json()["code"]) == (422, "auth.password_rejected")
    leaked = await _reset(site.http, token, LEAKED)
    assert (leaked.status_code, leaked.json()["code"]) == (422, "auth.password_rejected")
    assert "breach" in leaked.json()["detail"]
    assert (await _reset(site.http, token)).status_code == 200


@pytest.mark.parametrize("token", ["nonsense", "x" * 43, "", "x" * 128])
async def test_an_unknown_link_is_refused(site: Site, token: str) -> None:
    refused = await _reset(site.http, token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


async def test_a_link_to_an_address_the_account_has_left_is_refused(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)
    moved = f"moved.{uuid.uuid4().hex[:8]}@site.test"
    await _change(site, person, email=moved, email_normal=moved)
    refused = await _reset(site.http, token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")


@pytest.mark.parametrize("status", ["suspended", "deleted"])
async def test_an_account_that_cant_sign_in_any_more_is_refused(site: Site, status: str) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)
    await _change(site, person, status=status)
    refused = await _reset(site.http, token)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.token_invalid")
    assert not any(r.used_at for r in await _rows(site, person.id))  # nothing was used up


async def test_one_link_used_twice_at_once_resets_once(site: Site) -> None:
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        await _ask(site.http, person.email)
        token = _mailed(site, person)
        answers = await asyncio.gather(*(_reset(site.browser(), token) for _ in range(3)))
        assert sorted(a.status_code for a in answers) == [200, 400, 400]


async def test_a_reset_racing_a_new_ask_never_fails(site: Site) -> None:
    """Both take the account row before any token row (decision 0021)."""
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        await _ask(site.http, person.email)
        token = _mailed(site, person)
        clock.advance(61)  # past the resend wait, so the ask voids the link
        reset, asked = await asyncio.gather(
            _reset(site.browser(), token), _ask(site.browser(), person.email)
        )
        assert reset.status_code in {200, 400}
        assert asked.status_code == 202


async def test_a_reset_locks_the_account_before_its_link(site: Site) -> None:
    """The race above can't show the order: the reset's Argon2 hash comes
    before its locks, so the ask always finishes first. So hold the account
    row, wait until the reset is blocked, and check it hasn't taken its
    link's row yet; a reset that took the link first would hold that row
    while it waited, and NOWAIT would fail."""
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)
    [row] = await _rows(site, person.id)
    async with site.db() as holder, site.db() as watcher:
        await holder.execute(select(User.id).where(User.id == person.id).with_for_update())
        resetting = asyncio.create_task(_reset(site.browser(), token))
        blocked = False
        for _ in range(250):
            await asyncio.sleep(0.02)
            blocked = bool(
                await watcher.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                        " AND datname = current_database()"
                    )
                )
            )
            await watcher.rollback()
            if blocked:
                break
        assert blocked, "the reset never waited for the account row"
        free = await watcher.scalar(
            text("SELECT id FROM auth_token WHERE id = :id FOR UPDATE NOWAIT"), {"id": row.id}
        )
        assert free == row.id
        await watcher.rollback()
        await holder.rollback()
    assert (await resetting).status_code == 200


async def test_the_address_budget_ignores_case(site: Site) -> None:
    person = await _person(site)
    for variant in (person.email, person.email.upper(), person.email.title()):
        assert (await _ask(site.browser(), variant)).status_code == 202
    fourth = await _ask(site.browser(), person.email.swapcase())
    assert fourth.status_code == 429


# --- what follows ---------------------------------------------------------------


async def test_a_security_mail_follows_and_holds_no_link(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    await _reset(site.http, _mailed(site, person))
    [_, notice] = site.mail.to(person.email)
    assert "password" in notice.subject.lower()
    assert "token=" not in notice.text


async def test_a_failing_mailer_doesnt_fail_the_reset(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)

    class Broken:
        async def send(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("the mail host is down")

    site.app.state.mailer.inner = Broken()
    assert (await _reset(site.http, token)).status_code == 200


async def test_resets_are_audited_without_secrets(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    token = _mailed(site, person)
    await _reset(site.http, token)
    [event] = await _audit(site, "auth.password_reset")
    assert (event.result, event.actor_id, event.subject_id) == ("success", person.id, person.id)
    assert token not in repr(event.details)
    assert NEW not in repr(event.details)

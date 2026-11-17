"""Sign-in codes and magic links (SPEC.md 14.2, 14.6, 14.10 and 14.12;
docs/contracts/auth-api.md; decision 0021): what the contract suite can't see
from outside, such as the stored rows, the audit, races and accounts that
change between the mail and its use. The contract suite
(`kernel/tests/contract/`) covers the answers, the expiries and the limits."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.app import create_app
from kernel.auth import floor
from kernel.auth.accounts import normal_email
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import AuditEvent, Token, Totp, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, Draining, make_config

_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
_PURPOSES = ("sign_in_code", "magic_link")


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
    #: The audit log is shared by every test: this one's rows come after it.
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        """Another browser: no cookies of its own yet."""
        transport = Draining(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    mail = CapturingMailer()
    app = create_app(config=make_config(database_url=migrated_url), mailer=mail)
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
    totp_secret: str | None = None


async def _person(site: Site, *roles: str, status: str = "active", totp: bool = False) -> Person:
    email = f"Kim.{uuid.uuid4().hex[:10]}@Site.test"
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            status=status,
            email_verified_at=clock.now(),
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
    return await http.post("/api/auth/code", json={"email": email})


async def _verify(http: httpx.AsyncClient, email: str, code: str) -> httpx.Response:
    return await http.post("/api/auth/code/verify", json={"email": email, "code": code})


async def _confirm(http: httpx.AsyncClient, token: str) -> httpx.Response:
    return await http.post("/api/auth/link/confirm", json={"token": token})


def _code(text: str) -> str:
    codes = re.findall(r"(?<![\w-])(\d{6})(?![\w-])", text)
    assert len(codes) == 1, text
    return str(codes[0])


def _link(text: str) -> str:
    links = [word for word in text.split() if "/auth/link?" in word]
    assert len(links) == 1, text
    assert links[0].startswith(f"{SITE}/auth/link?token="), links[0]
    return parse_qs(urlsplit(links[0].rstrip(".,)")).query)["token"][0]


async def _mailed(site: Site, person: Person) -> tuple[str, str]:
    """The code and the link token of the last message to the person."""
    text = site.mail.to(person.email)[-1].text
    return _code(text), _link(text)


async def _rows(site: Site, user_id: uuid.UUID) -> list[Token]:
    async with site.db() as db:
        found = await db.scalars(
            select(Token)
            .where(Token.user_id == user_id, Token.purpose.in_(_PURPOSES))
            .order_by(Token.created_at, Token.purpose)
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


async def _warm(site: Site, connections: int = 3) -> None:
    """Open the pool's connections before a race. On a cold pool the first
    requests wait for connections one by one and never overlap, so a race
    test would prove nothing (seen: without the row lock, asks at once sent
    three mails on a warm pool and one on a cold one)."""
    opened = [site.db() for _ in range(connections)]
    try:
        await asyncio.gather(*(db.execute(select(1)) for db in opened))
    finally:
        for db in opened:
            await db.close()


def _signed_in(response: httpx.Response) -> bool:
    cookies = response.headers.get_list("set-cookie")
    return response.status_code == 200 and any(c.startswith("__Host-dk_session=") for c in cookies)


# --- asking ---------------------------------------------------------------------


async def test_one_message_holds_the_code_and_the_link(site: Site) -> None:
    person = await _person(site)
    asked = await _ask(site.http, f"  {person.email.upper()} ")
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    [message] = site.mail.to(person.email)  # the account's own form of the address
    assert _code(message.text)
    assert _link(message.text)
    rows = await _rows(site, person.id)
    assert sorted(row.purpose for row in rows) == ["magic_link", "sign_in_code"]
    for row in rows:
        assert row.email_normal == normal_email(person.email)
        assert row.expires_at - row.created_at == timedelta(minutes=10)
        assert row.used_at is None
        assert row.attempts == 0


async def test_the_code_is_kept_keyed_over_its_purpose_owner_and_value(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    rows = {row.purpose: row for row in await _rows(site, person.id)}
    assert rows["sign_in_code"].token_hash == keyed_hash("sign_in_code", str(person.id), code)
    assert rows["sign_in_code"].token_hash != keyed_hash("sign_in_code", code)
    assert rows["magic_link"].token_hash == keyed_hash("magic_link", token)


@pytest.mark.parametrize(
    ("roles", "status"),
    [(("admin",), "active"), (("editor",), "active"), ((), "suspended"), ((), "deleted")],
)
async def test_staff_and_accounts_that_cant_sign_in_are_sent_nothing(
    site: Site, roles: tuple[str, ...], status: str
) -> None:
    person = await _person(site, *roles, status=status)
    asked = await _ask(site.http, person.email)
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    assert site.mail.to(person.email) == []
    assert await _rows(site, person.id) == []
    [event] = await _audit(site, "auth.code_sent")
    assert (event.result, event.subject_id) == ("refused", person.id)


async def test_an_unknown_address_is_sent_nothing_and_kept_nowhere(site: Site) -> None:
    unknown = f"nobody.{uuid.uuid4().hex[:10]}@site.test"
    asked = await _ask(site.http, unknown)
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    assert site.mail.to(unknown) == []
    [event] = await _audit(site, "auth.code_sent")
    assert (event.result, event.subject_id) == ("refused", None)
    assert "@" not in repr(event.details)


async def test_an_unknown_address_has_the_same_budget(site: Site) -> None:
    """A 429 says nothing either: an address with no account spends the same
    3 asks per 15 minutes as one with an account. Eight asks: under the IP's 10."""
    person = await _person(site)
    unknown = f"nobody.{uuid.uuid4().hex[:10]}@site.test"
    seen = {}
    for email in (person.email, unknown):
        answers = [await _ask(site.browser(), email) for _ in range(4)]
        seen[email] = [a.status_code for a in answers]
        assert answers[-1].json()["code"] == "kernel.rate_limited"
    assert seen[person.email] == seen[unknown] == [202, 202, 202, 429]


async def test_a_new_code_voids_the_last_code_and_link(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    old_code, old_link = await _mailed(site, person)
    clock.advance(61)
    await _ask(site.http, person.email)
    new_code, new_link = await _mailed(site, person)
    assert (new_code, new_link) != (old_code, old_link)
    if old_code != new_code:
        refused = await _verify(site.browser(), person.email, old_code)
        assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_code")
    gone = await _confirm(site.browser(), old_link)
    assert (gone.status_code, gone.json()["code"]) == (401, "auth.invalid_link")
    assert _signed_in(await _confirm(site.browser(), new_link))  # the control


async def test_a_resend_within_60_seconds_leaves_the_first_code_working(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, _ = await _mailed(site, person)
    clock.advance(59)
    await _ask(site.http, person.email)
    assert len(site.mail.to(person.email)) == 1
    assert len(await _rows(site, person.id)) == 2
    assert [e.result for e in await _audit(site, "auth.code_sent")] == ["success", "waiting"]
    assert _signed_in(await _verify(site.http, person.email, code))


async def test_asks_at_once_send_one_message(site: Site) -> None:
    """Three, the address's budget: the account row's lock, not the limit,
    keeps it to one message. Three rounds, nine asks: under the IP's 10."""
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        answers = await asyncio.gather(*(_ask(site.browser(), person.email) for _ in range(3)))
        assert [a.status_code for a in answers] == [202] * 3
        assert len(site.mail.to(person.email)) == 1
        assert len(await _rows(site, person.id)) == 2


async def test_a_failing_mailer_changes_nothing(site: Site) -> None:
    class Broken:
        async def send(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("the mail host is down")

    site.app.state.mailer.inner = Broken()
    person = await _person(site)
    asked = await _ask(site.http, person.email)
    assert (asked.status_code, asked.json()) == (202, {"status": "check_email"})
    assert len(await _rows(site, person.id)) == 2


async def test_asks_and_tries_answer_no_sooner_than_the_floor(site: Site) -> None:
    """The time says nothing about the account (14.6). A known address costs
    a few more queries than an unknown one, and a wrong try on a live code
    writes where a try on an unknown address doesn't: the floor hides both."""
    person = await _person(site)
    unknown = f"nobody.{uuid.uuid4().hex[:8]}@site.test"
    timed = [
        lambda: _ask(site.http, person.email),
        lambda: _ask(site.http, unknown),
        lambda: _verify(site.http, unknown, "123456"),
    ]
    for call in timed:
        started = time.perf_counter()
        await call()
        assert time.perf_counter() - started >= floor.ANSWER_FLOOR
    code, _ = await _mailed(site, person)
    started = time.perf_counter()
    await _verify(site.http, person.email, f"{(int(code) + 1) % 1_000_000:06d}")
    assert time.perf_counter() - started >= floor.ANSWER_FLOOR


# --- signing in with the code ------------------------------------------------------


async def test_a_right_code_signs_in_and_uses_up_the_link(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    signed = await _verify(site.http, person.email.lower(), code)
    assert _signed_in(signed)
    assert signed.json()["status"] == "signed_in"
    assert signed.json()["user"]["id"] == str(person.id)
    assert (await site.http.get("/api/auth/session")).status_code == 200
    late = await _confirm(site.browser(), token)
    assert (late.status_code, late.json()["code"]) == (401, "auth.invalid_link")
    [event] = await _audit(site, "auth.sign_in")
    assert (event.result, event.subject_id, event.details["method"]) == (
        "success",
        person.id,
        "code",
    )


async def test_each_try_counts_before_the_code_is_checked(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, _ = await _mailed(site, person)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(4):
        refused = await _verify(site.http, person.email, wrong)
        assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_code")
    [row] = [r for r in await _rows(site, person.id) if r.purpose == "sign_in_code"]
    assert row.attempts == 4
    assert _signed_in(await _verify(site.http, person.email, code))  # the fifth try may still win
    failures = await _audit(site, "auth.sign_in")
    assert [(e.result, e.subject_id) for e in failures[:4]] == [("failure", person.id)] * 4
    assert code not in repr([e.details for e in failures])
    assert wrong not in repr([e.details for e in failures])


@pytest.mark.parametrize(
    "code", ["12345", "1234567", "abcdef", "12 345", "", "\uff11\uff12\uff13\uff14\uff15\uff16"]
)
async def test_a_code_that_isnt_six_digits_is_refused_and_costs_no_try(
    site: Site, code: str
) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    refused = await _verify(site.http, person.email, code)
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_code")
    assert all(r.attempts == 0 for r in await _rows(site, person.id))


async def test_a_code_for_an_address_with_no_code_is_refused(site: Site) -> None:
    refused = await _verify(site.http, f"nobody.{uuid.uuid4().hex[:8]}@site.test", "123456")
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_code")


async def test_one_code_verified_twice_at_once_signs_in_once(site: Site) -> None:
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        await _ask(site.http, person.email)
        code, _ = await _mailed(site, person)
        answers = await asyncio.gather(
            *(_verify(site.browser(), person.email, code) for _ in range(3))
        )
        assert sorted(a.status_code for a in answers) == [200, 401, 401]


# --- signing in with the link ------------------------------------------------------


async def test_a_confirmed_link_signs_in_and_uses_up_the_code(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    signed = await _confirm(site.http, token)
    assert _signed_in(signed)
    assert signed.json()["user"]["id"] == str(person.id)
    late = await _verify(site.browser(), person.email, code)
    assert (late.status_code, late.json()["code"]) == (401, "auth.invalid_code")
    [event, *_] = await _audit(site, "auth.sign_in")
    assert (event.result, event.details["method"]) == ("success", "link")


@pytest.mark.parametrize("token", ["nonsense", "x" * 43, "", "x" * 128])
async def test_an_unknown_link_is_refused(site: Site, token: str) -> None:
    refused = await _confirm(site.http, token)
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_link")


async def test_one_link_confirmed_twice_at_once_signs_in_once(site: Site) -> None:
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        await _ask(site.http, person.email)
        _, token = await _mailed(site, person)
        answers = await asyncio.gather(*(_confirm(site.browser(), token) for _ in range(3)))
        assert sorted(a.status_code for a in answers) == [200, 401, 401]


async def test_the_code_and_the_link_used_at_once_sign_in_once(site: Site) -> None:
    """Each path takes the account row before its token's, so neither waits
    on a row the other holds: one signs in and the other is a 401, never a
    deadlock's 500 (Codex on #42)."""
    await _warm(site)
    for _ in range(4):
        person = await _person(site)
        await _ask(site.http, person.email)
        code, token = await _mailed(site, person)
        answers = await asyncio.gather(
            _verify(site.browser(), person.email, code), _confirm(site.browser(), token)
        )
        assert sorted(a.status_code for a in answers) == [200, 401]


async def test_a_new_ask_racing_a_right_code_never_fails(site: Site) -> None:
    """The ask locks the account row, then voids the mail; a verify takes the
    same row first too. The code signs in or has been voided: 200 or 401,
    and the ask is a 202, never a 500. Three rounds, six asks: under the IP's 10."""
    await _warm(site)
    for _ in range(3):
        person = await _person(site)
        await _ask(site.http, person.email)
        code, _ = await _mailed(site, person)
        clock.advance(61)  # past the resend wait, so the ask voids the mail
        verified, asked = await asyncio.gather(
            _verify(site.browser(), person.email, code), _ask(site.browser(), person.email)
        )
        assert verified.status_code in {200, 401}
        assert asked.status_code == 202


# --- the account changes after the mail ------------------------------------------


async def _change(site: Site, person: Person, **values: object) -> None:
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(**values))
        await db.commit()


async def test_an_account_made_staff_after_the_mail_isnt_signed_in(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    async with site.db() as db:
        db.add(UserRole(user_id=person.id, role_id="editor"))
        await db.commit()
    by_code = await _verify(site.http, person.email, code)
    by_link = await _confirm(site.http, token)
    assert (by_code.status_code, by_code.json()["code"]) == (401, "auth.invalid_code")
    assert (by_link.status_code, by_link.json()["code"]) == (401, "auth.invalid_link")
    assert not any(r.used_at for r in await _rows(site, person.id))  # nothing was used up


@pytest.mark.parametrize("status", ["suspended", "deleted"])
async def test_an_account_that_cant_sign_in_any_more_isnt_signed_in(
    site: Site, status: str
) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    await _change(site, person, status=status)
    assert (await _verify(site.http, person.email, code)).status_code == 401
    assert (await _confirm(site.http, token)).status_code == 401


async def test_a_mail_to_an_address_the_account_has_left_signs_nobody_in(site: Site) -> None:
    person = await _person(site)
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    moved = f"moved.{uuid.uuid4().hex[:8]}@site.test"
    await _change(site, person, email=moved, email_normal=moved)
    assert (await _verify(site.http, person.email, code)).status_code == 401
    assert (await _verify(site.http, moved, code)).status_code == 401
    assert (await _confirm(site.http, token)).status_code == 401


async def test_signing_in_by_code_cancels_a_pending_deletion(site: Site) -> None:
    person = await _person(site)
    await _change(site, person, status="deleting", deletion_due_at=clock.now() + timedelta(days=9))
    await _ask(site.http, person.email)
    code, _ = await _mailed(site, person)
    assert _signed_in(await _verify(site.http, person.email, code))
    async with site.db() as db:
        user = await db.get(User, person.id)
        assert user is not None
        assert (user.status, user.deletion_due_at) == ("active", None)


# --- a member with a second factor ---------------------------------------------


@pytest.mark.parametrize("by", ["code", "link"])
async def test_a_second_factor_is_still_asked_for(site: Site, by: str) -> None:
    """An email code or link is never a second factor (14.2): a member who has
    one still gives it."""
    person = await _person(site, totp=True)
    assert person.totp_secret
    await _ask(site.http, person.email)
    code, token = await _mailed(site, person)
    first = (
        await _verify(site.http, person.email, code)
        if by == "code"
        else await _confirm(site.http, token)
    )
    assert first.status_code == 200
    assert not _signed_in(first)
    body = first.json()
    assert (body["status"], body["methods"]) == ("second_factor", ["totp"])
    finished = await site.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": body["challenge"], "totp": pyotp.TOTP(person.totp_secret).now()},
    )
    assert _signed_in(finished)
    [event] = [e for e in await _audit(site, "auth.sign_in") if e.result == "success"]
    assert (event.details["method"], event.details["second_factor"]) == (by, True)
    # The mail is used up at the first step: it can't open a second challenge.
    again = await _verify(site.browser(), person.email, code)
    assert again.status_code == 401
    assert (await _confirm(site.browser(), token)).status_code == 401

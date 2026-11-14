"""Sign-up and email verification (SPEC.md 14.6, 14.7 and 14.10;
docs/contracts/auth-api.md): what the contract suite can't see from outside,
such as the stored rows, the audit, the site's modes and the mail limit. The
contract suite (`kernel/tests/contract/`) covers the answers it shares with
sign-in and reset."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.app import create_app
from kernel.auth import passwords
from kernel.auth.accounts import normal_email
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import AuditEvent, Token, User, UserRole
from kernel.config import KernelConfig
from kernel.email import CapturingMailer, Mailer

from ..conftest import SITE, Client, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
OTHER = "amber walrus cello 5528 dune"
LEAKED = "copper heron valley 2093 tide"
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
    #: Passwords the fake breach lookup reports; None makes it unreachable.
    breached: set[str] | None = field(default_factory=set)
    audit_from: int = 0

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    async def sign_up(self, email: str, password: str = PASSWORD, **more: Any) -> httpx.Response:
        return await self.http.post(
            "/api/auth/sign-up", json={"email": email, "password": password, **more}
        )

    async def verify(self, token: str) -> httpx.Response:
        return await self.http.post("/api/auth/verify-email", json={"token": token})

    async def user(self, email: str) -> User | None:
        async with self.db() as db:
            found: User | None = await db.scalar(
                select(User).where(User.email_normal == normal_email(email))
            )
            return found

    async def audit(self, action: str) -> list[AuditEvent]:
        async with self.db() as db:
            rows = await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.id > self.audit_from, AuditEvent.action == action)
                .order_by(AuditEvent.id)
            )
            return list(rows)


def _fake_lookup(site_holder: list[Site]) -> passwords.RangeLookup:
    """Have I Been Pwned's range answer, for the passwords the site lists."""

    async def lookup(prefix: str) -> str | None:
        listed = site_holder[0].breached
        if listed is None:
            return None
        lines = []
        for password in listed:
            digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
            if digest.startswith(prefix):
                lines.append(f"{digest[5:]}:3")
        return "\r\n".join(lines)

    return lookup


@asynccontextmanager
async def _site(url: str, *, mailer: Mailer | None = None, **config: Any) -> AsyncIterator[Site]:
    mail = CapturingMailer()
    holder: list[Site] = []
    app = create_app(
        config=make_config(database_url=url, **({"sign_up_mode": "open"} | config)),
        mailer=mailer or mail,
        breach_lookup=_fake_lookup(holder),
    )
    async with Client(app) as http:
        http.headers.update(_SAME_ORIGIN)
        site = Site(app, http, mail)
        holder.append(site)
        async with site.db() as db:
            site.audit_from = await db.scalar(select(func.max(AuditEvent.id))) or 0
        yield site


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    async with _site(migrated_url) as made:
        yield made


def _address(name: str = "Sam") -> str:
    return f"{name}.{uuid.uuid4().hex[:10]}@Site.test"


def _token(text: str) -> str:
    links = [word for word in text.split() if "/auth/verify?" in word]
    assert len(links) == 1, text
    assert links[0].startswith(f"{SITE}/auth/verify?token="), links[0]
    return parse_qs(urlsplit(links[0].rstrip(".,)")).query)["token"][0]


async def _person(site: Site, email: str, password: str = PASSWORD) -> User:
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            password_hash=await site.app.state.passwords.hash(password),
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id="member"))
        await db.commit()
        return user


# --- a new account ---------------------------------------------------------------


async def test_a_new_address_gets_an_unverified_member_account_and_a_link(site: Site) -> None:
    email = _address()
    response = await site.sign_up(f"  {email} ")
    assert (response.status_code, response.json()) == (202, {"status": "check_email"})
    assert "set-cookie" not in response.headers  # signing up signs nobody in

    user = await site.user(email)
    assert user is not None
    assert (user.email, user.email_normal, user.email_verified_at) == (email, email.lower(), None)
    assert user.status == "active"
    assert user.password_hash is not None
    assert user.password_hash.startswith("$argon2id$")
    assert await site.app.state.passwords.check(PASSWORD, user.password_hash)
    async with site.db() as db:
        roles = list(await db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)))
        tokens = list(await db.scalars(select(Token).where(Token.user_id == user.id)))
    assert roles == ["member"]

    [message] = site.mail.to(email)
    assert "DevKit site" in message.subject
    token = _token(message.text)
    [row] = tokens
    assert (row.purpose, row.email_normal, row.used_at) == ("verify_email", email.lower(), None)
    assert row.token_hash == keyed_hash("verify_email", token) != token
    assert row.expires_at - row.created_at == timedelta(hours=24)

    [event] = await site.audit("auth.sign_up")
    assert (event.result, event.subject_id, event.actor_id) == ("success", user.id, user.id)
    assert email.lower() not in str(event.details).lower()


async def test_the_link_verifies_the_address_once(site: Site) -> None:
    email = _address()
    await site.sign_up(email)
    token = _token(site.mail.to(email)[-1].text)

    first = await site.verify(token)
    assert (first.status_code, first.json()) == (200, {"status": "verified"})
    assert "set-cookie" not in first.headers  # nor does verifying
    user = await site.user(email)
    assert user is not None
    assert user.email_verified_at is not None
    [event] = await site.audit("auth.email_verified")
    assert (event.result, event.subject_id) == ("success", user.id)

    again = await site.verify(token)
    assert (again.status_code, again.json()["code"]) == (400, "auth.token_invalid")


async def test_a_get_on_the_link_verifies_nothing(site: Site) -> None:
    """A mail scanner following the link changes nothing: only the confirm
    page's POST verifies."""
    email = _address()
    await site.sign_up(email)
    token = _token(site.mail.to(email)[-1].text)
    assert (await site.http.get(f"/api/auth/verify-email?token={token}")).status_code == 405
    user = await site.user(email)
    assert user is not None
    assert user.email_verified_at is None
    assert (await site.verify(token)).status_code == 200


async def test_the_link_lasts_24_hours(site: Site) -> None:
    early, late = _address("Early"), _address("Late")
    await site.sign_up(early)
    await site.sign_up(late)
    clock.advance(24 * 3600 - 60)
    assert (await site.verify(_token(site.mail.to(early)[-1].text))).status_code == 200
    clock.advance(120)
    gone = await site.verify(_token(site.mail.to(late)[-1].text))
    assert (gone.status_code, gone.json()["code"]) == (400, "auth.token_invalid")
    user = await site.user(late)
    assert user is not None
    assert user.email_verified_at is None


@pytest.mark.parametrize("token", ["", "nope", "x" * 43, "é" * 43])
async def test_a_made_up_token_verifies_nothing(site: Site, token: str) -> None:
    response = await site.verify(token)
    assert (response.status_code, response.json()["code"]) == (400, "auth.token_invalid")


async def test_a_link_for_an_address_since_changed_verifies_nothing(site: Site) -> None:
    email, moved = _address(), _address("Moved")
    await site.sign_up(email)
    async with site.db() as db:
        await db.execute(
            update(User)
            .where(User.email_normal == email.lower())
            .values(email=moved, email_normal=moved.lower())
        )
        await db.commit()
    response = await site.verify(_token(site.mail.to(email)[-1].text))
    assert (response.status_code, response.json()["code"]) == (400, "auth.token_invalid")
    user = await site.user(moved)
    assert user is not None
    assert user.email_verified_at is None


async def test_a_deleted_account_is_not_verified(site: Site) -> None:
    email = _address()
    await site.sign_up(email)
    async with site.db() as db:
        await db.execute(
            update(User).where(User.email_normal == email.lower()).values(status="deleted")
        )
        await db.commit()
    response = await site.verify(_token(site.mail.to(email)[-1].text))
    assert (response.status_code, response.json()["code"]) == (400, "auth.token_invalid")


# --- an address that has an account ------------------------------------------------


async def test_a_known_address_is_sent_a_notice_and_keeps_its_password(site: Site) -> None:
    email = _address()
    person = await _person(site, email)
    response = await site.sign_up(f" {email.upper()} ", OTHER)
    assert (response.status_code, response.json()) == (202, {"status": "check_email"})

    user = await site.user(email)
    assert user is not None
    assert user.password_hash == person.password_hash
    async with site.db() as db:
        accounts = await db.scalar(
            select(func.count()).select_from(User).where(User.email_normal == email.lower())
        )
        tokens = await db.scalar(
            select(func.count()).select_from(Token).where(Token.user_id == person.id)
        )
    assert (accounts, tokens) == (1, 0)

    [notice] = site.mail.to(email)
    assert notice.to == email  # the account's own address, not the variant typed
    assert "/auth/verify" not in notice.text
    assert f"{SITE}/sign-in" in notice.text
    [event] = await site.audit("auth.sign_up")
    assert (event.result, event.subject_id, event.actor_id) == ("existing", person.id, None)


@pytest.mark.parametrize("known", [False, True])
async def test_either_way_one_password_is_hashed(site: Site, known: bool) -> None:
    """The time says nothing: an address that has an account costs the same
    Argon2 hash as a new one (14.6)."""
    email = _address()
    if known:
        await _person(site, email)
    passwords_ = site.app.state.passwords
    hashed = passwords_.hash
    calls: list[str] = []

    async def counting(password: str) -> str:
        calls.append(password)
        result: str = await hashed(password)
        return result

    passwords_.hash = counting
    try:
        assert (await site.sign_up(email, OTHER)).status_code == 202
    finally:
        del passwords_.hash
    assert calls == [OTHER]


async def test_sign_ups_at_once_for_one_address_make_one_account(site: Site) -> None:
    email = _address()
    answers = await asyncio.gather(*(site.sign_up(email) for _ in range(5)))
    assert [answer.status_code for answer in answers] == [202] * 5
    async with site.db() as db:
        made = await db.scalar(
            select(func.count()).select_from(User).where(User.email_normal == email.lower())
        )
    assert made == 1
    texts = [message.text for message in site.mail.to(email)]
    assert sum("/auth/verify?token=" in text for text in texts) == 1
    # The link, then notices until the address's budget of 3 is spent; one
    # more when notices racing ahead spent it before the link went.
    assert 3 <= len(texts) <= 4


async def test_past_3_mails_in_15_minutes_an_address_is_sent_no_more_notices(
    site: Site,
) -> None:
    email = _address()
    answers = [(await site.sign_up(email)).status_code for _ in range(5)]
    assert answers == [202] * 5
    assert len(site.mail.to(email)) == 3


async def test_the_link_goes_out_even_when_notices_spent_the_budget(site: Site) -> None:
    """Sign-ups racing the one that makes the account can find it made and
    spend the address's budget on notices before its link is sent: the link
    must still go, or the account could never be verified (Codex on #39)."""
    email = _address()
    for _ in range(3):
        await site.app.state.limiter.hit("3/15m", "auth.sign_up.mail", email.lower())
    assert (await site.sign_up(email)).status_code == 202
    [message] = site.mail.to(email)
    assert _token(message.text)


# --- what's refused ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("short one", passwords.TOO_SHORT),
        ("a" * 16, passwords.FEW_CHARACTERS),
        ("sunshine1234", passwords.COMMON),
    ],
)
async def test_a_refused_password_makes_nothing(site: Site, password: str, reason: str) -> None:
    email = _address()
    response = await site.sign_up(email, password)
    assert response.status_code == 422
    assert (response.json()["code"], response.json()["detail"]) == (
        "auth.password_rejected",
        reason,
    )
    assert await site.user(email) is None
    assert site.mail.to(email) == []


async def test_a_password_made_of_the_address_is_refused(site: Site) -> None:
    email = "marigold.hollow@site.test"
    response = await site.sign_up(email, "Marigold.Hollow@Site.test")
    assert response.status_code == 422
    assert response.json()["detail"] == passwords.ABOUT_THIS_SITE


async def test_a_breached_password_is_refused(site: Site) -> None:
    site.breached = {LEAKED}
    email = _address()
    response = await site.sign_up(email, LEAKED)
    assert response.status_code == 422
    assert response.json()["detail"] == passwords.BREACHED
    assert (await site.sign_up(email, PASSWORD)).status_code == 202


async def test_an_unreachable_breach_lookup_lets_the_password_through(site: Site) -> None:
    site.breached = None
    email = _address()
    assert (await site.sign_up(email, LEAKED)).status_code == 202
    assert await site.user(email) is not None


@pytest.mark.parametrize(
    "email", ["not-an-address", "two@at@site.test", "a b@site.test", "x" * 250 + "@site.test"]
)
async def test_a_malformed_address_is_refused(site: Site, email: str) -> None:
    response = await site.sign_up(email)
    assert (response.status_code, response.json()["code"]) == (422, "kernel.invalid_request")
    assert site.mail.to(email) == []


@pytest.mark.parametrize(
    ("mode", "code", "extra"),
    [
        ("closed", "auth.sign_up_closed", {}),
        ("invite", "auth.invite_required", {}),
        ("invite", "auth.invite_required", {"invite": "an-invite-we-never-made"}),
    ],
)
async def test_a_closed_or_invite_only_site_makes_no_account(
    migrated_url: str, mode: str, code: str, extra: dict[str, str]
) -> None:
    async with _site(migrated_url, sign_up_mode=mode) as site:
        email = _address()
        response = await site.sign_up(email, **extra)
        assert (response.status_code, response.json()["code"]) == (403, code)
        assert await site.user(email) is None
        assert site.mail.to(email) == []


def test_sign_up_is_closed_until_a_site_opens_it() -> None:
    assert KernelConfig.model_fields["sign_up_mode"].default == "closed"


# --- the mail ------------------------------------------------------------------------


class _Failing:
    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        raise RuntimeError(f"the provider refused {to}")


async def test_a_failing_mailer_changes_nothing(
    migrated_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    async with _site(migrated_url, mailer=_Failing()) as site:
        email = _address()
        with caplog.at_level(logging.WARNING, logger="kernel.auth.sign_up"):
            response = await site.sign_up(email)
        assert response.status_code == 202
        assert await site.user(email) is not None
        assert "RuntimeError" in caplog.text
        assert email.lower() not in caplog.text.lower()

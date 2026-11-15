"""TOTP setup and confirm (SPEC.md 14.3, 14.4 and 14.6; docs/contracts/auth-api.md;
decision 0026): what the contract suite can't see from outside, such as the
sealed secret, the keyed hashes, the audit, the mail, races and lock order."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass

import httpx
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.app import create_app
from kernel.auth.accounts import normal_email
from kernel.auth.models import AuditEvent, RecoveryCode, Totp, User, UserRole
from kernel.auth.second_factor import STEP, recovery_code_hash
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
_TOTP_ROW_FREE = "SELECT user_id FROM auth_totp WHERE user_id = :id FOR UPDATE NOWAIT"


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
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
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
    signed = await browser.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert signed.json()["status"] == "signed_in", signed.text
    return Person(user.id, email, browser)


async def _set_up(http: httpx.AsyncClient) -> str:
    response = await http.post("/api/auth/totp/setup")
    assert response.status_code == 200, response.text
    secret: str = response.json()["secret"]
    return secret


async def _confirm(http: httpx.AsyncClient, code: str) -> httpx.Response:
    return await http.post("/api/auth/totp/confirm", json={"code": code})


async def _totp(site: Site, person: Person) -> Totp | None:
    async with site.db() as db:
        found: Totp | None = await db.get(Totp, person.id)
        return found


async def _code_rows(site: Site, person: Person) -> list[RecoveryCode]:
    async with site.db() as db:
        found = await db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == person.id))
        return list(found)


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


# --- at rest --------------------------------------------------------------------------


async def test_the_secret_is_sealed_at_rest_and_confirmed_only_by_a_code(site: Site) -> None:
    person = await _person(site)
    secret = await _set_up(person.browser)
    row = await _totp(site, person)
    assert row is not None
    assert secret not in row.secret_sealed
    assert crypto.open(row.secret_sealed) == secret
    assert (row.confirmed_at, row.last_step) == (None, 0)
    code = pyotp.TOTP(secret).now()
    step = int(time.time() // STEP)
    assert (await _confirm(person.browser, code)).status_code == 200
    row = await _totp(site, person)
    assert row is not None
    assert row.confirmed_at is not None
    # The step the code matched, so it can't be taken again (the clock may
    # have moved on a step between the two lines above).
    assert row.last_step in {step, step + 1}
    assert pyotp.TOTP(secret).at(row.last_step * STEP) == code


async def test_recovery_codes_are_kept_as_keyed_hashes_only(site: Site) -> None:
    person = await _person(site)
    secret = await _set_up(person.browser)
    codes = (await _confirm(person.browser, pyotp.TOTP(secret).now())).json()["recovery_codes"]
    assert all(re.fullmatch(r"[0-9a-z]{5}-[0-9a-z]{5}", code) for code in codes), codes
    rows = await _code_rows(site, person)
    assert sorted(row.code_hash for row in rows) == sorted(
        recovery_code_hash(person.id, code) for code in codes
    )
    assert all(row.used_at is None for row in rows)
    stored = " ".join(row.code_hash for row in rows)
    assert not any(code.replace("-", "") in stored for code in codes)


async def test_confirming_replaces_any_older_recovery_codes(site: Site) -> None:
    """None should be left from an earlier TOTP; if one were, it goes."""
    person = await _person(site)
    stale = recovery_code_hash(person.id, "stale-codes")
    async with site.db() as db:
        db.add(RecoveryCode(user_id=person.id, code_hash=stale))
        await db.commit()
    secret = await _set_up(person.browser)
    codes = (await _confirm(person.browser, pyotp.TOTP(secret).now())).json()["recovery_codes"]
    rows = await _code_rows(site, person)
    assert len(rows) == 10
    assert stale not in {row.code_hash for row in rows}
    assert {row.code_hash for row in rows} == {recovery_code_hash(person.id, c) for c in codes}


async def test_the_secret_and_the_codes_are_never_cached(site: Site) -> None:
    person = await _person(site)
    setup = await person.browser.post("/api/auth/totp/setup")
    assert setup.headers.get("cache-control") == "no-store"
    confirmed = await _confirm(person.browser, pyotp.TOTP(setup.json()["secret"]).now())
    assert confirmed.headers.get("cache-control") == "no-store"


# --- audit and mail ---------------------------------------------------------------------


async def test_setup_and_confirm_are_audited_and_confirming_is_mailed(site: Site) -> None:
    person = await _person(site)
    site.mail.clear()
    secret = await _set_up(person.browser)
    assert site.mail.to(person.email) == []  # nothing is added yet
    assert (await _confirm(person.browser, pyotp.TOTP(secret).now())).status_code == 200
    [started] = await _audit(site, "auth.totp_setup_started")
    [confirmed] = await _audit(site, "auth.totp_confirmed")
    for row in (started, confirmed):
        assert (row.actor_id, row.subject_id, row.result) == (person.id, person.id, "success")
    [notice] = site.mail.to(person.email)
    assert "two-step" in notice.subject.lower()
    assert secret not in notice.text


async def test_a_wrong_code_is_audited_as_a_failed_step_up(site: Site) -> None:
    person = await _person(site)
    secret = await _set_up(person.browser)
    right = {pyotp.TOTP(secret).at(time.time() + drift) for drift in (-30, 0, 30)}
    wrong = next(code for code in ("000000", "111111", "222222") if code not in right)
    refused = await _confirm(person.browser, wrong)
    assert refused.json()["code"] == "auth.invalid_second_factor"
    [failure] = await _audit(site, "auth.step_up")
    assert (failure.subject_id, failure.result) == (person.id, "failure")
    assert await _audit(site, "auth.totp_confirmed") == []


# --- the address --------------------------------------------------------------------


async def test_an_address_unverified_since_setup_confirms_nothing(site: Site) -> None:
    """No pre-claiming an address (14.3) holds at confirm too, whatever moved
    the account's address since the setup."""
    person = await _person(site)
    secret = await _set_up(person.browser)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(email_verified_at=None))
        await db.commit()
    refused = await _confirm(person.browser, pyotp.TOTP(secret).now())
    assert (refused.status_code, refused.json()["code"]) == (403, "auth.email_unverified")
    row = await _totp(site, person)
    assert row is not None
    assert row.confirmed_at is None
    assert await _code_rows(site, person) == []


# --- lock order and races ------------------------------------------------------------


async def _with_the_account_held(
    site: Site,
    person: Person,
    requests: list[Callable[[], Awaitable[httpx.Response]]],
    probe: str | None = None,
    meanwhile: Callable[[AsyncSession], Awaitable[None]] | None = None,
) -> list[httpx.Response]:
    """Hold the account row, start every request, and wait until each is
    blocked on a lock, so they really overlap once it's let go. With `probe`
    (a NOWAIT lock on the TOTP row), check that none has taken that row
    while it waits: one that took it before the account's would hold it, and
    NOWAIT would fail. With `meanwhile`, make that change while holding the
    row and commit it, as a reset would. Then let go and give their answers."""
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
            if probe is not None:
                assert await watcher.scalar(text(probe), {"id": person.id}) == person.id
            if meanwhile is not None:
                await meanwhile(holder)
                await holder.commit()
        finally:  # let the requests finish either way, so nothing leaks
            await watcher.rollback()
            await holder.rollback()
            answers = await asyncio.gather(*running)
    return list(answers)


async def _new_epoch(db: AsyncSession, person: Person) -> None:
    """What a reset or a password change does to every session."""
    await db.execute(
        update(User).where(User.id == person.id).values(session_epoch=User.session_epoch + 1)
    )


async def test_a_confirm_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    """Whoever set up a TOTP with a stolen password can't confirm it once the
    owner's reset has ended their session, though the request was made
    before."""
    person = await _person(site)
    secret = await _set_up(person.browser)
    code = pyotp.TOTP(secret).now()
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: _confirm(person.browser, code)],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    row = await _totp(site, person)
    assert row is not None
    assert row.confirmed_at is None
    assert await _code_rows(site, person) == []


async def test_a_setup_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    person = await _person(site)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/totp/setup")],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert await _totp(site, person) is None


async def test_setting_up_locks_the_account_before_the_totp_row(site: Site) -> None:
    person = await _person(site)
    await _set_up(person.browser)  # a row to replace
    [again] = await _with_the_account_held(
        site, person, [lambda: person.browser.post("/api/auth/totp/setup")], _TOTP_ROW_FREE
    )
    assert again.status_code == 200, again.text


async def test_confirming_locks_the_account_before_the_totp_row(site: Site) -> None:
    person = await _person(site)
    secret = await _set_up(person.browser)
    code = pyotp.TOTP(secret).now()
    [confirmed] = await _with_the_account_held(
        site, person, [lambda: _confirm(person.browser, code)], _TOTP_ROW_FREE
    )
    assert confirmed.status_code == 200, confirmed.text


async def test_two_setups_at_once_both_answer_and_the_last_secret_stands(site: Site) -> None:
    """Without the account lock, both would find no row and both insert one:
    the second a 500 from the primary key."""
    person = await _person(site)
    other = site.browser()
    other.cookies = person.browser.cookies

    def setup(http: httpx.AsyncClient) -> Callable[[], Awaitable[httpx.Response]]:
        return lambda: http.post("/api/auth/totp/setup")

    answers = await _with_the_account_held(site, person, [setup(person.browser), setup(other)])
    assert [answer.status_code for answer in answers] == [200, 200], [a.text for a in answers]
    row = await _totp(site, person)
    assert row is not None
    assert crypto.open(row.secret_sealed) in {answer.json()["secret"] for answer in answers}


async def test_two_confirms_at_once_give_one_set_of_codes(site: Site) -> None:
    person = await _person(site)
    secret = await _set_up(person.browser)
    code = pyotp.TOTP(secret).now()
    other = site.browser()
    other.cookies = person.browser.cookies
    answers = await _with_the_account_held(
        site, person, [lambda: _confirm(person.browser, code), lambda: _confirm(other, code)]
    )
    assert sorted(answer.status_code for answer in answers) == [200, 409]
    [won] = [answer for answer in answers if answer.status_code == 200]
    rows = await _code_rows(site, person)
    assert {row.code_hash for row in rows} == {
        recovery_code_hash(person.id, c) for c in won.json()["recovery_codes"]
    }

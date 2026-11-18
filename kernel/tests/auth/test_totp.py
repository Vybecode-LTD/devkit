"""TOTP setup, confirm and removal, and new recovery codes (SPEC.md 14.3 to
14.6; docs/contracts/auth-api.md; decisions 0026 and 0027): what the contract
suite can't see from outside, such as the sealed secret, the keyed hashes,
the audit, the mail, races and lock order, sign-in's and step-up's included
(step-up by password too, which shares the route)."""

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
from kernel.auth.models import AuditEvent, RecoveryCode, Token, Totp, User, UserRole
from kernel.auth.second_factor import STEP, recovery_code_hash
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, Draining, make_config

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
    now = time.time()  # one reading, so the code and its step agree (CodeRabbit on #47)
    code, step = pyotp.TOTP(secret).at(now), int(now // STEP)
    assert (await _confirm(person.browser, code)).status_code == 200
    row = await _totp(site, person)
    assert row is not None
    assert row.confirmed_at is not None
    assert row.last_step == step  # the code's step, so it can't be taken again


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
    row_id: uuid.UUID | None = None,
) -> list[httpx.Response]:
    """Hold the account row, start every request, and wait until each is
    blocked on a lock, so they really overlap once it's let go. With `probe`
    (a NOWAIT lock on one row: the TOTP row, or `row_id`'s), check that none
    has taken that row while it waits: one that took it before the account's
    would hold it, and NOWAIT would fail. With `meanwhile`, make that change while holding the
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
                row = person.id if row_id is None else row_id
                assert await watcher.scalar(text(probe), {"id": row}) == row
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


# --- removing a TOTP and new recovery codes (decision 0027) ---------------------------

_CODE_ROW_FREE = "SELECT id FROM auth_recovery_code WHERE id = :id FOR UPDATE NOWAIT"


async def _with_totp(site: Site, person: Person) -> tuple[str, list[str]]:
    """A confirmed TOTP, set up over HTTP: its secret and recovery codes. The
    step of the code that confirmed it is used up."""
    secret = await _set_up(person.browser)
    confirmed = await _confirm(person.browser, pyotp.TOTP(secret).now())
    assert confirmed.status_code == 200, confirmed.text
    codes: list[str] = confirmed.json()["recovery_codes"]
    return secret, codes


def _next_step(secret: str) -> str:
    return pyotp.TOTP(secret).at(time.time() + 30)


async def _challenge(site: Site, person: Person) -> tuple[httpx.AsyncClient, str]:
    """A password sign-in on a new browser, waiting on its second factor."""
    browser = site.browser()
    started = await browser.post(
        "/api/auth/sign-in", json={"email": person.email, "password": PASSWORD}
    )
    assert started.json()["status"] == "second_factor", started.text
    return browser, started.json()["challenge"]


def _cookie(response: httpx.Response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


async def _tokens(site: Site, person: Person, purpose: str) -> list[Token]:
    async with site.db() as db:
        found = await db.scalars(
            select(Token).where(Token.user_id == person.id, Token.purpose == purpose)
        )
        return list(found)


async def test_removing_a_totp_deletes_it_and_its_codes_audited_and_mailed(site: Site) -> None:
    person = await _person(site)
    secret, _ = await _with_totp(site, person)
    site.mail.clear()
    removed = await person.browser.delete("/api/auth/totp")
    assert removed.status_code == 204
    assert await _totp(site, person) is None
    assert await _code_rows(site, person) == []
    [row] = await _audit(site, "auth.totp_removed")
    assert (row.actor_id, row.subject_id, row.result) == (person.id, person.id, "success")
    [notice] = site.mail.to(person.email)
    assert "off" in notice.subject.lower()
    assert secret not in notice.text


async def test_removing_a_totp_gives_this_browser_a_fresh_device_cookie(site: Site) -> None:
    """The epoch goes up, and the device cookie is signed over it: without a
    fresh one, this browser would be a stranger over the failure limit."""
    person = await _person(site)
    await _with_totp(site, person)
    removed = await person.browser.delete("/api/auth/totp")
    assert _cookie(removed, "__Host-mf_device")
    for _ in range(5):  # strangers push the address over its failure limit
        await site.browser().post(
            "/api/auth/sign-in", json={"email": person.email, "password": "a wrong password 1"}
        )
    right = {"email": person.email, "password": PASSWORD}
    assert (await site.browser().post("/api/auth/sign-in", json=right)).status_code == 429
    assert (await person.browser.post("/api/auth/sign-in", json=right)).status_code == 200


async def test_removing_a_totp_voids_open_sign_ins_and_mailed_ways_in(site: Site) -> None:
    person = await _person(site)
    secret, _ = await _with_totp(site, person)
    browser, challenge = await _challenge(site, person)
    asked = await site.browser().post("/api/auth/code", json={"email": person.email})
    assert asked.status_code == 202
    assert (await person.browser.delete("/api/auth/totp")).status_code == 204
    for purpose in ("second_factor", "sign_in_code"):
        rows = await _tokens(site, person, purpose)
        assert rows, purpose
        assert all(row.used_at is not None for row in rows), purpose
    late = await browser.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": _next_step(secret)}
    )
    assert late.status_code == 401


async def test_removing_a_setup_not_confirmed_ends_nothing(site: Site) -> None:
    person = await _person(site)
    await _set_up(person.browser)
    other = site.browser()
    signed = await other.post(
        "/api/auth/sign-in", json={"email": person.email, "password": PASSWORD}
    )
    assert signed.json()["status"] == "signed_in"
    site.mail.clear()
    assert (await person.browser.delete("/api/auth/totp")).status_code == 204
    assert await _totp(site, person) is None
    assert (await other.get("/api/auth/session")).status_code == 200
    assert site.mail.to(person.email) == []  # no factor was removed


async def test_removing_locks_the_account_before_the_totp_row(site: Site) -> None:
    person = await _person(site)
    await _with_totp(site, person)
    [removed] = await _with_the_account_held(
        site, person, [lambda: person.browser.delete("/api/auth/totp")], _TOTP_ROW_FREE
    )
    assert removed.status_code == 204, removed.text


async def test_a_removal_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    person = await _person(site)
    await _with_totp(site, person)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.delete("/api/auth/totp")],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert await _totp(site, person) is not None
    assert len(await _code_rows(site, person)) == 10


async def test_new_recovery_codes_are_keyed_hashes_never_cached_audited_and_mailed(
    site: Site,
) -> None:
    person = await _person(site)
    _, old = await _with_totp(site, person)
    site.mail.clear()
    made = await person.browser.post("/api/auth/recovery-codes")
    assert made.status_code == 200, made.text
    assert made.headers.get("cache-control") == "no-store"
    codes = made.json()["recovery_codes"]
    assert all(re.fullmatch(r"[0-9a-z]{5}-[0-9a-z]{5}", code) for code in codes), codes
    assert {row.code_hash for row in await _code_rows(site, person)} == {
        recovery_code_hash(person.id, code) for code in codes
    }
    assert not set(old) & set(codes)
    [row] = await _audit(site, "auth.recovery_codes_replaced")
    assert (row.actor_id, row.subject_id, row.result) == (person.id, person.id, "success")
    [notice] = site.mail.to(person.email)
    assert "recovery codes" in notice.subject.lower()
    assert not any(code in notice.text for code in codes)


async def test_new_recovery_codes_lock_the_account_before_the_old_rows(site: Site) -> None:
    person = await _person(site)
    await _with_totp(site, person)
    [first, *_] = await _code_rows(site, person)
    [made] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/recovery-codes")],
        _CODE_ROW_FREE,
        row_id=first.id,
    )
    assert made.status_code == 200, made.text


async def test_new_recovery_codes_give_way_to_a_reset_that_lands_first(site: Site) -> None:
    person = await _person(site)
    _, old = await _with_totp(site, person)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/recovery-codes")],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert {row.code_hash for row in await _code_rows(site, person)} == {
        recovery_code_hash(person.id, code) for code in old
    }


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [("DELETE", "/api/auth/totp", 204), ("POST", "/api/auth/recovery-codes", 409)],
)
async def test_after_a_role_change_the_answers_that_roll_back_carry_the_new_cookie(
    site: Site, method: str, path: str, status: int
) -> None:
    """With no TOTP, both let their transaction go; the session token the
    role change replaced still reaches the browser (Codex on #48)."""
    person = await _person(site)
    async with site.db() as db:
        await db.execute(
            update(User).where(User.id == person.id).values(role_version=User.role_version + 1)
        )
        await db.commit()
    old = person.browser.cookies.get("__Host-mf_session")
    response = await person.browser.request(method, path)
    assert response.status_code == status, response.text
    new = _cookie(response, "__Host-mf_session")
    assert new
    assert new != old
    assert (await person.browser.get("/api/auth/session")).status_code == 200


# --- sign-in and step-up take the account first too (decision 0027) ------------------


async def test_finishing_a_sign_in_with_a_totp_locks_the_account_before_the_totp_row(
    site: Site,
) -> None:
    """Removal holds the account, then deletes the TOTP row; a sign-in that
    took the row first, then waited for the account, would deadlock with it."""
    person = await _person(site)
    secret, _ = await _with_totp(site, person)
    browser, challenge = await _challenge(site, person)
    code = _next_step(secret)
    [finished] = await _with_the_account_held(
        site,
        person,
        [
            lambda: browser.post(
                "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": code}
            )
        ],
        _TOTP_ROW_FREE,
    )
    assert finished.json()["status"] == "signed_in", finished.text


async def test_finishing_a_sign_in_with_a_recovery_code_locks_the_account_first(
    site: Site,
) -> None:
    person = await _person(site)
    _, codes = await _with_totp(site, person)
    browser, challenge = await _challenge(site, person)
    [row] = [
        row
        for row in await _code_rows(site, person)
        if row.code_hash == recovery_code_hash(person.id, codes[0])
    ]
    [finished] = await _with_the_account_held(
        site,
        person,
        [
            lambda: browser.post(
                "/api/auth/sign-in/second-factor",
                json={"challenge": challenge, "recovery_code": codes[0]},
            )
        ],
        _CODE_ROW_FREE,
        row_id=row.id,
    )
    assert finished.json()["status"] == "signed_in", finished.text


async def test_stepping_up_with_a_totp_locks_the_account_before_the_totp_row(
    site: Site,
) -> None:
    person = await _person(site)
    secret, _ = await _with_totp(site, person)
    code = _next_step(secret)
    [stepped] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/step-up", json={"totp": code})],
        _TOTP_ROW_FREE,
    )
    assert stepped.status_code == 200, stepped.text


async def _step_up_successes(site: Site) -> list[AuditEvent]:
    return [row for row in await _audit(site, "auth.step_up") if row.result == "success"]


async def test_a_step_up_by_totp_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    """A reset that ends the session while a step-up waits on the account wins:
    the step-up answers 401 and its code's step isn't used up (CodeRabbit on
    #50, found for passkeys)."""
    person = await _person(site)
    secret, _ = await _with_totp(site, person)
    before = await _totp(site, person)
    assert before is not None
    code = _next_step(secret)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/step-up", json={"totp": code})],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert await _step_up_successes(site) == []
    after = await _totp(site, person)
    assert after is not None
    assert after.last_step == before.last_step  # the code can still be given


async def test_a_step_up_by_password_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    """The same for a password: it's checked before the lock, so a slow hash
    holds no row, and the session is looked at again once the lock is taken."""
    person = await _person(site)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/step-up", json={"password": PASSWORD})],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert await _step_up_successes(site) == []


async def test_two_step_ups_on_one_cookie_that_meet_at_the_account_issue_one_token(
    site: Site,
) -> None:
    """Looking at the session again under the lock mustn't take the winner's
    new token hash for the one this request came with: only the first
    replaces the token, the second answers 200 with no cookie, so the browser
    keeps the winner's whatever order the answers arrive in (Codex on #52)."""
    person = await _person(site)

    def step_up() -> Awaitable[httpx.Response]:
        return person.browser.post("/api/auth/step-up", json={"password": PASSWORD})

    answers = await _with_the_account_held(site, person, [step_up, step_up])
    assert [answer.status_code for answer in answers] == [200, 200]
    issued = [a for a in answers if "__Host-mf_session" in a.headers.get("set-cookie", "")]
    assert len(issued) == 1
    assert (await person.browser.get("/api/auth/session")).status_code == 200

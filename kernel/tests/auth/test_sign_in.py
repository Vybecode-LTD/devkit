"""Signing in and out, the second factor, the session and step-up (SPEC.md
14.4 to 14.6 and 14.10; docs/contracts/auth-api.md): what the contract suite
can't see from outside, such as the audit rows, the stored hash and the
security mail. The contract suite (`kernel/tests/contract/`) covers the rest."""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import timedelta

import httpx
import pyotp
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from fastapi import FastAPI
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.app import create_app
from kernel.auth import sessions
from kernel.auth.accounts import normal_email
from kernel.auth.models import (
    AuditEvent,
    Passkey,
    RecoveryCode,
    Session,
    Totp,
    User,
    UserRole,
)
from kernel.auth.second_factor import (
    check_totp,
    methods_of,
    recovery_code_hash,
    use_recovery_code,
)
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
WRONG = "a wrong password 1"
RECOVERY = "k7m2-p9x4-w3qa"
KERNEL_PERMISSIONS = {
    "auth.user.manage",
    "auth.user.suspend",
    "auth.role.assign",
    "auth.audit.read",
    "kernel.module.manage",
    "kernel.settings.manage",
}


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
        sessions_: AsyncSession = self.app.state.database.sessions()
        return sessions_

    def browser(self) -> httpx.AsyncClient:
        """Another browser: no cookies of its own yet."""
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    mail = CapturingMailer()
    app = create_app(config=make_config(database_url=migrated_url), mailer=mail)
    async with Client(app) as http:
        http.headers.update(_SAME_ORIGIN)
        site = Site(app, http, mail)
        async with site.db() as db:
            site.audit_from = await db.scalar(select(func.max(AuditEvent.id))) or 0
        yield site


@dataclass
class Person:
    id: uuid.UUID
    email: str
    totp_secret: str | None = None


async def _person(
    site: Site,
    *roles: str,
    password: str | None = PASSWORD,
    totp: bool = False,
    status: str = "active",
    password_hash: str | None = None,
) -> Person:
    email = f"Pat.{uuid.uuid4().hex[:10]}@Site.test"
    hashed = password_hash or (await site.app.state.passwords.hash(password) if password else None)
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            password_hash=hashed,
            status=status,
            email_verified_at=clock.now(),
            deletion_due_at=clock.now() + timedelta(days=14) if status == "deleting" else None,
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
            db.add(RecoveryCode(user_id=user.id, code_hash=recovery_code_hash(user.id, RECOVERY)))
        await db.commit()
        return Person(user.id, email, secret)


async def _sign_in(
    http: httpx.AsyncClient, person: Person, password: str = PASSWORD
) -> httpx.Response:
    return await http.post("/api/auth/sign-in", json={"email": person.email, "password": password})


async def _signed_in(http: httpx.AsyncClient, person: Person) -> None:
    body = (await _sign_in(http, person)).json()
    if body["status"] == "second_factor":
        assert person.totp_secret
        body = (
            await http.post(
                "/api/auth/sign-in/second-factor",
                json={"challenge": body["challenge"], "totp": pyotp.TOTP(person.totp_secret).now()},
            )
        ).json()
    assert body["status"] == "signed_in", body


def _cookie(response: httpx.Response, name: str) -> str:
    [header] = [v for v in response.headers.get_list("set-cookie") if v.startswith(f"{name}=")]
    return header


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        rows = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(rows)


# --- signing in ----------------------------------------------------------------


async def test_signing_in_answers_with_the_account_and_sets_both_cookies(site: Site) -> None:
    person = await _person(site)
    response = await _sign_in(site.http, person)
    assert response.status_code == 200, response.text
    user = {
        "id": str(person.id),
        "email": person.email,
        "roles": ["member"],
        "permissions": [],
        "verified": True,
        "second_factor": False,
    }
    assert response.json() == {"status": "signed_in", "user": user}
    for name in (sessions.SESSION_COOKIE, sessions.DEVICE_COOKIE):
        header = _cookie(response, name).lower()
        for attribute in ("httponly", "secure", "samesite=lax", "path=/"):
            assert attribute in header, (name, attribute)
        assert "domain=" not in header
    assert (await site.http.get("/api/auth/session")).json() == {"user": user}


async def test_the_address_is_matched_whatever_its_case_and_spaces(site: Site) -> None:
    person = await _person(site)
    response = await site.http.post(
        "/api/auth/sign-in", json={"email": f"  {person.email.upper()} ", "password": PASSWORD}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("status", ["suspended", "deleted"])
async def test_an_account_that_cant_sign_in_answers_as_a_wrong_password(
    site: Site, status: str
) -> None:
    blocked = await _person(site, status=status)
    active = await _person(site)
    refused = await _sign_in(site.http, blocked)
    wrong = await _sign_in(site.http, active, WRONG)
    assert refused.status_code == wrong.status_code == 401
    assert {k: v for k, v in refused.json().items() if k != "instance"} == {
        k: v for k, v in wrong.json().items() if k != "instance"
    }


async def test_signing_in_cancels_a_pending_deletion(site: Site) -> None:
    person = await _person(site, status="deleting")
    assert (await _sign_in(site.http, person)).status_code == 200
    async with site.db() as db:
        user = await db.get(User, person.id)
        assert user is not None
        assert (user.status, user.deletion_due_at) == ("active", None)


async def test_a_hash_with_other_parameters_is_redone_at_sign_in(site: Site) -> None:
    other = PasswordHasher(memory_cost=24 * 1024, time_cost=3, parallelism=2).hash(PASSWORD)
    person = await _person(site, password_hash=other)
    assert (await _sign_in(site.http, person)).status_code == 200
    async with site.db() as db:
        stored = (await db.get(User, person.id)).password_hash  # type: ignore[union-attr]
    assert stored
    assert stored != other
    assert not site.app.state.passwords.needs_rehash(stored)
    assert await site.app.state.passwords.check(PASSWORD, stored)


async def test_signing_in_ends_the_browsers_old_session(site: Site) -> None:
    person = await _person(site)
    await _signed_in(site.http, person)
    old = site.http.cookies.get(sessions.SESSION_COOKIE)
    await _signed_in(site.http, person)
    async with site.db() as db:
        found = await db.scalar(
            select(Session).where(Session.token_hash == sessions.hash_token(old or ""))
        )
    assert found is None


async def test_a_new_device_is_mailed_and_a_known_one_isnt(site: Site) -> None:
    person = await _person(site)
    await _signed_in(site.http, person)
    [notice] = site.mail.to(person.email)
    assert "new device" in notice.text
    assert not re.search(r"(?<!\d)\d{6}(?!\d)", notice.text)  # never mistaken for a code
    await site.http.post("/api/auth/sign-out")
    await _signed_in(site.http, person)  # the same browser: it holds the device cookie
    assert len(site.mail.to(person.email)) == 1
    async with site.browser() as other:
        await _signed_in(other, person)
    assert len(site.mail.to(person.email)) == 2


async def test_a_failing_mailer_doesnt_fail_the_sign_in(site: Site) -> None:
    class Broken:
        async def send(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("the mail host is down")

    site.app.state.mailer.inner = Broken()
    person = await _person(site)
    assert (await _sign_in(site.http, person)).status_code == 200


async def test_sign_ins_and_their_failures_are_audited(site: Site) -> None:
    person = await _person(site)
    await _sign_in(site.http, person, WRONG)
    await site.http.post("/api/auth/sign-in", json={"email": "nobody@site.test", "password": WRONG})
    await _sign_in(site.http, person)
    rows = await _audit(site, "auth.sign_in")
    assert [(r.result, r.subject_id) for r in rows] == [
        ("failure", person.id),
        ("failure", None),
        ("success", person.id),
    ]
    assert rows[-1].actor_id == person.id
    assert all(str(r.ip) == "127.0.0.1" for r in rows)
    assert "@" not in repr([r.details for r in rows])  # the typed address is never kept


async def test_an_owner_holds_every_permission_and_a_member_none(site: Site) -> None:
    for roles, expected in [
        (("owner",), KERNEL_PERMISSIONS),
        (("admin",), KERNEL_PERMISSIONS),
        (("member",), set()),
    ]:
        async with site.browser() as browser:
            person = await _person(site, *roles)
            user = (await _sign_in(browser, person)).json()["user"]
            assert set(user["permissions"]) >= expected, roles
            assert user["permissions"] == sorted(user["permissions"])
            if not expected:
                assert user["permissions"] == []


# --- the second factor ---------------------------------------------------------


async def test_an_unconfirmed_totp_asks_for_no_second_factor(site: Site) -> None:
    person = await _person(site)
    async with site.db() as db:
        db.add(Totp(user_id=person.id, secret_sealed=crypto.seal(pyotp.random_base32())))
        await db.commit()
    assert (await _sign_in(site.http, person)).json()["status"] == "signed_in"


async def test_a_second_factor_names_its_methods_and_is_recorded(site: Site) -> None:
    person = await _person(site, totp=True)
    first = (await _sign_in(site.http, person)).json()
    assert first["status"] == "second_factor"
    assert first["methods"] == ["totp", "recovery_code"]
    assert site.http.cookies.get(sessions.SESSION_COOKIE) is None  # not signed in yet
    assert person.totp_secret
    done = await site.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": first["challenge"], "totp": pyotp.TOTP(person.totp_secret).now()},
    )
    assert done.json()["user"]["second_factor"] is True
    async with site.db() as db:
        row = await db.scalar(select(Session).where(Session.user_id == person.id))
    assert row is not None
    assert row.second_factor_at is not None


async def test_a_recovery_code_works_once(site: Site) -> None:
    person = await _person(site, totp=True)
    for attempt in range(2):
        async with site.browser() as browser:
            challenge = (await _sign_in(browser, person)).json()["challenge"]
            response = await browser.post(
                "/api/auth/sign-in/second-factor",
                json={"challenge": challenge, "recovery_code": RECOVERY.upper().replace("-", " ")},
            )
            expected = (200, None) if attempt == 0 else (401, "auth.invalid_second_factor")
            assert (response.status_code, response.json().get("code")) == expected


async def test_a_challenge_lasts_10_minutes_and_works_once(site: Site) -> None:
    person = await _person(site, totp=True)
    late = (await _sign_in(site.http, person)).json()["challenge"]
    clock.advance(9 * 60)
    on_time = (await _sign_in(site.http, person)).json()["challenge"]
    clock.advance(61)  # `late` is 10 minutes and a second old; `on_time`, 61 seconds
    ended = await site.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": late, "recovery_code": RECOVERY}
    )
    assert (ended.status_code, ended.json()["code"]) == (401, "auth.challenge_ended")
    used = await site.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": on_time, "recovery_code": RECOVERY}
    )
    assert used.status_code == 200
    assert person.totp_secret
    again = await site.http.post(
        "/api/auth/sign-in/second-factor",
        json={"challenge": on_time, "totp": pyotp.TOTP(person.totp_secret).now()},
    )
    assert (again.status_code, again.json()["code"]) == (401, "auth.challenge_ended")


@pytest.mark.parametrize("challenge", ["nonsense", "x" * 43, ""])
async def test_an_unknown_challenge_has_ended(site: Site, challenge: str) -> None:
    response = await site.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "totp": "123456"}
    )
    assert (response.status_code, response.json()["code"]) == (401, "auth.challenge_ended")


@pytest.mark.parametrize(
    "body", [{"challenge": "c"}, {"challenge": "c", "totp": "123456", "recovery_code": "abc"}]
)
async def test_a_second_factor_takes_exactly_one_method(site: Site, body: dict[str, str]) -> None:
    response = await site.http.post("/api/auth/sign-in/second-factor", json=body)
    assert response.status_code == 422


async def test_second_factor_failures_are_limited_per_account(site: Site) -> None:
    """Five per sign-in end it; past 10 in an hour across sign-ins, the
    account takes no more guesses, so knowing the password isn't a way to
    guess codes for ever."""
    person = await _person(site, totp=True)
    answers = []
    for _ in range(3):
        async with site.browser() as browser:
            challenge = (await _sign_in(browser, person)).json()["challenge"]
            for _ in range(5):
                response = await browser.post(
                    "/api/auth/sign-in/second-factor",
                    json={"challenge": challenge, "recovery_code": "wrong-code-0000"},
                )
                answers.append(response.status_code)
    assert answers == [401] * 10 + [429] * 5
    rows = await _audit(site, "auth.second_factor")
    assert len(rows) == 10
    assert {(r.result, r.subject_id) for r in rows} == {("failure", person.id)}


# --- TOTP and recovery codes, directly -----------------------------------------


async def test_a_totp_code_counts_once_and_never_for_an_earlier_step(site: Site) -> None:
    person = await _person(site, totp=True)
    assert person.totp_secret
    totp = pyotp.TOTP(person.totp_secret)
    now = time.time()
    async with site.db() as db:
        assert await check_totp(db, person.id, totp.at(now - 30), at=now)  # one step of drift
        assert await check_totp(db, person.id, totp.at(now), at=now)
        assert not await check_totp(db, person.id, totp.at(now), at=now)  # replayed
        assert not await check_totp(db, person.id, totp.at(now - 30), at=now)  # earlier
        assert not await check_totp(db, person.id, totp.at(now + 60), at=now)  # beyond drift
        assert await check_totp(db, person.id, totp.at(now + 30), at=now)
        for bad in ("", "12345", "1234567", "abcdef", " 123456"):
            assert not await check_totp(db, person.id, bad, at=now)


async def test_an_unconfirmed_or_missing_totp_checks_nothing(site: Site) -> None:
    person = await _person(site)
    secret = pyotp.random_base32()
    async with site.db() as db:
        assert not await check_totp(db, person.id, pyotp.TOTP(secret).now())
        db.add(Totp(user_id=person.id, secret_sealed=crypto.seal(secret)))
        await db.commit()
        assert not await check_totp(db, person.id, pyotp.TOTP(secret).now())


async def test_a_recovery_code_is_only_its_owners(site: Site) -> None:
    mine, theirs = await _person(site, totp=True), await _person(site, totp=True)
    async with site.db() as db:
        assert not await use_recovery_code(db, theirs.id, "not-the-code")
        assert await use_recovery_code(db, mine.id, RECOVERY)
        assert not await use_recovery_code(db, mine.id, RECOVERY)
        await db.commit()
        assert await use_recovery_code(db, theirs.id, RECOVERY)


# --- step-up -------------------------------------------------------------------


async def test_stepping_up_with_a_totp(site: Site) -> None:
    person = await _person(site, totp=True)
    await _signed_in(site.http, person)
    clock.advance(11 * 60)
    before = site.http.cookies.get(sessions.SESSION_COOKIE)
    assert person.totp_secret
    code = pyotp.TOTP(person.totp_secret).at(time.time() + 30)  # the sign-in spent this step's
    response = await site.http.post("/api/auth/step-up", json={"totp": code})
    assert response.json() == {"status": "recent"}
    assert site.http.cookies.get(sessions.SESSION_COOKIE) not in {None, before}
    rows = await _audit(site, "auth.step_up")
    assert [r.result for r in rows] == ["success"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"password": WRONG}, "auth.invalid_credentials"),
        ({"totp": "000000"}, "auth.invalid_second_factor"),
    ],
)
async def test_a_wrong_step_up_is_refused(site: Site, body: dict[str, str], code: str) -> None:
    await _signed_in(site.http, await _person(site))
    response = await site.http.post("/api/auth/step-up", json=body)
    assert (response.status_code, response.json()["code"]) == (401, code)
    assert (await site.http.get("/api/auth/session")).status_code == 200  # still signed in


async def test_the_fifth_failed_step_up_ends_the_session_and_its_cookie(site: Site) -> None:
    await _signed_in(site.http, await _person(site))
    for _ in range(4):
        await site.http.post("/api/auth/step-up", json={"password": WRONG})
    fifth = await site.http.post("/api/auth/step-up", json={"password": WRONG})
    assert (fifth.status_code, fifth.json()["code"]) == (401, "kernel.not_signed_in")
    assert "max-age=0" in _cookie(fifth, sessions.SESSION_COOKIE).lower()
    assert (await _audit(site, "auth.session_ended"))[0].details == {"reason": "step_up_failures"}


async def test_step_up_needs_a_session_and_one_method(site: Site) -> None:
    refused = await site.http.post("/api/auth/step-up", json={"password": PASSWORD})
    assert (refused.status_code, refused.json()["code"]) == (401, "kernel.not_signed_in")
    await _signed_in(site.http, await _person(site))
    for body in ({}, {"password": PASSWORD, "totp": "123456"}):
        assert (await site.http.post("/api/auth/step-up", json=body)).status_code == 422


# --- signing out ----------------------------------------------------------------


async def test_signing_out_ends_the_session_and_keeps_the_device(site: Site) -> None:
    person = await _person(site)
    await _signed_in(site.http, person)
    response = await site.http.post("/api/auth/sign-out")
    assert response.status_code == 204
    assert "max-age=0" in _cookie(response, sessions.SESSION_COOKIE).lower()
    assert not [
        v for v in response.headers.get_list("set-cookie") if v.startswith(sessions.DEVICE_COOKIE)
    ]
    async with site.db() as db:
        assert await db.scalar(select(Session).where(Session.user_id == person.id)) is None
    rows = await _audit(site, "auth.sign_out")
    assert [(r.subject_id, r.result) for r in rows] == [(person.id, "success")]


async def test_signing_out_without_a_session_is_fine(site: Site) -> None:
    assert (await site.http.post("/api/auth/sign-out")).status_code == 204
    assert await _audit(site, "auth.sign_out") == []


# --- addresses -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "normal"),
    [("Pat@Site.Test", "pat@site.test"), ("  pat@site.test\t", "pat@site.test")],
)
def test_an_address_is_kept_trimmed_and_lowercased(typed: str, normal: str) -> None:
    assert normal_email(typed) == normal


# --- edges ------------------------------------------------------------------------


async def test_an_account_with_no_role_holds_nothing(site: Site) -> None:
    person = await _person(site)
    async with site.db() as db:
        await db.execute(delete(UserRole).where(UserRole.user_id == person.id))
        await db.commit()
    user = (await _sign_in(site.http, person)).json()["user"]
    assert (user["roles"], user["permissions"]) == ([], [])


async def test_an_account_suspended_before_its_second_factor_isnt_signed_in(site: Site) -> None:
    person = await _person(site, totp=True)
    challenge = (await _sign_in(site.http, person)).json()["challenge"]
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(status="suspended"))
        await db.commit()
    response = await site.http.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "recovery_code": RECOVERY}
    )
    assert (response.status_code, response.json()["code"]) == (401, "auth.challenge_ended")
    assert site.http.cookies.get(sessions.SESSION_COOKIE) is None
    async with site.db() as db:  # the code wasn't spent on a sign-in that didn't happen
        assert await use_recovery_code(db, person.id, RECOVERY)


async def test_the_methods_name_a_passkey_too(site: Site) -> None:
    with_totp, only_passkey = await _person(site, totp=True), await _person(site)
    async with site.db() as db:
        for person in (with_totp, only_passkey):
            db.add(
                Passkey(
                    user_id=person.id, credential_id=os.urandom(16), public_key=b"k", name="Laptop"
                )
            )
        await db.commit()
        assert await methods_of(db, with_totp.id) == ["totp", "recovery_code", "passkey"]
        assert await methods_of(db, only_passkey.id) == ["passkey"]


async def test_a_recovery_code_of_the_wrong_length_checks_nothing(site: Site) -> None:
    person = await _person(site, totp=True)
    async with site.db() as db:
        for code in ("", "abc-1234", "x" * 33):
            assert not await use_recovery_code(db, person.id, code)


def test_an_address_that_isnt_an_ip_is_audited_as_none() -> None:
    from fastapi import FastAPI
    from starlette.requests import Request

    from kernel.auth import audit

    app = FastAPI()
    app.state.client_ip_header = ""
    request = Request({"type": "http", "app": app, "headers": [(b"user-agent", b"x" * 400)]})
    added: list[AuditEvent] = []

    class Db:
        def add(self, row: AuditEvent) -> None:
            added.append(row)

    audit.record(Db(), request, "auth.sign_in", "failure")  # type: ignore[arg-type]
    [row] = added
    assert row.ip is None
    assert len(row.user_agent) == 300


async def test_a_step_up_right_after_a_role_change_sets_one_working_cookie(site: Site) -> None:
    """The role change gives this request a new token, then step-up replaces
    it again: only step-up's may reach the browser, or the dead one wins."""
    person = await _person(site)
    await _signed_in(site.http, person)
    async with site.db() as db:
        await db.execute(
            update(User).where(User.id == person.id).values(role_version=User.role_version + 1)
        )
        await db.commit()
    response = await site.http.post("/api/auth/step-up", json={"password": PASSWORD})
    assert response.status_code == 200
    cookies = [
        v for v in response.headers.get_list("set-cookie") if v.startswith(sessions.SESSION_COOKIE)
    ]
    assert len(cookies) == 1
    assert (await site.http.get("/api/auth/session")).status_code == 200


async def test_the_wait_grows_with_the_failures(site: Site) -> None:
    """Past 10 failures in an hour the wait is the hour's, not the quarter's
    (14.6): the windows run on real time, so the failures are counted here
    as the sign-in route counts them, without waiting 15 minutes between."""
    from kernel.auth.routes import _SIGN_IN_SCOPE, SIGN_IN_FAILURES

    person = await _person(site)
    limiter = site.app.state.limiter
    first = await _sign_in(site.http, person, WRONG)
    for _ in range(4):
        await _sign_in(site.http, person, WRONG)
    quarter = await _sign_in(site.http, person)
    assert first.status_code == 401
    assert quarter.status_code == 429
    assert int(quarter.headers["retry-after"]) <= 15 * 60
    for rule in SIGN_IN_FAILURES[1:]:  # five more, as after the quarter's window
        for _ in range(5):
            await limiter.hit(rule, _SIGN_IN_SCOPE, normal_email(person.email))
    hour = await _sign_in(site.http, person)
    assert hour.status_code == 429
    assert int(hour.headers["retry-after"]) > 15 * 60


async def test_an_owner_holds_the_kernels_permissions_though_no_role_grants_them(
    site: Site,
) -> None:
    """14.8: an owner holds every permission, whether or not a role still grants it."""
    from kernel.auth.accounts import permissions_of
    from kernel.auth.models import RolePermission

    owner = await _person(site, "owner")
    async with site.db() as db:  # never committed: the other tests keep the grant
        await db.execute(
            delete(RolePermission).where(RolePermission.permission == "auth.audit.read")
        )
        held = await permissions_of(
            db, owner.id, {"owner"}, declared=site.app.state.declared_permissions
        )
        await db.rollback()
    assert "auth.audit.read" in held


async def test_parallel_guesses_dont_outrun_the_accounts_budget(site: Site) -> None:
    """Each try takes its place in the hour's budget before its code is
    checked, so guesses sent at once over many sign-ins get 10 between them."""
    import asyncio

    person = await _person(site, totp=True)
    browsers = [site.browser() for _ in range(3)]
    challenges = [(await _sign_in(b, person)).json()["challenge"] for b in browsers]

    async def guess(browser: httpx.AsyncClient, challenge: str) -> int:
        response = await browser.post(
            "/api/auth/sign-in/second-factor",
            json={"challenge": challenge, "recovery_code": "wrong-code-0000"},
        )
        return response.status_code

    answers = await asyncio.gather(
        *(guess(b, c) for b, c in zip(browsers, challenges, strict=True) for _ in range(5))
    )
    for browser in browsers:
        await browser.aclose()
    assert sorted(answers) == [401] * 10 + [429] * 5


async def test_a_right_code_clears_the_accounts_failures(site: Site) -> None:
    """Three rounds of 4 wrong and 1 right: 12 failures in the hour, but
    each right code proves the account's owner is there."""
    person = await _person(site, totp=True)
    for _ in range(3):
        async with site.browser() as browser:
            challenge = (await _sign_in(browser, person)).json()["challenge"]
            for _ in range(4):
                await browser.post(
                    "/api/auth/sign-in/second-factor",
                    json={"challenge": challenge, "recovery_code": "wrong-code-0000"},
                )
            done = await browser.post(
                "/api/auth/sign-in/second-factor",
                json={"challenge": challenge, "recovery_code": RECOVERY},
            )
            assert done.status_code == 200
            async with site.db() as db:  # the next round may use the code again
                await db.execute(
                    update(RecoveryCode)
                    .where(RecoveryCode.user_id == person.id)
                    .values(used_at=None)
                )
                await db.commit()

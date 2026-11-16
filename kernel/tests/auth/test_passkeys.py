"""Passkeys (SPEC.md 14.2 to 14.6; docs/contracts/auth-api.md; decision 0028):
what the contract suite can't see from outside, such as what is kept, the
keyed challenges, the audit and the mail, the account checked again at each
step, races and lock order."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.app import create_app
from kernel.auth import ceremonies, second_factor
from kernel.auth.accounts import normal_email
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import AuditEvent, Passkey, Session, Token, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, make_config
from ..contract.authenticator import Authenticator, b64url

PASSWORD = "quiet orbit lantern 4471 marsh"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}
_PASSKEY_ROW_FREE = "SELECT id FROM auth_passkey WHERE id = :id FOR UPDATE NOWAIT"
REGISTER_START = "/api/auth/passkeys/register/start"
REGISTER_FINISH = "/api/auth/passkeys/register/finish"
PASSKEY_START = "/api/auth/passkeys/sign-in/start"
PASSKEY_FINISH = "/api/auth/passkeys/sign-in/finish"


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
    key: Authenticator


async def _person(site: Site, *, roles: tuple[str, ...] = ("member",)) -> Person:
    """A verified account, signed in a moment ago on a browser of its own."""
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
        for role in roles:
            db.add(UserRole(user_id=user.id, role_id=role))
        await db.commit()
    browser = site.browser()
    signed = await browser.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert signed.json()["status"] == "signed_in", signed.text
    return Person(user.id, email, browser, Authenticator(SITE))


async def _options(person: Person, name: str = "Laptop") -> dict[str, Any]:
    start = await person.browser.post(REGISTER_START, json={"name": name})
    assert start.status_code == 200, start.text
    options: dict[str, Any] = start.json()
    return options


async def _register(person: Person, name: str = "Laptop") -> dict[str, Any]:
    finish = await person.browser.post(
        REGISTER_FINISH, json=person.key.create(await _options(person, name))
    )
    assert finish.status_code == 201, finish.text
    made: dict[str, Any] = finish.json()
    return made


async def _sign_in(site: Site, person: Person, **knobs: Any) -> httpx.Response:
    browser = site.browser()
    start = await browser.post(PASSKEY_START)
    assert start.status_code == 200, start.text
    return await browser.post(PASSKEY_FINISH, json=person.key.get(start.json(), **knobs))


async def _passkeys(site: Site, person: Person) -> list[Passkey]:
    async with site.db() as db:
        found = await db.scalars(select(Passkey).where(Passkey.user_id == person.id))
        return list(found)


async def _audit(site: Site, action: str) -> list[AuditEvent]:
    async with site.db() as db:
        found = await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.id > site.audit_from)
            .order_by(AuditEvent.id)
        )
        return list(found)


async def _tokens(site: Site, purpose: str, person: Person) -> list[Token]:
    async with site.db() as db:
        found = await db.scalars(
            select(Token).where(Token.purpose == purpose, Token.user_id == person.id)
        )
        return list(found)


# --- what is kept -----------------------------------------------------------------------


async def test_a_passkey_keeps_its_credential_key_count_and_transports(site: Site) -> None:
    person = await _person(site)
    made = await _register(person, "Laptop")
    [row] = await _passkeys(site, person)
    held = person.key.credentials[0]
    assert (str(row.id), row.name, row.credential_id) == (made["id"], "Laptop", held.id)
    assert row.public_key  # the COSE key the authenticator gave
    assert (row.sign_count, sorted(row.transports), row.last_used_at) == (
        0,
        ["hybrid", "internal"],
        None,
    )


async def test_a_challenge_is_kept_only_as_a_keyed_hash_for_5_minutes(site: Site) -> None:
    person = await _person(site)
    options = await _options(person)
    [row] = await _tokens(site, ceremonies.REGISTER, person)
    assert row.token_hash == keyed_hash(ceremonies.REGISTER, options["challenge"])
    assert options["challenge"] not in str(row.data)
    assert row.user_id == person.id
    assert row.expires_at - row.created_at == ceremonies.LIFETIME
    async with site.db() as db:
        session_ids = list(await db.scalars(select(Session.id).where(Session.user_id == person.id)))
    assert row.data == {"name": "Laptop", "session": str(session_ids[0])}
    start = await site.browser().post(PASSKEY_START)
    hashed = keyed_hash(ceremonies.SIGN_IN, start.json()["challenge"])
    async with site.db() as db:
        anyone = await db.scalar(select(Token).where(Token.token_hash == hashed))
    assert anyone is not None
    assert (anyone.purpose, anyone.user_id) == (ceremonies.SIGN_IN, None)  # nobody known yet


async def test_options_are_never_cached(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    answers = [
        await person.browser.post(REGISTER_START, json={"name": "Phone"}),
        await site.browser().post(PASSKEY_START),
        await person.browser.post("/api/auth/step-up/passkey"),
    ]
    assert [answer.headers.get("cache-control") for answer in answers] == ["no-store"] * 3


async def test_the_relying_party_is_the_sites_and_debug_adds_the_dev_origins() -> None:
    config = make_config(site_url="https://Shop.Example.org/", cors_origins="http://localhost:5173")
    assert ceremonies.relying_party(config).id == "shop.example.org"
    assert ceremonies.relying_party(config).origins == ("https://shop.example.org",)
    debug = make_config(
        debug=True, site_url="http://localhost:8000", cors_origins="http://localhost:5173/"
    )
    assert ceremonies.relying_party(debug).origins == (
        "http://localhost:8000",
        "http://localhost:5173",
    )


@pytest.mark.parametrize("client_data", ["", "not base64!", b64url(b"not json"), b64url(b"{}")])
def test_unreadable_client_data_answers_no_challenge(client_data: str) -> None:
    assert ceremonies.answered(client_data) is None


# --- the account, checked again --------------------------------------------------------


async def test_an_address_unverified_since_the_start_adds_no_passkey(site: Site) -> None:
    person = await _person(site)
    options = await _options(person)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(email_verified_at=None))
        await db.commit()
    refused = await person.browser.post(REGISTER_FINISH, json=person.key.create(options))
    assert (refused.status_code, refused.json()["code"]) == (403, "auth.email_unverified")
    assert await _passkeys(site, person) == []


async def test_the_limit_holds_at_finish_too(site: Site) -> None:
    """Twenty starts at once can't finish into twenty-one passkeys."""
    person = await _person(site)
    early = await _options(person, "Early")
    for number in range(20):
        await _register(person, f"Key {number}")
    late = await person.browser.post(REGISTER_FINISH, json=person.key.create(early))
    assert (late.status_code, late.json()["code"]) == (409, "auth.too_many_passkeys")
    assert len(await _passkeys(site, person)) == 20


async def test_a_passkey_registered_already_isnt_added_twice(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    again = person.key.create(await _options(person, "Again"), credential=person.key.credentials[0])
    refused = await person.browser.post(REGISTER_FINISH, json=again)
    assert (refused.status_code, refused.json()["code"]) == (400, "auth.invalid_passkey")
    assert len(await _passkeys(site, person)) == 1


async def test_an_account_that_cant_sign_in_isnt_signed_in_by_its_passkey(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(status="suspended"))
        await db.commit()
    refused = await _sign_in(site, person)
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_passkey")


async def test_a_sign_in_with_no_user_handle_is_refused(site: Site) -> None:
    """A discoverable passkey names its account; one that doesn't proves nothing."""
    person = await _person(site)
    await _register(person)
    browser = site.browser()
    options = (await browser.post(PASSKEY_START)).json()
    answer = person.key.get(options)
    del answer["response"]["userHandle"]
    refused = await browser.post(PASSKEY_FINISH, json=answer)
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_passkey")


async def test_a_passkey_sign_in_is_two_factors_and_cancels_a_deletion(site: Site) -> None:
    person = await _person(site, roles=("editor",))
    await _register(person)
    async with site.db() as db:
        await db.execute(update(User).where(User.id == person.id).values(status="deleting"))
        await db.commit()
    signed = await _sign_in(site, person)
    assert signed.status_code == 200, signed.text
    async with site.db() as db:
        user = await db.get(User, person.id)
        newest = await db.scalar(
            select(Session).where(Session.user_id == person.id).order_by(Session.started_at.desc())
        )
    assert user is not None
    assert user.status == "active"
    assert newest is not None
    assert newest.second_factor_at is not None
    [row] = await _passkeys(site, person)
    assert row.last_used_at is not None


# --- audit and mail ---------------------------------------------------------------------


async def test_adding_renaming_and_removing_are_audited_and_mailed(site: Site) -> None:
    person = await _person(site)
    site.mail.clear()
    made = await _register(person, "Laptop")
    [added] = site.mail.to(person.email)
    assert "passkey was added" in added.subject.lower()
    renamed = await person.browser.patch(f"/api/auth/passkeys/{made['id']}", json={"name": "Odd"})
    assert renamed.status_code == 200
    assert len(site.mail.to(person.email)) == 1  # a name opens nothing: no mail
    assert (await person.browser.delete(f"/api/auth/passkeys/{made['id']}")).status_code == 204
    removed = site.mail.to(person.email)[-1]
    assert "passkey was removed" in removed.subject.lower()
    assert "Odd" not in removed.text  # whoever names a passkey chooses its words
    for action in ("auth.passkey_added", "auth.passkey_renamed", "auth.passkey_removed"):
        [row] = await _audit(site, action)
        assert (row.actor_id, row.subject_id, row.result) == (person.id, person.id, "success")
        assert row.details == {"passkey": made["id"]}


async def test_passkey_sign_ins_are_audited_with_their_method(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    assert (await _sign_in(site, person)).status_code == 200
    assert (await _sign_in(site, person, uv=False)).status_code == 401
    rows = [row for row in await _audit(site, "auth.sign_in") if row.details.get("method")]
    passkey = [(row.result, row.subject_id) for row in rows if row.details["method"] == "passkey"]
    assert passkey == [("success", person.id), ("failure", person.id)]
    success = next(row for row in rows if row.details["method"] == "passkey")
    assert success.details["second_factor"] is True


@pytest.mark.parametrize("name", ["Line\nbreak", "Tab\there", "Sep" + chr(0x2028) + "arator"])
async def test_a_name_holds_no_line_break_or_control_character(site: Site, name: str) -> None:
    person = await _person(site)
    refused = await person.browser.post(REGISTER_START, json={"name": name})
    assert (refused.status_code, refused.json()["code"]) == (422, "kernel.invalid_request")


# --- the second factor -----------------------------------------------------------------


async def test_passkey_options_keep_the_sign_ins_first_factor(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    browser = site.browser()
    first = await browser.post(
        "/api/auth/sign-in", json={"email": person.email, "password": PASSWORD}
    )
    challenge = first.json()["challenge"]
    options = await browser.post(
        "/api/auth/sign-in/second-factor/passkey", json={"challenge": challenge}
    )
    [row] = await _tokens(site, "second_factor", person)
    webauthn_challenge = options.json()["challenge"]
    assert set(row.data) == {"method", "passkey", "passkey_until"}
    assert row.data["method"] == "password"
    # Kept as a keyed hash, as every ceremony's challenge is, for 5 minutes.
    assert row.data["passkey"] == keyed_hash(second_factor.PASSKEY_PURPOSE, webauthn_challenge)
    assert webauthn_challenge not in str(row.data)
    until = datetime.fromisoformat(row.data["passkey_until"])
    assert until - clock.now() <= ceremonies.LIFETIME
    assert row.attempts == 0  # options cost no try


async def test_a_step_up_by_passkey_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    options = (await person.browser.post("/api/auth/step-up/passkey")).json()
    answer = person.key.get(options)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/step-up", json={"passkey": answer})],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    successes = [
        row
        for row in await _audit(site, "auth.step_up")
        if row.details.get("method") == "passkey" and row.result == "success"
    ]
    assert successes == []
    [row] = await _passkeys(site, person)
    assert row.last_used_at is None  # nothing of the step-up was written


async def test_another_accounts_passkey_is_no_second_factor(site: Site) -> None:
    person, other = await _person(site), await _person(site)
    await _register(person)
    await _register(other)
    browser = site.browser()
    first = await browser.post(
        "/api/auth/sign-in", json={"email": person.email, "password": PASSWORD}
    )
    challenge = first.json()["challenge"]
    options = (
        await browser.post("/api/auth/sign-in/second-factor/passkey", json={"challenge": challenge})
    ).json()
    theirs = other.key.get(options, credential=other.key.credentials[0])
    refused = await browser.post(
        "/api/auth/sign-in/second-factor", json={"challenge": challenge, "passkey": theirs}
    )
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_second_factor")
    [failure] = [
        row
        for row in await _audit(site, "auth.second_factor")
        if row.details.get("method") == "passkey"
    ]
    assert (failure.subject_id, failure.result) == (person.id, "failure")


# --- removal ------------------------------------------------------------------------------


async def test_removing_a_passkey_voids_every_other_way_in(site: Site) -> None:
    person = await _person(site)
    made = await _register(person)
    async with site.db() as db:
        for purpose in ("sign_in_code", "magic_link", "reset_password", "second_factor"):
            db.add(
                Token(
                    purpose=purpose,
                    token_hash=keyed_hash(purpose, uuid.uuid4().hex),
                    user_id=person.id,
                    email_normal=normal_email(person.email),
                    created_at=clock.now(),
                    expires_at=clock.now() + ceremonies.LIFETIME,
                )
            )
        await db.commit()
    removed = await person.browser.delete(f"/api/auth/passkeys/{made['id']}")
    assert removed.status_code == 204
    assert "__Host-dk_device" in removed.headers.get("set-cookie", "")  # over the new epoch
    async with site.db() as db:
        live = await db.scalar(
            select(func.count())
            .select_from(Token)
            .where(Token.user_id == person.id, Token.used_at.is_(None))
            .where(
                Token.purpose.in_(("sign_in_code", "magic_link", "reset_password", "second_factor"))
            )
        )
    assert live == 0
    assert (await person.browser.get("/api/auth/session")).status_code == 200


# --- lock order and races -----------------------------------------------------------------


async def _with_the_account_held(
    site: Site,
    person: Person,
    requests: list[Callable[[], Awaitable[httpx.Response]]],
    probe_row: uuid.UUID | None = None,
    meanwhile: Callable[[AsyncSession], Awaitable[None]] | None = None,
    waiting: int | None = None,
) -> list[httpx.Response]:
    """Hold the account row, start every request, and wait until each is
    blocked on a lock, so they really overlap once it's let go. With
    `probe_row`, check with NOWAIT that none took that passkey row first. With
    `meanwhile`, make that change while holding the row, as a reset would.
    `waiting` is how many must block, when not every request reaches the lock."""
    need = len(requests) if waiting is None else waiting
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
                if blocked >= need:
                    break
            assert blocked >= need, "the requests never all waited for the account row"
            if probe_row is not None:
                found = await watcher.scalar(text(_PASSKEY_ROW_FREE), {"id": probe_row})
                assert found == probe_row
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


async def test_one_registration_finished_twice_at_once_adds_one_passkey(site: Site) -> None:
    person = await _person(site)
    credential = person.key.create(await _options(person))
    answers = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post(REGISTER_FINISH, json=credential) for _ in range(2)],
    )
    assert sorted(answer.status_code for answer in answers) == [201, 400]
    assert len(await _passkeys(site, person)) == 1


async def test_one_assertion_sent_twice_at_once_signs_in_once(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    browser = site.browser()
    answer = person.key.get((await browser.post(PASSKEY_START)).json())
    [row] = await _passkeys(site, person)
    # The challenge is used up before the account is locked, so only the
    # request that took it waits; the other is refused at once.
    answers = await _with_the_account_held(
        site,
        person,
        [lambda: site.browser().post(PASSKEY_FINISH, json=answer) for _ in range(2)],
        probe_row=row.id,
        waiting=1,
    )
    assert sorted(a.status_code for a in answers) == [200, 401]


async def test_a_passkey_sign_in_locks_the_account_before_the_passkey(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    [row] = await _passkeys(site, person)
    browser = site.browser()
    answer = person.key.get((await browser.post(PASSKEY_START)).json())
    [signed] = await _with_the_account_held(
        site, person, [lambda: browser.post(PASSKEY_FINISH, json=answer)], probe_row=row.id
    )
    assert signed.status_code == 200, signed.text


async def test_a_removal_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    person = await _person(site)
    made = await _register(person)
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.delete(f"/api/auth/passkeys/{made['id']}")],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert len(await _passkeys(site, person)) == 1


async def test_a_registration_gives_way_to_a_reset_that_lands_first(site: Site) -> None:
    person = await _person(site)
    credential = person.key.create(await _options(person))
    [late] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post(REGISTER_FINISH, json=credential)],
        meanwhile=lambda db: _new_epoch(db, person),
    )
    assert (late.status_code, late.json()["code"]) == (401, "kernel.not_signed_in")
    assert await _passkeys(site, person) == []


async def test_a_step_up_by_passkey_locks_the_account_first(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    [row] = await _passkeys(site, person)
    options = (await person.browser.post("/api/auth/step-up/passkey")).json()
    answer = person.key.get(options)
    [stepped] = await _with_the_account_held(
        site,
        person,
        [lambda: person.browser.post("/api/auth/step-up", json={"passkey": answer})],
        probe_row=row.id,
    )
    assert stepped.status_code == 200, stepped.text
    [audited] = [
        r for r in await _audit(site, "auth.step_up") if r.details.get("method") == "passkey"
    ]
    assert audited.result == "success"


# --- what can't be read ---------------------------------------------------------------


async def test_a_malformed_sign_in_challenge_gets_no_passkey_options(site: Site) -> None:
    refused = await site.browser().post(
        "/api/auth/sign-in/second-factor/passkey", json={"challenge": "not-a-challenge"}
    )
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.challenge_ended")


async def test_expecting_a_passkey_on_an_ended_challenge_keeps_nothing(site: Site) -> None:
    life = ceremonies.LIFETIME
    async with site.db() as db:
        assert await second_factor.expect_passkey(db, "short", "x" * 43, lifetime=life) is False
        assert await second_factor.expect_passkey(db, "y" * 43, "x" * 43, lifetime=life) is False


async def test_a_credential_id_that_isnt_base64url_signs_nobody_in(site: Site) -> None:
    person = await _person(site)
    await _register(person)
    browser = site.browser()
    answer = person.key.get((await browser.post(PASSKEY_START)).json())
    answer["rawId"] = "not base64url!"
    refused = await browser.post(PASSKEY_FINISH, json=answer)
    assert (refused.status_code, refused.json()["code"]) == (401, "auth.invalid_passkey")


async def test_a_failing_mailer_changes_nothing(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    person = await _person(site)

    async def refuse(*_: object) -> None:
        raise ConnectionError("the mail host is down")

    monkeypatch.setattr(site.mail, "send", refuse)
    made = await _register(person)
    assert len(await _passkeys(site, person)) == 1
    assert (await person.browser.delete(f"/api/auth/passkeys/{made['id']}")).status_code == 204
    assert await _passkeys(site, person) == []

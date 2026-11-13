"""Sessions (SPEC.md 14.5): opaque tokens checked against the database on
every request, so any of them can be ended at once.

These are the service's own tests. The contract suite checks the same rules
over HTTP once the routes exist.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from kernel import clock
from kernel.auth import sessions
from kernel.auth.models import Session, User, UserRole
from kernel.db import Database

HOUR = 60 * 60
DAY = 24 * HOUR
CHROME_ON_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


async def _user(db: AsyncSession, *roles: str, status: str = "active") -> User:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@site.test"
    user = User(
        id=user_id,
        email=email,
        email_normal=email,
        status=status,
        session_epoch=0,
        role_version=0,
    )
    db.add(user)
    await db.flush()
    for role in roles or ("member",):
        db.add(UserRole(user_id=user_id, role_id=role))
    await db.commit()
    return user


async def _rows(db: AsyncSession, user: User) -> int:
    statement = select(func.count()).select_from(Session).where(Session.user_id == user.id)
    return (await db.execute(statement)).scalar_one()


async def _start(db: AsyncSession, user: User, **kwargs: Any) -> tuple[str, Session]:
    token, row = await sessions.start(db, user, user_agent=CHROME_ON_WINDOWS, **kwargs)
    await db.commit()
    return token, row


# --- tokens --------------------------------------------------------------------


async def test_a_token_is_32_random_bytes_and_only_its_hash_is_kept(db: AsyncSession) -> None:
    user = await _user(db)
    token, row = await _start(db, user)
    assert len(token) == 43  # 32 bytes, URL-safe base64, unpadded
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    stored = (await db.execute(select(Session).where(Session.id == row.id))).scalar_one()
    assert token not in {stored.token_hash, stored.device_label, stored.user_agent}


async def test_every_sign_in_gets_its_own_token(db: AsyncSession) -> None:
    user = await _user(db)
    first, _ = await _start(db, user)
    second, _ = await _start(db, user)
    assert first != second


async def test_an_unknown_empty_or_oversized_token_is_no_session(db: AsyncSession) -> None:
    await _start(db, await _user(db))
    for token in (None, "", "not-a-token", "x" * 5000):
        assert await sessions.resume(db, token) is None


async def test_a_session_keeps_who_it_is_and_from_where(db: AsyncSession) -> None:
    user = await _user(db)
    token, row = await _start(db, user, second_factor=True)
    resumed = await sessions.resume(db, token)
    assert resumed is not None
    assert (resumed.user.id, resumed.session.id) == (user.id, row.id)
    assert row.device_label == "Chrome on Windows"
    assert row.user_agent == CHROME_ON_WINDOWS
    assert row.second_factor_at == row.started_at == row.authenticated_at


async def test_the_user_agent_is_cut_to_300_characters(db: AsyncSession) -> None:
    user = await _user(db)
    _, row = await sessions.start(db, user, user_agent="A" * 1000)
    await db.commit()
    assert len(row.user_agent) == 300


# --- lifetimes -----------------------------------------------------------------


async def test_a_member_session_ends_after_14_idle_days(db: AsyncSession) -> None:
    token, _ = await _start(db, await _user(db))
    clock.advance(14 * DAY - 60)
    assert await sessions.resume(db, token) is not None  # and seen now
    clock.advance(14 * DAY + 60)  # 28 days in: inside the absolute limit
    assert await sessions.resume(db, token) is None


async def test_a_member_session_ends_after_30_days_however_busy(db: AsyncSession) -> None:
    token, row = await _start(db, await _user(db))
    assert row.expires_at == row.started_at + timedelta(days=30)
    for _ in range(29):
        clock.advance(DAY)
        assert await sessions.resume(db, token) is not None
    clock.advance(DAY + 60)
    assert await sessions.resume(db, token) is None


async def test_a_staff_session_ends_after_8_idle_hours(db: AsyncSession) -> None:
    token, _ = await _start(db, await _user(db, "editor"))
    clock.advance(8 * HOUR - 60)
    assert await sessions.resume(db, token) is not None
    clock.advance(8 * HOUR + 60)
    assert await sessions.resume(db, token) is None


async def test_a_staff_session_ends_after_7_days_however_busy(db: AsyncSession) -> None:
    token, row = await _start(db, await _user(db, "admin"))
    assert row.expires_at == row.started_at + timedelta(days=7)
    for _ in range(23):  # every 7 hours, to 161 hours
        clock.advance(7 * HOUR)
        assert await sessions.resume(db, token) is not None
    clock.advance(7 * HOUR + 60)  # 168 hours and a minute
    assert await sessions.resume(db, token) is None


async def test_lifetimes_come_from_the_caller(db: AsyncSession) -> None:
    short = sessions.Lifetimes(
        member=sessions.Lifetime(idle=timedelta(minutes=5), absolute=timedelta(hours=1)),
    )
    token, row = await _start(db, await _user(db), lifetimes=short)
    assert row.expires_at == row.started_at + timedelta(hours=1)
    clock.advance(6 * 60)
    assert await sessions.resume(db, token, lifetimes=short) is None


async def test_a_short_idle_limit_is_kept_alive_by_use(db: AsyncSession) -> None:
    """Visits are written often enough for any idle limit, not just hourly."""
    short = sessions.Lifetimes(
        member=sessions.Lifetime(idle=timedelta(minutes=5), absolute=timedelta(hours=1)),
    )
    token, _ = await _start(db, await _user(db), lifetimes=short)
    for _ in range(10):  # a request a minute, for ten minutes
        clock.advance(60)
        assert await sessions.resume(db, token, lifetimes=short) is not None


async def test_any_role_but_member_is_staff(db: AsyncSession) -> None:
    for roles, staff in ((("member",), False), (("owner",), True), (("member", "editor"), True)):
        user = await _user(db, *roles)
        assert await sessions.is_staff(db, user.id) is staff


async def test_last_seen_is_written_at_most_hourly(db: AsyncSession, database: Database) -> None:
    token, row = await _start(db, await _user(db))

    async def last_seen() -> datetime:
        async with database.sessions() as other:
            found = await other.execute(select(Session.last_seen_at).where(Session.id == row.id))
            return found.scalar_one()

    started = await last_seen()
    clock.advance(59 * 60)
    await sessions.resume(db, token)
    assert await last_seen() == started
    clock.advance(2 * 60)
    await sessions.resume(db, token)
    assert await last_seen() >= started + timedelta(minutes=61)  # written now


# --- ending sessions -----------------------------------------------------------


async def test_a_suspended_or_departing_account_has_no_session(db: AsyncSession) -> None:
    for status in ("suspended", "deleting", "deleted"):
        user = await _user(db)
        token, _ = await _start(db, user)
        user.status = status
        await db.commit()
        assert await sessions.resume(db, token) is None


async def test_ending_them_all_ends_every_session(db: AsyncSession) -> None:
    user = await _user(db)
    one, _ = await _start(db, user)
    two, _ = await _start(db, user)
    await sessions.end_all(db, user)
    await db.commit()
    assert user.session_epoch == 1
    assert await sessions.resume(db, one) is None
    assert await sessions.resume(db, two) is None
    assert await _rows(db, user) == 0


async def test_a_raised_epoch_ends_older_sessions_even_with_their_rows(db: AsyncSession) -> None:
    user = await _user(db)
    token, _ = await _start(db, user)
    user.session_epoch += 1  # as a suspension or a reset elsewhere does
    await db.commit()
    assert await sessions.resume(db, token) is None


async def test_a_password_change_keeps_this_session_and_ends_the_others(db: AsyncSession) -> None:
    user = await _user(db)
    mine, kept = await _start(db, user)
    theirs, _ = await _start(db, user)
    await sessions.end_all_but(db, user, kept)
    await db.commit()
    assert await sessions.resume(db, mine) is not None
    assert await sessions.resume(db, theirs) is None
    assert await _rows(db, user) == 1


async def test_signing_out_ends_only_that_session(db: AsyncSession) -> None:
    user = await _user(db)
    mine, _ = await _start(db, user)
    theirs, _ = await _start(db, user)
    await sessions.end_by_token(db, mine)
    await sessions.end_by_token(db, "not-a-token")
    await sessions.end_by_token(db, None)  # no cookie: nothing to end
    await db.commit()
    assert await sessions.resume(db, mine) is None
    assert await sessions.resume(db, theirs) is not None


async def test_one_session_can_be_ended_only_by_its_account(db: AsyncSession) -> None:
    user, stranger = await _user(db), await _user(db)
    token, row = await _start(db, user)
    assert await sessions.end(db, stranger, row.id) is False
    assert await sessions.resume(db, token) is not None
    assert await sessions.end(db, user, row.id) is True
    await db.commit()
    assert await sessions.resume(db, token) is None


async def test_signing_out_everywhere_else_keeps_this_one(db: AsyncSession) -> None:
    user = await _user(db)
    mine, kept = await _start(db, user)
    theirs, _ = await _start(db, user)
    await sessions.end_others(db, user, kept.id)
    await db.commit()
    assert await sessions.resume(db, mine) is not None
    assert await sessions.resume(db, theirs) is None
    assert user.session_epoch == 0  # nothing else changes


async def test_the_list_shows_live_sessions_most_recent_first(db: AsyncSession) -> None:
    user = await _user(db)
    old, older_row = await _start(db, user)
    clock.advance(2 * HOUR)
    _, newer_row = await _start(db, user)
    ended, ended_row = await _start(db, user)
    await sessions.end_by_token(db, ended)
    await db.commit()
    listed = await sessions.live_of(db, user)
    assert [row.id for row in listed] == [newer_row.id, older_row.id]
    clock.advance(2 * HOUR)
    await sessions.resume(db, old)  # seen again: first now
    listed = await sessions.live_of(db, user)
    assert [row.id for row in listed] == [older_row.id, newer_row.id]
    assert ended_row.id not in {row.id for row in listed}


async def test_a_sign_in_clears_the_accounts_ended_sessions(db: AsyncSession) -> None:
    user = await _user(db)
    await _start(db, user)
    clock.advance(31 * DAY)
    await _start(db, user)
    assert await _rows(db, user) == 1


# --- new tokens ----------------------------------------------------------------


async def test_a_role_change_issues_a_new_token_and_kills_the_old(db: AsyncSession) -> None:
    user = await _user(db)
    old, _ = await _start(db, user)
    user.role_version += 1
    await db.commit()
    resumed = await sessions.resume(db, old)
    assert resumed is not None
    assert resumed.token not in {None, old}
    assert await sessions.resume(db, old) is None
    again = await sessions.resume(db, resumed.token)
    assert again is not None
    assert again.token is None  # nothing to replace this time


async def test_a_member_made_staff_gets_staff_limits(db: AsyncSession) -> None:
    user = await _user(db)
    old, row = await _start(db, user)
    db.add(UserRole(user_id=user.id, role_id="editor"))
    user.role_version += 1
    await db.commit()
    resumed = await sessions.resume(db, old)
    assert resumed is not None
    assert resumed.staff is True
    assert resumed.session.expires_at == row.started_at + timedelta(days=7)
    clock.advance(8 * HOUR + 60)
    assert await sessions.resume(db, resumed.token) is None


async def test_requests_racing_a_role_change_issue_one_token(
    db: AsyncSession, database: Database
) -> None:
    user = await _user(db)
    old, _ = await _start(db, user)
    user.role_version += 1
    await db.commit()

    async def one_request() -> sessions.Resumed | None:
        async with database.sessions() as request_db:
            return await sessions.resume(request_db, old)

    results = await asyncio.gather(*(one_request() for _ in range(4)))
    issued = [result.token for result in results if result is not None and result.token]
    assert len(issued) == 1
    assert await sessions.resume(db, old) is None
    assert await sessions.resume(db, issued[0]) is not None


async def test_a_request_that_loses_the_race_carries_on_without_a_token(
    db: AsyncSession, database: Database
) -> None:
    """The other request's update holds the row; this one reads the old hash,
    waits on the lock, then finds the hash gone: it issues nothing."""
    user = await _user(db)
    old, row = await _start(db, user)
    user.role_version += 1
    await db.commit()

    async def waiting_on_a_lock() -> bool:
        async with database.sessions() as watcher:
            found = await watcher.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            return bool(found.scalar_one())

    async with database.sessions() as winner:
        await winner.execute(
            update(Session).where(Session.id == row.id).values(token_hash="f" * 64)
        )
        async with database.sessions() as loser_db:
            loser = asyncio.create_task(sessions.resume(loser_db, old))
            for _ in range(500):
                if await waiting_on_a_lock():
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("the request never waited on the row")
            await winner.commit()
            result = await loser
    assert result is not None
    assert result.token is None
    assert await sessions.resume(db, old) is None


async def test_step_up_without_a_second_factor_leaves_that_record(db: AsyncSession) -> None:
    user = await _user(db)
    _, row = await _start(db, user)
    await sessions.step_up(db, row)
    await db.commit()
    assert row.second_factor_at is None


async def test_step_up_replaces_the_token_and_makes_the_sign_in_recent(db: AsyncSession) -> None:
    user = await _user(db)
    old, row = await _start(db, user)
    assert sessions.recent(row)
    clock.advance(11 * 60)
    resumed = await sessions.resume(db, old)
    assert resumed is not None
    assert not sessions.recent(resumed.session)
    new = await sessions.step_up(db, resumed.session, second_factor=True)
    await db.commit()
    assert new != old
    assert await sessions.resume(db, old) is None
    stepped = await sessions.resume(db, new)
    assert stepped is not None
    assert sessions.recent(stepped.session)
    assert stepped.session.second_factor_at == stepped.session.authenticated_at


# --- devices -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        (CHROME_ON_WINDOWS, "Chrome on Windows"),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Mobile Safari/537.36 EdgA/130.0.0.0",
            "Edge on Android",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Firefox on Mac",
        ),
        ("Mozilla/5.0 Firefox/131.0", "Firefox"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "A browser on Windows"),
        ("curl/8.0", "An unknown device"),
        ("", "An unknown device"),
    ],
)
def test_a_device_is_named_from_its_user_agent(agent: str, label: str) -> None:
    assert sessions.device_label(agent) == label


def _transient(epoch: int = 0) -> User:
    return User(id=uuid.uuid4(), session_epoch=epoch, role_version=0)


def test_a_device_cookie_counts_for_its_own_account_only() -> None:
    mine, theirs = _transient(), _transient()
    value = sessions.device_token(mine)
    assert sessions.knows_device(value, mine)
    assert not sessions.knows_device(value, theirs)
    assert not sessions.knows_device(sessions.device_token(theirs), mine)


@pytest.mark.parametrize(
    "value", [None, "", "forged", "a.b", "é" * 30 + "." + "0" * 64, "x" * 5000]
)
def test_a_forged_or_garbled_device_cookie_counts_for_nobody(value: str | None) -> None:
    assert not sessions.knows_device(value, _transient())


def test_a_raised_epoch_makes_every_device_a_stranger_again() -> None:
    user = _transient()
    value = sessions.device_token(user)
    user.session_epoch += 1
    assert not sessions.knows_device(value, user)


# --- cookies -------------------------------------------------------------------


def _set_cookie(response: Response) -> str:
    headers = [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]
    assert len(headers) == 1
    return headers[0]


def test_the_session_cookie_is_host_only_http_only_secure_and_lax() -> None:
    now = clock.now()
    row = Session(expires_at=now + timedelta(days=30))
    response = Response()
    sessions.set_session_cookie(response, "the-token", row)
    cookie = _set_cookie(response)
    assert cookie.startswith("__Host-dk_session=the-token;")
    for part in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", f"Max-Age={30 * DAY}"):
        assert part in cookie
    assert "Domain" not in cookie


def test_clearing_the_session_cookie_repeats_its_attributes() -> None:
    response = Response()
    sessions.clear_session_cookie(response)
    cookie = _set_cookie(response)
    assert cookie.startswith("__Host-dk_session=")
    for part in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=0"):
        assert part in cookie


def test_the_device_cookie_is_its_own_cookie_and_lasts_a_year() -> None:
    response = Response()
    sessions.set_device_cookie(response, _transient())
    cookie = _set_cookie(response)
    assert cookie.startswith("__Host-dk_device=")
    for part in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", f"Max-Age={365 * DAY}"):
        assert part in cookie

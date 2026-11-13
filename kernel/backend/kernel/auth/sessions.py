"""Web sessions (SPEC.md 14.5), lifted from VybeSite's `services/sessions.py`
and `services/members.py`, onto one `auth_user` table and its roles.

**A session is a random token in an HttpOnly cookie** (`__Host-dk_session`),
and the database keeps only the token's SHA-256, one row per signed-in
browser. A copy of the table signs nobody in, no page script can read the
cookie, and deleting a row ends that session at once.

**A session counts** while every one of these holds:

- its row exists, whatever the cookie says;
- the account is `active` (a suspension or a pending deletion ends it);
- its `epoch` is still the account's `session_epoch`, which goes up on a
  password change, a reset, a second-factor reset or a suspension;
- it was seen within the idle limit, and started within the absolute limit:
  14 and 30 days for members, 8 hours and 7 days for staff (any role but
  `member`). A member made staff gets staff limits from then on.

**A new token** replaces the old at sign-in (`start`), at step-up
(`step_up`) and after a role change: `role_version` goes up, and the
session's next request (`resume`) gets a new token for the caller to set,
while the old one stops working. When requests race that change, one of
them issues the token; the others carry on without one, and any that
arrives after it is no longer signed in.

`last_seen_at` is written at most hourly, or every eighth of a shorter idle
limit, so use keeps any session alive. `start` and the `end…` calls run
in the caller's transaction, which the caller commits; `resume` commits
what it changes itself, before the response sets a cookie that relies on it.

Every time comes from `kernel.clock`, so the contract suite can move it.
"""

from __future__ import annotations

import hashlib
import math
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from starlette.responses import Response

from kernel import clock
from kernel.auth.hashing import keyed_hash, same
from kernel.auth.models import Session, User, UserRole

SESSION_COOKIE = "__Host-dk_session"
#: A browser that has signed in to an account before (14.5, decision 0013).
#: Never the session: signing out keeps it.
DEVICE_COOKIE = "__Host-dk_device"
DEVICE_DAYS = 365

#: The longest gap between writes of `last_seen_at`. An hour either way
#: doesn't matter to an 8-hour idle limit, and it spares a write on every
#: request. A shorter idle limit writes more often (`Lifetime.touch_every`).
TOUCH_EVERY = timedelta(hours=1)
#: The share of the idle limit a visit may go unwritten: an eighth, as an
#: hour is of the staff's 8 hours, so every limit keeps the same margin.
_TOUCH_SHARE = 8
#: How recent a sign-in must be for `require_recent_auth` (14.4).
RECENT = timedelta(minutes=10)

_USER_AGENT_CHARS = 300
#: `secrets.token_urlsafe(32)` is 43 characters; anything far longer is no
#: token of ours and isn't worth hashing.
_TOKEN_CHARS = 128
_DEVICE_VALUE = re.compile(r"([A-Za-z0-9_-]{16,64})\.([0-9a-f]{64})")
_ACTIVE = "active"


# --- lifetimes ---------------------------------------------------------------


@dataclass(frozen=True)
class Lifetime:
    """How long a session may sit unused, and how long it may last at all."""

    idle: timedelta
    absolute: timedelta

    @property
    def touch_every(self) -> timedelta:
        """How often a visit is written: hourly, or an eighth of a shorter idle
        limit, so a session in use never runs out between writes."""
        return min(TOUCH_EVERY, self.idle / _TOUCH_SHARE)


@dataclass(frozen=True)
class Lifetimes:
    """The site's limits (SPEC.md 14.5's table, and site settings per Q6)."""

    member: Lifetime = Lifetime(idle=timedelta(days=14), absolute=timedelta(days=30))
    staff: Lifetime = Lifetime(idle=timedelta(hours=8), absolute=timedelta(days=7))

    def of(self, staff: bool) -> Lifetime:
        return self.staff if staff else self.member


DEFAULT_LIFETIMES = Lifetimes()


# --- tokens ------------------------------------------------------------------


def hash_token(token: str) -> str:
    """A session token's SHA-256, in hex: all the database keeps of it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """A new session token, 32 random bytes, and its hash."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def _plausible(token: str | None) -> bool:
    return isinstance(token, str) and 0 < len(token) <= _TOKEN_CHARS


# --- the device's name -------------------------------------------------------

# Tried in this order: Edge and Opera say Chrome too, Chrome says Safari, and
# Chrome on an iPhone says CriOS.
_BROWSERS = (
    ("Edge", re.compile(r"\bEdg(e|A|iOS)?/")),
    ("Opera", re.compile(r"\bOPR/")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/")),
    ("Firefox", re.compile(r"\b(Firefox|FxiOS)/")),
    ("Chrome", re.compile(r"\b(Chrome|CriOS)/")),
    ("Safari", re.compile(r"\bVersion/[\d.]+.*\bSafari/")),
)
# Phones name other systems too ("like Mac OS X", "Linux"), so they come first.
_SYSTEMS = (
    ("iPhone", re.compile(r"\biPhone\b")),
    ("iPad", re.compile(r"\biPad\b")),
    ("Android", re.compile(r"\bAndroid\b")),
    ("ChromeOS", re.compile(r"\bCrOS\b")),
    ("Windows", re.compile(r"\bWindows\b")),
    ("Mac", re.compile(r"\bMacintosh\b")),
    ("Linux", re.compile(r"\bLinux\b")),
)


def device_label(user_agent: str) -> str:
    """What the account page calls a session: "Chrome on Android"."""
    agent = (user_agent or "")[:500]
    browser = next((name for name, pattern in _BROWSERS if pattern.search(agent)), "")
    system = next((name for name, pattern in _SYSTEMS if pattern.search(agent)), "")
    if browser and system:
        return f"{browser} on {system}"
    if browser:
        return browser
    if system:
        return f"A browser on {system}"
    return "An unknown device"


# --- known devices -----------------------------------------------------------
#
# Over an account's failure limit (14.6), the right password still signs in
# on a browser that has signed in to that account before, and is refused
# anywhere else just as a wrong one is. So strangers typing wrong passwords
# can't lock the owner out of their own browsers. Each sign-in hands the
# browser a random nonce signed (`keyed_hash`, under SECRET_KEY) with the
# account's id and its session epoch: nothing is stored, a cookie counts for
# its own account alone, and raising the epoch (a reset, a new password, a
# suspension) makes every browser a stranger until it signs in again. A route
# that raises the epoch on a browser that stays signed in should hand it a
# fresh cookie.


def _device_mac(user: User, nonce: str) -> str:
    return keyed_hash("known_device", str(user.id), str(user.session_epoch), nonce)


def device_token(user: User) -> str:
    """The device cookie's value for a browser that just signed in to `user`."""
    nonce = secrets.token_urlsafe(16)
    return f"{nonce}.{_device_mac(user, nonce)}"


def knows_device(value: str | None, user: User | None) -> bool:
    """Whether a device cookie's value was handed to a browser signed in to
    `user`, at its current epoch."""
    if not value or user is None or len(value) > 200:
        return False
    match = _DEVICE_VALUE.fullmatch(value)
    if match is None:
        return False
    nonce, mac = match.groups()
    return same(mac, _device_mac(user, nonce))


# --- cookies -----------------------------------------------------------------
#
# `Secure; HttpOnly; Path=/` and no `Domain`, so the `__Host-` prefix holds and
# no other host shares them. SameSite=Lax, so arriving from an emailed link or
# a provider's redirect finds the person signed in; every write is still
# refused cross-site by the Origin check.


def _set(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max(0, max_age),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def set_session_cookie(response: Response, token: str, session: Session) -> None:
    """The session cookie, lasting until the session's absolute end."""
    seconds = (session.expires_at - clock.now()).total_seconds()
    _set(response, SESSION_COOKIE, token, math.ceil(seconds))


def clear_session_cookie(response: Response) -> None:
    """Drop the session cookie, with the attributes it was set with: a browser
    keeps a `__Host-` cookie whose removal lacks them."""
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def set_device_cookie(response: Response, user: User) -> None:
    """Mark this browser as one that has signed in to `user`, for a year."""
    _set(response, DEVICE_COOKIE, device_token(user), DEVICE_DAYS * 24 * 60 * 60)


# --- which limits apply ------------------------------------------------------


def _staff_clause(user_id: Any) -> Any:
    return (
        select(UserRole.role_id)
        .where(UserRole.user_id == user_id, UserRole.role_id != "member")
        .exists()
    )


async def is_staff(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether the account holds any role but `member` (14.1)."""
    return bool((await db.execute(select(_staff_clause(user_id)))).scalar())


def _deadline(session: Session, life: Lifetime) -> datetime:
    """The absolute end: the stored one, or sooner for a member made staff."""
    return min(session.expires_at, session.started_at + life.absolute)


def is_live(
    session: Session,
    user: User,
    *,
    staff: bool,
    now: datetime | None = None,
    lifetimes: Lifetimes = DEFAULT_LIFETIMES,
) -> bool:
    """Whether a session still counts (the module's list)."""
    now = now or clock.now()
    life = lifetimes.of(staff)
    return (
        user.status == _ACTIVE
        and session.epoch == user.session_epoch
        and _deadline(session, life) > now
        and session.last_seen_at + life.idle > now
    )


def recent(session: Session, *, within: timedelta = RECENT, now: datetime | None = None) -> bool:
    """Whether the session signed in or stepped up within `within` (14.4)."""
    return (now or clock.now()) - session.authenticated_at <= within


# --- starting and resuming ---------------------------------------------------


async def start(
    db: AsyncSession,
    user: User,
    *,
    user_agent: str,
    second_factor: bool = False,
    lifetimes: Lifetimes = DEFAULT_LIFETIMES,
) -> tuple[str, Session]:
    """A new session for this browser: its token, for the cookie, and its row.
    `second_factor` records that the sign-in used one. The account's ended
    sessions are cleared at the same time, so its list stays short without a
    pass of its own. The caller commits."""
    now = clock.now()
    life = lifetimes.of(await is_staff(db, user.id))
    await db.execute(
        delete(Session).where(
            Session.user_id == user.id,
            (Session.epoch != user.session_epoch)
            | (Session.expires_at <= now)
            | (Session.last_seen_at <= now - life.idle),
        )
    )
    token, token_hash = new_token()
    agent = (user_agent or "")[:_USER_AGENT_CHARS]
    row = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        epoch=user.session_epoch,
        role_version=user.role_version,
        started_at=now,
        last_seen_at=now,
        expires_at=now + life.absolute,
        authenticated_at=now,
        second_factor_at=now if second_factor else None,
        user_agent=agent,
        device_label=device_label(agent),
    )
    db.add(row)
    await db.flush()
    return token, row


@dataclass
class Resumed:
    """A live session, its account, whether staff limits apply, and the new
    token to set when this request replaced the old one."""

    session: Session
    user: User
    staff: bool
    token: str | None = None


async def resume(
    db: AsyncSession,
    token: str | None,
    *,
    lifetimes: Lifetimes = DEFAULT_LIFETIMES,
) -> Resumed | None:
    """The live session a cookie's token is for, or None. After a role change
    it replaces the token (`Resumed.token`, for the caller to set); otherwise
    it records the visit (`Lifetime.touch_every`). Either is committed here."""
    if not _plausible(token):
        return None
    old_hash = hash_token(cast(str, token))
    statement = (
        select(Session, User, _staff_clause(Session.user_id).label("staff"))
        .join(User, User.id == Session.user_id)
        .where(Session.token_hash == old_hash)
        .execution_options(populate_existing=True)
    )
    found = (await db.execute(statement)).first()
    if found is None:
        return None
    session, user, staff = found[0], found[1], bool(found[2])
    now = clock.now()
    if not is_live(session, user, staff=staff, now=now, lifetimes=lifetimes):
        return None
    if session.role_version != user.role_version:
        return await _reissue(db, session, user, staff, old_hash, now, lifetimes)
    if now - session.last_seen_at >= lifetimes.of(staff).touch_every:
        session.last_seen_at = now
        await db.commit()
    return Resumed(session, user, staff)


async def _reissue(
    db: AsyncSession,
    session: Session,
    user: User,
    staff: bool,
    old_hash: str,
    now: datetime,
    lifetimes: Lifetimes,
) -> Resumed:
    """Replace a token after a role change. Only the request whose update
    still finds the old hash issues the new token."""
    token, token_hash = new_token()
    values = {
        "token_hash": token_hash,
        "role_version": user.role_version,
        "expires_at": _deadline(session, lifetimes.of(staff)),
        "last_seen_at": now,
    }
    result = await db.execute(
        update(Session)
        .where(Session.id == session.id, Session.token_hash == old_hash)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    won = cast(CursorResult[Any], result).rowcount == 1
    await db.commit()
    if not won:
        return Resumed(session, user, staff)
    for name, value in values.items():
        set_committed_value(session, name, value)
    return Resumed(session, user, staff, token)


async def step_up(db: AsyncSession, session: Session, *, second_factor: bool = False) -> str | None:
    """A fresh sign-in on this session (14.4): a new token, returned for the
    cookie, and the sign-in time reset. The caller commits.

    Only a request that still finds the session's old token replaces it. One
    that loses to another step-up of the same session (a double click) gets
    None: the session is already freshly signed in, so the caller answers as
    for success and sets no cookie, and the browser keeps the winner's."""
    now = clock.now()
    token, token_hash = new_token()
    values: dict[str, Any] = {
        "token_hash": token_hash,
        "authenticated_at": now,
        "last_seen_at": now,
    }
    if second_factor:
        values["second_factor_at"] = now
    result = await db.execute(
        update(Session)
        .where(Session.id == session.id, Session.token_hash == session.token_hash)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        return None
    for name, value in values.items():
        set_committed_value(session, name, value)
    return token


# --- listing and ending ------------------------------------------------------


async def live_of(
    db: AsyncSession, user: User, *, lifetimes: Lifetimes = DEFAULT_LIFETIMES
) -> list[Session]:
    """The account's sessions that still count, the most recently seen first."""
    now = clock.now()
    staff = await is_staff(db, user.id)
    rows = await db.execute(
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.last_seen_at.desc(), Session.started_at.desc())
    )
    return [
        row
        for row in rows.scalars()
        if is_live(row, user, staff=staff, now=now, lifetimes=lifetimes)
    ]


async def _delete(db: AsyncSession, *where: Any) -> int:
    result = await db.execute(delete(Session).where(*where))
    return cast(CursorResult[Any], result).rowcount or 0


async def end(db: AsyncSession, user: User, session_id: uuid.UUID) -> bool:
    """End one of the account's sessions: False when it has none by that id."""
    return await _delete(db, Session.user_id == user.id, Session.id == session_id) > 0


async def end_by_token(db: AsyncSession, token: str | None) -> None:
    """End the session a cookie's token is for, live or not (sign-out)."""
    if _plausible(token):
        await _delete(db, Session.token_hash == hash_token(cast(str, token)))


async def end_others(db: AsyncSession, user: User, keep: uuid.UUID) -> None:
    """End every session the account has but `keep` ("sign out everywhere else")."""
    await _delete(db, Session.user_id == user.id, Session.id != keep)


async def _raise_epoch(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(session_epoch=User.session_epoch + 1)
        .returning(User.session_epoch)
        .execution_options(synchronize_session=False)
    )
    epoch = int(result.scalar_one())
    set_committed_value(user, "session_epoch", epoch)
    return epoch


async def end_all(db: AsyncSession, user: User) -> None:
    """End every session of the account: a reset, a second-factor reset or a
    suspension (14.5). The epoch goes up, so a session can't outlive this
    even if its row is missed."""
    await _raise_epoch(db, user)
    await _delete(db, Session.user_id == user.id)


async def end_all_but(db: AsyncSession, user: User, keep: Session) -> None:
    """A password change: every other session ends, and `keep` carries on at
    the account's new epoch."""
    epoch = await _raise_epoch(db, user)
    await db.execute(
        update(Session)
        .where(Session.id == keep.id)
        .values(epoch=epoch)
        .execution_options(synchronize_session=False)
    )
    set_committed_value(keep, "epoch", epoch)
    await _delete(db, Session.user_id == user.id, Session.id != keep.id)


__all__ = [
    "DEFAULT_LIFETIMES",
    "DEVICE_COOKIE",
    "SESSION_COOKIE",
    "Lifetime",
    "Lifetimes",
    "Resumed",
    "clear_session_cookie",
    "device_label",
    "device_token",
    "end",
    "end_all",
    "end_all_but",
    "end_by_token",
    "end_others",
    "hash_token",
    "is_live",
    "is_staff",
    "knows_device",
    "live_of",
    "new_token",
    "recent",
    "resume",
    "set_device_cookie",
    "set_session_cookie",
    "start",
    "step_up",
]

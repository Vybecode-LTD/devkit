"""The second factor at sign-in and step-up (SPEC.md 14.4 and 14.6).

**TOTP** (RFC 6238, pyotp): 6 digits, 30-second steps, one step of drift
either way. A code counts only for a confirmed TOTP, and only once: the step
it matched is stored, and a code for that step or an earlier one is refused,
by an update that only one of two racing requests can make. TOTP runs on
real time (`time.time()`), never `kernel.clock`: the codes come from the
person's authenticator app, whose clock is the world's.

**Recovery codes:** each kept as a keyed hash over the account and the code,
compared after dropping case, spaces and hyphens, and used at most once (an
update that only one request can make).

**The challenge** a sign-in waits on once the password has passed: 32 random
bytes, kept as a keyed hash in `auth_token` (purpose `second_factor`), valid
10 minutes and single use. Each try is counted before the code is checked, by
an update that refuses a sixth, so racing requests get 5 tries between them,
never more.
"""

from __future__ import annotations

import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

import pyotp
from sqlalchemy import CursorResult, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import Passkey, RecoveryCode, Token, Totp, User

STEP = 30
DRIFT = 1
CHALLENGE_LIFETIME = timedelta(minutes=10)
CHALLENGE_TRIES = 5
_CODE = re.compile(r"[0-9]{6}")
#: `secrets.token_urlsafe(32)` is 43 characters.
_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")
_PURPOSE = "second_factor"


def _rows(result: Any) -> int:
    return cast(CursorResult[Any], result).rowcount


# --- TOTP -----------------------------------------------------------------------


async def check_totp(
    db: AsyncSession, user_id: uuid.UUID, code: str, *, at: float | None = None
) -> bool:
    """Whether `code` is the account's confirmed TOTP for a step not yet used,
    within one step of `at` (now). Records the step; the caller commits."""
    if not _CODE.fullmatch(code):
        return False
    totp = await db.scalar(
        select(Totp).where(Totp.user_id == user_id, Totp.confirmed_at.is_not(None))
    )
    if totp is None:
        return False
    generator = pyotp.TOTP(crypto.open(totp.secret_sealed))
    current = int((time.time() if at is None else at) // STEP)
    matched = [
        step
        for step in range(current - DRIFT, current + DRIFT + 1)
        if hmac.compare_digest(generator.at(step * STEP), code)
    ]
    if not matched:
        return False
    step = max(matched)
    result = await db.execute(
        update(Totp)
        .where(Totp.user_id == user_id, Totp.last_step < step)
        .values(last_step=step)
        .execution_options(synchronize_session=False)
    )
    return _rows(result) == 1


# --- recovery codes -------------------------------------------------------------


def normal_recovery_code(code: str) -> str:
    return "".join(character for character in code.lower() if character.isalnum())


def recovery_code_hash(user_id: uuid.UUID, code: str) -> str:
    return keyed_hash("recovery_code", str(user_id), normal_recovery_code(code))


async def use_recovery_code(db: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    """Whether `code` is one of the account's unused recovery codes, which it
    then uses up. The caller commits."""
    if not 8 <= len(normal_recovery_code(code)) <= 32:
        return False
    result = await db.execute(
        update(RecoveryCode)
        .where(
            RecoveryCode.user_id == user_id,
            RecoveryCode.code_hash == recovery_code_hash(user_id, code),
            RecoveryCode.used_at.is_(None),
        )
        .values(used_at=clock.now())
        .execution_options(synchronize_session=False)
    )
    return _rows(result) == 1


async def methods_of(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """The second factors the account can finish a sign-in with."""
    totp = exists().where(Totp.user_id == user_id, Totp.confirmed_at.is_not(None))
    codes = exists().where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
    passkey = exists().where(Passkey.user_id == user_id)
    has_totp, has_codes, has_passkey = (await db.execute(select(totp, codes, passkey))).one()
    methods = []
    if has_totp:
        methods.append("totp")
        if has_codes:
            methods.append("recovery_code")
    if has_passkey:
        methods.append("passkey")
    return methods


# --- the challenge ------------------------------------------------------------------


def _challenge_hash(token: str) -> str:
    return keyed_hash(_PURPOSE, token)


async def open_challenge(db: AsyncSession, user: User) -> str:
    """A sign-in waiting on its second factor: the token for the client. The
    caller commits."""
    token = secrets.token_urlsafe(32)
    now = clock.now()
    db.add(
        Token(
            purpose=_PURPOSE,
            token_hash=_challenge_hash(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + CHALLENGE_LIFETIME,
        )
    )
    await db.flush()
    return token


@dataclass(frozen=True)
class Challenge:
    id: uuid.UUID
    user_id: uuid.UUID


async def take_try(db: AsyncSession, token: str) -> Challenge | None:
    """Count one try against a live challenge, or None when it has ended
    (unknown, used, expired or out of tries). The caller commits, before
    checking the code, so a try counts even when the answer is an error."""
    if not _CHALLENGE.fullmatch(token):
        return None
    row = (
        await db.execute(
            update(Token)
            .where(
                Token.purpose == _PURPOSE,
                Token.token_hash == _challenge_hash(token),
                Token.used_at.is_(None),
                Token.expires_at > clock.now(),
                Token.attempts < CHALLENGE_TRIES,
            )
            .values(attempts=Token.attempts + 1)
            .returning(Token.id, Token.user_id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None or row.user_id is None:
        return None
    return Challenge(row.id, row.user_id)


async def close(db: AsyncSession, challenge: Challenge) -> bool:
    """Use the challenge up; False when another request already did."""
    result = await db.execute(
        update(Token)
        .where(Token.id == challenge.id, Token.used_at.is_(None))
        .values(used_at=clock.now())
        .execution_options(synchronize_session=False)
    )
    return _rows(result) == 1

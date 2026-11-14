"""Sign-in codes and magic links at /api/auth (SPEC.md 14.2, 14.6, 14.10 and
14.12; docs/contracts/auth-api.md; decision 0021).

**Members only, and never a second factor.** `POST /code` mails one message
holding a 6-digit code and a link to `/auth/link?token=…`, both valid 10
minutes and single use. Staff, a suspended or deleted account, or an address
with no account are sent nothing, with the same 202. The account is checked
again when the code or link is used, so one made staff, suspended or moved to
another address since the mail isn't signed in. A member who has a second
factor still gives it: a right code or link opens the same challenge a right
password does.

**Kept as keyed hashes** (decision 0012, amended): the code over its purpose,
its owner and its value, found by its purpose and address, since two people
can be sent the same digits; the link over its purpose and value, found by
that hash (`tokens.py`).

**One live mail per account.** A new code voids the account's earlier code
and link, and signing in with either uses up both. Asking again within 60
seconds (by `kernel.clock`) answers the same and sends nothing; the account
row is locked while that is decided, so asks at once send one message.
Every path locks the account row before any of its code or link rows, so a
code and its link used at once, or a code racing a new ask, can't deadlock.

**Tries:** five per code, each counted before the code is checked, by an
update that refuses a sixth, so racing requests get five between them.
Marking the code used is a second update that only one request can make.

**Limits** (14.6): 10 asks per IP an hour, and 3 per address in 15 minutes,
counted for every address, known or not. The mail goes out after the
answer; a mailer that fails is logged and changes nothing.

**The time says nothing either.** A known address costs a few more queries
than an unknown one, and a wrong try on a live code writes where a try on
an unknown address doesn't, so timing would tell which addresses have
accounts. Every ask and every try therefore answers no sooner than
a fixed floor (`floor.py`), far above that work: the floor plays the part
the dummy Argon2 verify plays at sign-in.

**A link is used only by POST** `/link/confirm`, which the site's
`/auth/link` page sends: a mail scanner that opens the link neither uses it
up nor signs anyone in.
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from kernel import clock
from kernel.access import public
from kernel.auth import accounts, audit, floor, second_factor, sessions, tokens
from kernel.auth.hashing import keyed_hash, same
from kernel.auth.models import Token, User
from kernel.auth.routes import finish_sign_in
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import Mailer
from kernel.errors import Problem
from kernel.ratelimit import RateLimiter, rate_limit, too_many

log = logging.getLogger(__name__)

router = APIRouter()

ASKS_PER_IP = "10/1h"
ASKS_PER_ADDRESS = "3/15m"
LIFETIME = timedelta(minutes=10)
RESEND_WAIT = timedelta(seconds=60)
TRIES = 5
_CODE = "sign_in_code"
_LINK = "magic_link"
_ADDRESS_SCOPE = "auth.code.address"
#: ASCII digits only: `\d` would also take other scripts' digits.
_SIX_DIGITS = re.compile(r"[0-9]{6}")


class AskForCode(BaseModel):
    model_config = ConfigDict(strict=True)

    email: str = Field(max_length=320)


class VerifyCode(BaseModel):
    model_config = ConfigDict(strict=True)

    email: str = Field(max_length=320)
    code: str = Field(max_length=32)


class ConfirmLink(BaseModel):
    model_config = ConfigDict(strict=True)

    token: str = Field(max_length=128)


def code_hash(user_id: uuid.UUID, code: str) -> str:
    return keyed_hash(_CODE, str(user_id), code)


def _invalid_code() -> Problem:
    return Problem("auth.invalid_code", 401, "That code didn't work. Ask for a new one.")


def _invalid_link() -> Problem:
    return Problem("auth.invalid_link", 401, "This link has expired or has already been used.")


async def _void(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Use up every live code and link of the account."""
    await tokens.void(db, user_id, (_CODE, _LINK))


# --- asking -------------------------------------------------------------------------


@router.post(
    "/code",
    status_code=202,
    dependencies=[Depends(public), Depends(rate_limit(ASKS_PER_IP))],
)
async def ask_for_code(
    body: AskForCode,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    started = floor.start()
    normal = accounts.normal_email(body.email)
    limiter = cast(RateLimiter, request.app.state.limiter)
    if not await limiter.hit(ASKS_PER_ADDRESS, _ADDRESS_SCOPE, normal):
        raise too_many(await limiter.wait_seconds(ASKS_PER_ADDRESS, _ADDRESS_SCOPE, normal))
    # Locked until the commit, so asks at once decide one after another.
    user: User | None = await db.scalar(
        select(User).where(User.email_normal == normal).with_for_update()
    )
    mail: tuple[str, str, str] | None = None
    if user is None or user.status not in accounts.SIGNS_IN or await sessions.is_staff(db, user.id):
        audit.record(db, request, "auth.code_sent", "refused", subject=user.id if user else None)
    elif await _waiting(db, normal):
        audit.record(db, request, "auth.code_sent", "waiting", subject=user.id)
    else:
        code, link = await _issue(db, user, normal)
        audit.record(db, request, "auth.code_sent", "success", subject=user.id)
        mail = (user.email, *_message(request.app.state.config, code, link))
    await db.commit()
    if mail is not None:
        background.add_task(_send, request.app.state.mailer, *mail)
    await floor.wait_out(started)
    return {"status": "check_email"}


async def _waiting(db: AsyncSession, normal: str) -> bool:
    """Whether a code went to this address within the resend wait."""
    recent = exists().where(
        Token.purpose == _CODE,
        Token.email_normal == normal,
        Token.created_at > clock.now() - RESEND_WAIT,
    )
    return bool(await db.scalar(select(recent)))


async def _issue(db: AsyncSession, user: User, normal: str) -> tuple[str, str]:
    """A new code and link, voiding the last ones. The caller commits."""
    await _void(db, user.id)
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = clock.now()
    db.add(
        Token(
            purpose=_CODE,
            token_hash=code_hash(user.id, code),
            user_id=user.id,
            email_normal=normal,
            created_at=now,
            expires_at=now + LIFETIME,
        )
    )
    link = await tokens.issue(db, _LINK, user.id, normal, lifetime=LIFETIME)
    return code, link


def _message(config: KernelConfig, code: str, link: str) -> tuple[str, str]:
    minutes = int(LIFETIME.total_seconds() // 60)
    return (
        f"Your {config.site_name} sign-in code",
        f"Your code to sign in to {config.site_name} is {code}\n\n"
        f"Or open this link to sign in on this device:\n\n"
        f"{config.site_url.rstrip('/')}/auth/link?token={link}\n\n"
        f"The code and the link work once, within {minutes} minutes.\n\n"
        "If you didn't ask to sign in, ignore this message: nobody can use it "
        "without reading your email.\n",
    )


async def _send(mailer: Mailer, to: str, subject: str, text: str) -> None:
    try:
        await mailer.send(to, subject, text)
    except Exception as error:
        log.warning("A sign-in code wasn't sent (%s).", type(error).__name__)


# --- signing in -------------------------------------------------------------------


@dataclass(frozen=True)
class _Try:
    id: uuid.UUID
    user_id: uuid.UUID
    email_normal: str
    token_hash: str


async def _take_try(db: AsyncSession, normal: str) -> _Try | None:
    """Count one try against the address's live code, or None when it has
    none (never sent, used, expired or out of tries). The caller commits."""
    latest = (
        select(Token.id)
        .where(
            Token.purpose == _CODE,
            Token.email_normal == normal,
            Token.used_at.is_(None),
            Token.expires_at > clock.now(),
        )
        .order_by(Token.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    row = (
        await db.execute(
            update(Token)
            .where(Token.id == latest, Token.attempts < TRIES)
            .values(attempts=Token.attempts + 1)
            .returning(Token.id, Token.user_id, Token.email_normal, Token.token_hash)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if row is None or row.user_id is None or row.email_normal is None:
        return None
    return _Try(row.id, row.user_id, row.email_normal, row.token_hash)


async def _use(db: AsyncSession, token_id: uuid.UUID) -> bool:
    """Mark the code used; False when another request already did."""
    used = await db.scalar(
        update(Token)
        .where(Token.id == token_id, Token.used_at.is_(None))
        .values(used_at=clock.now())
        .returning(Token.id)
        .execution_options(synchronize_session=False)
    )
    return used is not None


@router.post("/code/verify", dependencies=[Depends(public)])
async def verify_code(
    body: VerifyCode,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    started = floor.start()
    try:
        return await _verify_code(body, request, background, db)
    finally:  # a right code too: only the answer may differ, never the time
        await floor.wait_out(started)


async def _verify_code(
    body: VerifyCode, request: Request, background: BackgroundTasks, db: AsyncSession
) -> Response:
    normal = accounts.normal_email(body.email)
    taken = await _take_try(db, normal) if _SIX_DIGITS.fullmatch(body.code) else None
    await db.commit()  # the try counts, whatever happens next
    if taken is None:
        raise _invalid_code()
    if not same(taken.token_hash, code_hash(taken.user_id, body.code)):
        audit.record(
            db,
            request,
            "auth.sign_in",
            "failure",
            subject=taken.user_id,
            details={"method": "code"},
        )
        await db.commit()
        raise _invalid_code()
    await accounts.lock(db, taken.user_id)
    if not await _use(db, taken.id):
        await db.rollback()
        raise _invalid_code()
    return await _sign_in(
        request, db, background, taken.user_id, taken.email_normal, "code", _invalid_code
    )


@router.post("/link/confirm", dependencies=[Depends(public)])
async def confirm_link(
    body: ConfirmLink,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    owner = await tokens.owner_of(db, _LINK, body.token)
    if owner is not None:
        await accounts.lock(db, owner)
    redeemed = await tokens.redeem(db, _LINK, body.token) if owner is not None else None
    if redeemed is None or redeemed.email_normal is None:
        await db.rollback()
        raise _invalid_link()
    return await _sign_in(
        request, db, background, redeemed.user_id, redeemed.email_normal, "link", _invalid_link
    )


async def _sign_in(
    request: Request,
    db: AsyncSession,
    background: BackgroundTasks,
    user_id: uuid.UUID,
    sent_to: str,
    method: str,
    refused: Callable[[], Problem],
) -> Response:
    """After a right code or link, inside the transaction that used it: sign
    in, or open the second factor's challenge. An account that can't sign in
    now, is staff now or has left the address the mail went to is refused,
    and the rollback leaves its code and link as they were."""
    user = await db.get(User, user_id, populate_existing=True)
    if (
        user is None
        or user.status not in accounts.SIGNS_IN
        or user.email_normal != sent_to
        or await sessions.is_staff(db, user.id)
    ):
        await db.rollback()
        raise refused()
    await _void(db, user.id)
    methods = await second_factor.methods_of(db, user.id)
    if methods:
        challenge = await second_factor.open_challenge(db, user, method=method)
        await db.commit()
        return JSONResponse({"status": "second_factor", "challenge": challenge, "methods": methods})
    return await finish_sign_in(request, db, background, user, second_factor=False, method=method)

"""Password resets at /api/auth (SPEC.md 14.6, 14.7, 14.10 and 14.12;
docs/contracts/auth-api.md; decision 0022).

**Asking** (`POST /password/reset-request`) answers 202 `{"status":
"check_email"}` whatever the address. An account that can sign in is mailed
a link to `/auth/reset?token=…`, valid 30 minutes and single use. Staff are
mailed one too: a reset signs nobody in, so their second factor still guards
the account. A suspended or deleted account, or an address with no account,
is sent nothing. Limits as a code's (14.6): 10 asks per IP an hour, 3 per
address in 15 minutes, and asking again within 60 seconds (by
`kernel.clock`) sends nothing. A new link voids the last one. The account
row is locked while an ask is decided, so asks at once send one message,
and every ask answers no sooner than the floor (`floor.py`), so the time
says nothing about the account either.

**Resetting** (`POST /password/reset`) checks the link, then the new
password (rules, list, breach lookup): a refused one leaves the link
working. One Argon2 hash later, the account row is locked and the link used,
once. The account must still have the address the link went to and be able
to sign in. Then the password is replaced; every session ends (the epoch
goes up, which also makes every browser a stranger to the device cookie);
every live sign-in code and link, reset link and second-factor challenge of
the account is voided; and the address is marked verified, since the link
proved the inbox and the reset has shut out whoever else knew the old
password, which gives a pre-claimed address back to its real owner (decision
0022). The address's failed sign-ins are cleared, so strangers' guesses
don't keep the new password waiting. A security mail goes out after the
answer. It signs nobody in.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.access import public
from kernel.auth import accounts, audit, floor, sessions, tokens
from kernel.auth.models import Token, User
from kernel.auth.passwords import Passwords, refusal, site_context
from kernel.auth.routes import forget_sign_in_failures
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import Mailer
from kernel.errors import Problem
from kernel.ratelimit import RateLimiter, rate_limit, too_many

log = logging.getLogger(__name__)

router = APIRouter()

ASKS_PER_IP = "10/1h"
ASKS_PER_ADDRESS = "3/15m"
LIFETIME = timedelta(minutes=30)
RESEND_WAIT = timedelta(seconds=60)
_RESET = "reset_password"
_ADDRESS_SCOPE = "auth.password_reset.address"
#: Every way in a reset ends: what was sent or opened before it.
_ENDED = ("sign_in_code", "magic_link", _RESET, "second_factor")


class AskForReset(BaseModel):
    model_config = ConfigDict(strict=True)

    email: str = Field(max_length=320)


class Reset(BaseModel):
    model_config = ConfigDict(strict=True)

    token: str = Field(max_length=128)
    password: str = Field(max_length=1024)


def _token_invalid() -> Problem:
    return Problem("auth.token_invalid", 400, "This link has expired or has already been used.")


# --- asking -------------------------------------------------------------------------


@router.post(
    "/password/reset-request",
    status_code=202,
    dependencies=[Depends(public), Depends(rate_limit(ASKS_PER_IP))],
)
async def ask_for_reset(
    body: AskForReset,
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
    action = "auth.password_reset_requested"
    if user is None or user.status not in accounts.SIGNS_IN:
        audit.record(db, request, action, "refused", subject=user.id if user else None)
    elif await _waiting(db, normal):
        audit.record(db, request, action, "waiting", subject=user.id)
    else:
        await tokens.void(db, user.id, (_RESET,))
        token = await tokens.issue(db, _RESET, user.id, normal, lifetime=LIFETIME)
        audit.record(db, request, action, "success", subject=user.id)
        mail = (user.email, *_reset_mail(request.app.state.config, token))
    await db.commit()
    if mail is not None:
        background.add_task(_send, request.app.state.mailer, *mail)
    await floor.wait_out(started)
    return {"status": "check_email"}


async def _waiting(db: AsyncSession, normal: str) -> bool:
    """Whether a reset link went to this address within the resend wait."""
    recent = exists().where(
        Token.purpose == _RESET,
        Token.email_normal == normal,
        Token.created_at > clock.now() - RESEND_WAIT,
    )
    return bool(await db.scalar(select(recent)))


def _reset_mail(config: KernelConfig, token: str) -> tuple[str, str]:
    minutes = int(LIFETIME.total_seconds() // 60)
    return (
        f"Reset your {config.site_name} password",
        f"Someone asked to reset the password of your {config.site_name} account. "
        f"To choose a new one, open this link within {minutes} minutes:\n\n"
        f"{config.site_url.rstrip('/')}/auth/reset?token={token}\n\n"
        "The link works once. Resetting signs out every device.\n\n"
        "If you didn't ask, ignore this message: your password stays as it is.\n",
    )


async def _send(mailer: Mailer, to: str, subject: str, text: str) -> None:
    try:
        await mailer.send(to, subject, text)
    except Exception as error:
        log.warning("A password reset mail wasn't sent (%s).", type(error).__name__)


# --- resetting ----------------------------------------------------------------------


@router.post("/password/reset", dependencies=[Depends(public)])
async def reset_password(
    body: Reset,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    owner = await tokens.owner_of(db, _RESET, body.token)
    user = await db.get(User, owner) if owner is not None else None
    if user is None:
        await db.rollback()
        raise _token_invalid()
    user_id, email = user.id, user.email
    config = cast(KernelConfig, request.app.state.config)
    # No connection held through the lookup and the hash. The rollback
    # expires `user`, so only the values read above are used until it's
    # loaded again.
    await db.rollback()
    reason = await refusal(
        body.password, site_context(config, email), lookup=request.app.state.breach_lookup
    )
    if reason is not None:
        raise Problem("auth.password_rejected", 422, reason)
    hashed = await cast(Passwords, request.app.state.passwords).hash(body.password)

    await accounts.lock(db, user_id)  # before the token row, as every route does
    redeemed = await tokens.redeem(db, _RESET, body.token)
    user = await db.get(User, user_id, populate_existing=True)
    if (
        redeemed is None
        or user is None
        or user.status not in accounts.SIGNS_IN
        or user.email_normal != redeemed.email_normal
    ):
        await db.rollback()
        raise _token_invalid()
    now = clock.now()
    user.password_hash = hashed
    if user.email_verified_at is None:
        user.email_verified_at = now
    await sessions.end_all(db, user)
    await tokens.void(db, user.id, _ENDED)
    audit.record(db, request, "auth.password_reset", "success", actor=user.id, subject=user.id)
    await db.commit()
    await forget_sign_in_failures(cast(RateLimiter, request.app.state.limiter), user.email_normal)
    background.add_task(_send, request.app.state.mailer, user.email, *_notice(config, now))
    return {"status": "password_reset"}


def _notice(config: KernelConfig, at: datetime) -> tuple[str, str]:
    when = f"{at.day} {at:%B %Y} at {at:%H:%M} UTC"
    return (
        f"Your {config.site_name} password was reset",
        f"The password of your {config.site_name} account was reset on {when}, "
        "and every device was signed out.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, someone can read your email: secure your mailbox first, "
        f"then reset your password again at {config.site_url.rstrip('/')}/sign-in.\n",
    )

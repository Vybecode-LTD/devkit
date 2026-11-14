"""The auth routes at /api/auth: signing in and out, the second factor, the
session and step-up (SPEC.md 14.2 to 14.6 and 14.10;
docs/contracts/auth-api.md). Sign-up, codes, links and resets come next.

**Nothing says whether an account exists.** A sign-in for an unknown
address, a suspended or deleted account, or one with no password costs the
same Argon2 verify as a wrong password (`Passwords.check`), counts against
the same failure limit, writes the same audit row and gets the same answer.

**Limits** (14.6, decision 0019), on top of 10 sign-ins per address per minute:

- *Failed passwords*, per address typed (normalized): past 5 in 15 minutes,
  10 in an hour or 20 in a day, every password is refused with 429 and the
  wait, the right one too, so guesses spread over strangers' browsers can't
  outlast it. A browser holding the account's device cookie is exempt: the
  owner still signs in where they have before (14.5).
- *Second-factor failures:* 5 per sign-in end it (`auth.challenge_ended`),
  and past 10 in an hour the account takes no more codes, so knowing the
  password isn't a way to guess codes for ever.
- *Step-up failures:* the fifth in 15 minutes ends the session.

**A new device** (no device cookie for the account) is mailed a notice after
it signs in, without delaying the answer; a mailer that fails is logged and
changes nothing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from kernel import clock
from kernel.access import public
from kernel.auth import accounts, audit, second_factor, sessions
from kernel.auth.dependencies import current_user, lifetimes_of, signed_in, supersede
from kernel.auth.models import Session, User
from kernel.auth.passwords import Passwords
from kernel.auth.sessions import Resumed
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import Mailer
from kernel.errors import Problem
from kernel.ratelimit import RateLimiter, rate_limit, too_many

log = logging.getLogger(__name__)

router = APIRouter()

SIGN_IN_FAILURES = ("5/15m", "10/1h", "20/1d")
SECOND_FACTOR_FAILURES = "10/1h"
STEP_UP_FAILURES = "5/15m"
_SIGN_IN_SCOPE = "auth.sign_in.failures"
_SECOND_FACTOR_SCOPE = "auth.second_factor.failures"
_STEP_UP_SCOPE = "auth.step_up.failures"


class SignIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class SecondFactor(BaseModel):
    challenge: str = Field(max_length=128)
    totp: str | None = Field(default=None, max_length=16)
    recovery_code: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_method(self) -> SecondFactor:
        if (self.totp is None) == (self.recovery_code is None):
            raise ValueError("Send either a totp or a recovery_code.")
        return self


class StepUp(BaseModel):
    password: str | None = Field(default=None, max_length=1024)
    totp: str | None = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def _one_method(self) -> StepUp:
        if (self.password is None) == (self.totp is None):
            raise ValueError("Send either a password or a totp.")
        return self


def _limiter(request: Request) -> RateLimiter:
    return cast(RateLimiter, request.app.state.limiter)


def _passwords(request: Request) -> Passwords:
    return cast(Passwords, request.app.state.passwords)


def _challenge_ended() -> Problem:
    return Problem("auth.challenge_ended", 401, "This sign-in has ended. Start again.")


async def _wait(limiter: RateLimiter, rules: tuple[str, ...], scope: str, key: str) -> int:
    return max([await limiter.wait_seconds(rule, scope, key) for rule in rules])


# --- signing in ----------------------------------------------------------------


@router.post("/sign-in", dependencies=[Depends(public), Depends(rate_limit("10/1m"))])
async def sign_in(
    body: SignIn,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    limiter = _limiter(request)
    email = accounts.normal_email(body.email)
    user = await accounts.by_email(db, email)
    if user is not None and user.status not in accounts.SIGNS_IN:
        user = None
    if not sessions.knows_device(request.cookies.get(sessions.DEVICE_COOKIE), user):
        wait = await _wait(limiter, SIGN_IN_FAILURES, _SIGN_IN_SCOPE, email)
        if wait:
            raise too_many(wait)
    passwords = _passwords(request)
    hashed = user.password_hash if user is not None else None
    if user is None or hashed is None or not await passwords.check(body.password, hashed):
        if user is None or hashed is None:
            await passwords.check(body.password, None)  # the same cost as a wrong password
        for rule in SIGN_IN_FAILURES:
            await limiter.hit(rule, _SIGN_IN_SCOPE, email)
        audit.record(
            db, request, "auth.sign_in", "failure", subject=user.id if user is not None else None
        )
        await db.commit()
        raise Problem(
            "auth.invalid_credentials", 401, "That email and password don't match an account."
        )
    if passwords.needs_rehash(hashed):
        user.password_hash = await passwords.hash(body.password)
    methods = await second_factor.methods_of(db, user.id)
    if methods:
        challenge = await second_factor.open_challenge(db, user)
        await db.commit()
        return JSONResponse({"status": "second_factor", "challenge": challenge, "methods": methods})
    return await _finish(request, db, background, user, second_factor=False)


@router.post("/sign-in/second-factor", dependencies=[Depends(public)])
async def finish_with_second_factor(
    body: SecondFactor,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    challenge = await second_factor.take_try(db, body.challenge)
    await db.commit()  # the try counts, whatever happens next
    if challenge is None:
        raise _challenge_ended()
    limiter = _limiter(request)
    key = str(challenge.user_id)
    if await limiter.used_up(SECOND_FACTOR_FAILURES, _SECOND_FACTOR_SCOPE, key):
        raise too_many(
            await limiter.wait_seconds(SECOND_FACTOR_FAILURES, _SECOND_FACTOR_SCOPE, key)
        )
    if body.totp is not None:
        method, ok = "totp", await second_factor.check_totp(db, challenge.user_id, body.totp)
    else:
        method = "recovery_code"
        ok = await second_factor.use_recovery_code(db, challenge.user_id, body.recovery_code or "")
    if not ok:
        await limiter.hit(SECOND_FACTOR_FAILURES, _SECOND_FACTOR_SCOPE, key)
        audit.record(
            db,
            request,
            "auth.second_factor",
            "failure",
            subject=challenge.user_id,
            details={"method": method},
        )
        await db.commit()
        raise Problem("auth.invalid_second_factor", 401, "That code didn't work. Try again.")
    user = await db.get(User, challenge.user_id, populate_existing=True)
    if (
        user is None
        or user.status not in accounts.SIGNS_IN
        or not await second_factor.close(db, challenge)
    ):
        await db.rollback()
        raise _challenge_ended()
    return await _finish(request, db, background, user, second_factor=True)


async def _finish(
    request: Request,
    db: AsyncSession,
    background: BackgroundTasks,
    user: User,
    *,
    second_factor: bool,
) -> JSONResponse:
    """Start the session, after the password and any second factor."""
    known = sessions.knows_device(request.cookies.get(sessions.DEVICE_COOKIE), user)
    await sessions.end_by_token(db, request.cookies.get(sessions.SESSION_COOKIE))
    now = clock.now()
    if user.status == "deleting":  # signing in cancels a deletion (14.7)
        user.status, user.deletion_due_at = "active", None
    user.last_sign_in_at = now
    token, session = await sessions.start(
        db,
        user,
        user_agent=request.headers.get("user-agent", ""),
        second_factor=second_factor,
        lifetimes=lifetimes_of(request),
    )
    audit.record(
        db,
        request,
        "auth.sign_in",
        "success",
        actor=user.id,
        subject=user.id,
        details={"second_factor": second_factor, "new_device": not known},
    )
    shown = await accounts.view(db, user, declared=request.app.state.declared_permissions)
    await db.commit()
    response = JSONResponse({"status": "signed_in", "user": shown})
    sessions.set_session_cookie(response, token, session)
    sessions.set_device_cookie(response, user)
    if not known:
        background.add_task(
            _mail_new_device,
            request.app.state.mailer,
            request.app.state.config,
            user.email,
            session.device_label,
            now,
        )
    return response


async def _mail_new_device(
    mailer: Mailer, config: KernelConfig, to: str, device: str, at: datetime
) -> None:
    when = f"{at.day} {at:%B %Y} at {at:%H:%M} UTC"
    text = (
        f"Someone signed in to your {config.site_name} account from a new device "
        f"({device or 'a browser we could not name'}) on {when}.\n\n"
        "If that was you, there's nothing to do.\n\n"
        "If it wasn't, reset your password from the sign-in page, "
        f"{config.site_url.rstrip('/')}/sign-in: that signs every device out.\n"
    )
    try:
        await mailer.send(to, f"New sign-in to {config.site_name}", text)
    except Exception as error:
        log.warning("The new-device mail wasn't sent (%s).", type(error).__name__)


# --- the session ---------------------------------------------------------------


@router.get("/session")
async def session(
    request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return {"user": await accounts.view(db, user, declared=request.app.state.declared_permissions)}


@router.post("/sign-out", status_code=204, dependencies=[Depends(public)])
async def sign_out(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Ends this browser's session; the device cookie stays (14.5)."""
    ended = await sessions.end_by_token(db, request.cookies.get(sessions.SESSION_COOKIE))
    if ended is not None:
        audit.record(db, request, "auth.sign_out", "success", actor=ended, subject=ended)
    await db.commit()
    response = Response(status_code=204)
    sessions.clear_session_cookie(response)
    return response


@router.post("/step-up", dependencies=[Depends(current_user)])
async def step_up(
    body: StepUp,
    request: Request,
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """A fresh sign-in on this session (14.4), by password or TOTP."""
    user, row = resumed.user, resumed.session
    if body.password is not None:
        method = "password"
        ok = await _passwords(request).check(body.password, user.password_hash)
    else:
        method = "totp"
        ok = await second_factor.check_totp(db, user.id, body.totp or "")
    if not ok:
        await _failed_step_up(request, db, user, row)
        if method == "password":
            raise Problem("auth.invalid_credentials", 401, "That password isn't right.")
        raise Problem("auth.invalid_second_factor", 401, "That code didn't work. Try again.")
    token = await sessions.step_up(db, row, second_factor=method == "totp")
    audit.record(
        db,
        request,
        "auth.step_up",
        "success",
        actor=user.id,
        subject=user.id,
        details={"method": method},
    )
    await db.commit()
    response = JSONResponse({"status": "recent"})
    if token is not None:
        supersede(request)
        sessions.set_session_cookie(response, token, row)
    return response


async def _failed_step_up(request: Request, db: AsyncSession, user: User, row: Session) -> None:
    """Count the failure; the fifth in 15 minutes ends the session (14.6)."""
    limiter = _limiter(request)
    key = str(row.id)
    await limiter.hit(STEP_UP_FAILURES, _STEP_UP_SCOPE, key)
    audit.record(db, request, "auth.step_up", "failure", actor=user.id, subject=user.id)
    if not await limiter.used_up(STEP_UP_FAILURES, _STEP_UP_SCOPE, key):
        await db.commit()
        return
    await db.execute(delete(Session).where(Session.id == row.id))
    audit.record(
        db,
        request,
        "auth.session_ended",
        "success",
        actor=user.id,
        subject=user.id,
        details={"reason": "step_up_failures"},
    )
    await db.commit()
    supersede(request)
    carrier = Response()
    sessions.clear_session_cookie(carrier)
    raise Problem(
        "kernel.not_signed_in",
        401,
        "Too many tries: you've been signed out. Sign in again.",
        headers={"set-cookie": carrier.headers["set-cookie"]},
    )

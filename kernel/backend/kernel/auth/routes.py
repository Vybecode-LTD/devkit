"""The auth routes at /api/auth: signing in and out, the second factor, the
session and step-up (SPEC.md 14.2 to 14.6 and 14.10;
docs/contracts/auth-api.md). Sign-up and verification are in `sign_up.py`,
sign-in codes and magic links in `codes.py`, password resets in `resets.py`,
passkeys in `passkeys.py` (their second-factor and step-up checks are here).

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
  password isn't a way to guess codes for ever. Each try takes its place in
  the hour's budget before its code is checked, so parallel guesses can't
  outrun it, and a right code starts the account's count again.
- *Step-up failures:* the fifth in 15 minutes ends the session.

**One lock order** (decision 0021): a route that touches an account's token,
session, TOTP or recovery-code rows locks the account row first. A password
sign-in takes it after the password is checked and looks at the account
again, so a reset or a suspension that landed meanwhile wins over the old
password. The second-factor step and step-up by TOTP or passkey take it
before the code or passkey is checked, since checking one writes its row
(decisions 0027 and 0028).

**A new device** (no device cookie for the account) is mailed a notice after
it signs in, without delaying the answer; a mailer that fails is logged and
changes nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from kernel import clock
from kernel.access import public
from kernel.auth import accounts, audit, ceremonies, mails, second_factor, sessions
from kernel.auth.ceremonies import AssertionCredential
from kernel.auth.dependencies import current_user, lifetimes_of, signed_in, supersede
from kernel.auth.models import Passkey, Session, User
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
    model_config = ConfigDict(strict=True)

    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class SecondFactor(BaseModel):
    model_config = ConfigDict(strict=True)

    challenge: str = Field(max_length=128)
    totp: str | None = Field(default=None, max_length=16)
    recovery_code: str | None = Field(default=None, max_length=64)
    passkey: AssertionCredential | None = None

    @model_validator(mode="after")
    def _one_method(self) -> SecondFactor:
        sent = (self.totp, self.recovery_code, self.passkey)
        if sum(factor is not None for factor in sent) != 1:
            raise ValueError("Send one of a totp, a recovery_code or a passkey.")
        return self


class StepUp(BaseModel):
    model_config = ConfigDict(strict=True)

    password: str | None = Field(default=None, max_length=1024)
    totp: str | None = Field(default=None, max_length=16)
    passkey: AssertionCredential | None = None

    @model_validator(mode="after")
    def _one_method(self) -> StepUp:
        if sum(factor is not None for factor in (self.password, self.totp, self.passkey)) != 1:
            raise ValueError("Send one of a password, a totp or a passkey.")
        return self


def _limiter(request: Request) -> RateLimiter:
    return cast(RateLimiter, request.app.state.limiter)


def _passwords(request: Request) -> Passwords:
    return cast(Passwords, request.app.state.passwords)


def _challenge_ended() -> Problem:
    return Problem("auth.challenge_ended", 401, "This sign-in has ended. Start again.")


async def forget_sign_in_failures(limiter: RateLimiter, email: str) -> None:
    """Clear the address's failed sign-ins: a finished reset calls this. It
    makes every browser a stranger (the epoch), so a stranger's guesses
    mustn't keep the owner's new password waiting for up to a day."""
    for rule in SIGN_IN_FAILURES:
        await limiter.forget(rule, _SIGN_IN_SCOPE, accounts.normal_email(email))


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
    rehashed = await passwords.hash(body.password) if passwords.needs_rehash(hashed) else None
    # Lock the account, then look again: a reset or a suspension may have
    # landed while the password was being checked or re-hashed, and the
    # password checked above must not win over it (Codex on #43).
    await accounts.lock(db, user.id)
    user = await db.get(User, user.id, populate_existing=True)
    if user is None or user.status not in accounts.SIGNS_IN or user.password_hash != hashed:
        await db.rollback()
        raise Problem(
            "auth.invalid_credentials", 401, "That email and password don't match an account."
        )
    if rehashed is not None:
        user.password_hash = rehashed
    methods = await second_factor.methods_of(db, user.id)
    if methods:
        challenge = await second_factor.open_challenge(db, user)
        await db.commit()
        return JSONResponse({"status": "second_factor", "challenge": challenge, "methods": methods})
    return await finish_sign_in(request, db, background, user, second_factor=False)


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
    # The try takes its place in the account's budget before its code is
    # checked, so guesses sent at once can't all pass a check made first.
    if not await limiter.hit(SECOND_FACTOR_FAILURES, _SECOND_FACTOR_SCOPE, key):
        raise too_many(
            await limiter.wait_seconds(SECOND_FACTOR_FAILURES, _SECOND_FACTOR_SCOPE, key)
        )
    # The account before its TOTP or recovery-code row and the challenge's,
    # as a reset and a TOTP removal take them (Codex on #43; decision 0027).
    await accounts.lock(db, challenge.user_id)
    if body.totp is not None:
        method, ok = "totp", await second_factor.check_totp(db, challenge.user_id, body.totp)
    elif body.passkey is not None:
        method = "passkey"
        # The options the last start route gave, as a keyed hash, for 5 minutes.
        answered = ceremonies.answered(body.passkey.response.client_data_json)
        ok = challenge.expects(answered) and await _passkey_answers(
            request, db, challenge.user_id, answered, body.passkey, uv=False
        )
    else:
        method = "recovery_code"
        ok = await second_factor.use_recovery_code(db, challenge.user_id, body.recovery_code or "")
    if not ok:
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
    # A right code shows the owner is here: the account's count starts again.
    await limiter.forget(SECOND_FACTOR_FAILURES, _SECOND_FACTOR_SCOPE, key)
    return await finish_sign_in(
        request, db, background, user, second_factor=True, method=challenge.method
    )


async def finish_sign_in(
    request: Request,
    db: AsyncSession,
    background: BackgroundTasks,
    user: User,
    *,
    second_factor: bool,
    method: str = "password",
) -> JSONResponse:
    """Start the session, after the first factor (`method`: a password, a
    code or a link) and any second factor. Every caller holds the account's
    row lock already, taken before any token or session row; it is taken
    again here, at no cost, so a new caller can't get the order wrong."""
    await accounts.lock(db, user.id)
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
        details={"method": method, "second_factor": second_factor, "new_device": not known},
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
    subject, text = mails.rendered(
        "kernel.new_sign_in", device=device or "a browser we could not name", when=mails.when(at)
    )
    try:
        await mailer.send(to, subject, text)
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
    """A fresh sign-in on this session (14.4), by password, TOTP or passkey."""
    user, row = resumed.user, resumed.session
    if body.password is not None:
        method = "password"
        ok = await _passwords(request).check(body.password, user.password_hash)
        # Hashed before the lock, so a slow hash holds no row; then the account
        # and the session again: a reset that ended it meanwhile wins.
        user = await accounts.held(db, user.id, row.id)
    elif body.passkey is not None:
        method = "passkey"
        # The account before its token and passkey rows, then the session
        # again: a reset that ended it meanwhile wins (CodeRabbit on #50).
        user = await accounts.held(db, user.id, row.id)
        # The options `step-up/passkey` gave this session, used up either way.
        challenge = ceremonies.answered(body.passkey.response.client_data_json)
        kept = challenge is not None and (
            await ceremonies.use(
                db, ceremonies.STEP_UP, challenge, user_id=user.id, session_id=row.id
            )
            is not None
        )
        ok = kept and await _passkey_answers(request, db, user.id, challenge, body.passkey, uv=True)
    else:
        method = "totp"
        # The account before its TOTP row (decision 0027), then the session
        # again, so a reset that lands first leaves the code's step unused.
        user = await accounts.held(db, user.id, row.id)
        ok = await second_factor.check_totp(db, user.id, body.totp or "")
    if not ok:
        await failed_step_up(request, db, user, row)
        if method == "password":
            raise Problem("auth.invalid_credentials", 401, "That password isn't right.")
        if method == "passkey":
            raise Problem("auth.invalid_passkey", 401, "That passkey didn't work. Try again.")
        raise Problem("auth.invalid_second_factor", 401, "That code didn't work. Try again.")
    token = await sessions.step_up(db, row, second_factor=method != "password")
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


async def _passkey_answers(
    request: Request,
    db: AsyncSession,
    user_id: uuid.UUID,
    challenge: str | None,
    credential: AssertionCredential,
    *,
    uv: bool,
) -> bool:
    """Whether `credential` is one of the account's passkeys answering
    `challenge`, with user verification if `uv`. The caller holds the
    account's lock; the passkey's count and last use are written."""
    raw_id = credential.credential_id()
    if challenge is None or raw_id is None:
        return False
    passkey = await db.scalar(
        select(Passkey)
        .where(Passkey.credential_id == raw_id, Passkey.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if passkey is None:
        return False
    party = ceremonies.relying_party(request.app.state.config)
    return ceremonies.used(passkey, credential, challenge, party, require_user_verification=uv)


async def failed_step_up(request: Request, db: AsyncSession, user: User, row: Session) -> None:
    """Count a failed step-up, or a wrong current password at a password
    change; the fifth in 15 minutes ends the session (14.6)."""
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

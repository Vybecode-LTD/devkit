"""Setting up a TOTP at /api/auth (SPEC.md 14.3, 14.4 and 14.6;
docs/contracts/auth-api.md; decision 0026).

**`POST /totp/setup`**, step-up. 403 `auth.email_unverified` until the
account's address is verified, so whoever signed up with someone else's
address can't leave a factor behind for its owner to inherit (14.3). 409
`auth.totp_exists` while the account has a confirmed TOTP: that one is
removed first (`DELETE /totp`), so a setup never takes away a factor that
works. Otherwise a new 160-bit secret, sealed at rest, takes the place of
any earlier one not yet confirmed, and the answer gives it with its
`otpauth://` URI: the site's name as the issuer, the account's address as
the label. It is no second factor until it is confirmed.

**`POST /totp/confirm {code}`**, signed in. A right code for the secret
waiting, within one step of now, confirms it: the TOTP is a second factor
from then on, the step the code matched counts as used, so the code can't
sign anyone in, and the answer gives 10 new recovery codes in place of any
older ones. 409 `auth.no_pending_totp` with nothing to confirm (no setup,
or confirmed already); 403 `auth.email_unverified` if the address isn't
verified now. A wrong code answers 401 `auth.invalid_second_factor` and
counts as a failed step-up, so the fifth in 15 minutes ends the session
(14.6). A security mail follows the answer.

Both answers hold a secret, so neither may be cached (`Cache-Control:
no-store`). Both lock the account row before its TOTP and recovery-code
rows, as every route takes the account first (decision 0021), and then look
at the account again: a reset, a password change or a suspension that ended
this session meanwhile wins, and the request answers 401
`kernel.not_signed_in`, so nobody whose session a reset ended can still turn
on a factor of theirs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import cast

import pyotp
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from kernel import clock, crypto
from kernel.auth import accounts, audit, second_factor
from kernel.auth.dependencies import current_user, require_recent_auth, signed_in
from kernel.auth.models import Session, Totp, User
from kernel.auth.routes import failed_step_up
from kernel.auth.sessions import Resumed
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import Mailer
from kernel.errors import Problem

log = logging.getLogger(__name__)

router = APIRouter()

#: Both answers hold a secret.
_NO_STORE = {"Cache-Control": "no-store"}


class TotpCode(BaseModel):
    model_config = ConfigDict(strict=True)

    code: str = Field(max_length=16)


def _unverified() -> Problem:
    return Problem("auth.email_unverified", 403, "Verify your email address first.")


async def _held(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> User:
    """Lock the account, before its TOTP and recovery-code rows, and look at
    it again: if this session ended meanwhile, the other request stands."""
    await accounts.lock(db, user_id)
    user = await db.get(User, user_id, populate_existing=True)
    session = await db.get(Session, session_id, populate_existing=True)
    if (
        user is None
        or user.status not in accounts.SIGNS_IN
        or session is None
        or session.epoch != user.session_epoch
    ):
        await db.rollback()
        raise Problem("kernel.not_signed_in", 401, "Sign in to continue.")
    return user


@router.post("/totp/setup")
async def set_up_totp(
    request: Request,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _held(db, user.id, resumed.session.id)
    if user.email_verified_at is None:
        await db.rollback()
        raise _unverified()
    totp = await db.get(Totp, user.id, populate_existing=True)
    if totp is not None and totp.confirmed_at is not None:
        await db.rollback()
        raise Problem(
            "auth.totp_exists",
            409,
            "Two-step sign-in is on already. Remove the authenticator to set up another.",
        )
    secret = pyotp.random_base32()  # 32 characters: 160 bits (RFC 4226)
    sealed, now = crypto.seal(secret), clock.now()
    if totp is None:
        db.add(Totp(user_id=user.id, secret_sealed=sealed, created_at=now))
    else:  # an earlier setup never confirmed: its secret goes
        totp.secret_sealed, totp.last_step, totp.created_at = sealed, 0, now
    audit.record(db, request, "auth.totp_setup_started", "success", actor=user.id, subject=user.id)
    config = cast(KernelConfig, request.app.state.config)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=config.site_name)
    await db.commit()
    return JSONResponse({"secret": secret, "otpauth_uri": uri}, headers=_NO_STORE)


@router.post("/totp/confirm")
async def confirm_totp(
    body: TotpCode,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _held(db, user.id, resumed.session.id)
    if user.email_verified_at is None:
        await db.rollback()
        raise _unverified()
    totp = await db.get(Totp, user.id, populate_existing=True)
    if totp is None or totp.confirmed_at is not None:
        await db.rollback()
        raise Problem(
            "auth.no_pending_totp", 409, "There's no new authenticator to confirm. Set one up."
        )
    step = second_factor.matching_step(crypto.open(totp.secret_sealed), body.code)
    if step is None:
        await failed_step_up(request, db, user, resumed.session)  # the fifth ends it
        raise Problem("auth.invalid_second_factor", 401, "That code didn't work. Try again.")
    now = clock.now()
    totp.confirmed_at, totp.last_step = now, step  # this code can't be used again
    codes = await second_factor.new_recovery_codes(db, user.id)
    audit.record(db, request, "auth.totp_confirmed", "success", actor=user.id, subject=user.id)
    to = user.email
    await db.commit()
    config = cast(KernelConfig, request.app.state.config)
    background.add_task(_send, request.app.state.mailer, to, *_notice(config, now))
    return JSONResponse({"recovery_codes": codes}, headers=_NO_STORE)


def _notice(config: KernelConfig, at: datetime) -> tuple[str, str]:
    when = f"{at.day} {at:%B %Y} at {at:%H:%M} UTC"
    site = config.site_url.rstrip("/")
    return (
        f"Two-step sign-in is on for your {config.site_name} account",
        f"An authenticator app was added to your {config.site_name} account on {when}, "
        "so signing in now asks for one of its codes too.\n\n"
        "If that was you, there's nothing to do. Keep your recovery codes somewhere safe.\n\n"
        f"If it wasn't, someone else has your password: reset it now at {site}/sign-in, "
        f"then ask {config.site_name} to remove the authenticator.\n",
    )


async def _send(mailer: Mailer, to: str, subject: str, text: str) -> None:
    try:
        await mailer.send(to, subject, text)
    except Exception as error:
        log.warning("A two-step sign-in mail wasn't sent (%s).", type(error).__name__)

"""Setting up, confirming and removing a TOTP, and new recovery codes, at
/api/auth (SPEC.md 14.3 to 14.6; docs/contracts/auth-api.md; decisions 0026
and 0027).

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
(14.6). A security mail follows the answer, with a link that undoes the
TOTP for whoever didn't add it (`factor_undo`, decision 0030).

**`DELETE /totp`**, step-up, 204. A confirmed TOTP goes with its recovery
codes, and that is the second-factor reset of 14.5 (the owner's answer):
the session epoch goes up, every other session ends, and this one carries
on at the new epoch with a fresh device cookie, as at a password change.
Every live sign-in code and link, reset link and second-factor challenge
of the account is voided, and a security mail follows. A setup never
confirmed was no factor: it goes, and nothing else ends. With no TOTP at
all, nothing changes.

**`POST /recovery-codes`**, step-up. 10 new recovery codes, the old ones
void; 409 `auth.no_second_factor` while the account has no confirmed TOTP.
A security mail follows, since new codes are a way in.

The answers that hold a secret are never cached (`Cache-Control:
no-store`). Every route here locks the account row before its TOTP,
recovery-code, session and token rows, as every route takes the account
first (decisions 0021 and 0027), and then looks at the account and the
session again: a reset, a password change or a suspension that ended this
session meanwhile wins, and the request answers 401 `kernel.not_signed_in`,
so nobody whose session a reset ended can still change the account's
factors.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

import pyotp
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from kernel import clock, crypto
from kernel.answers import answer
from kernel.auth import accounts, audit, factor_undo, mails, second_factor, sessions, tokens
from kernel.auth.answers import RecoveryCodes, TotpSetup
from kernel.auth.dependencies import current_user, require_recent_auth, signed_in
from kernel.auth.models import RecoveryCode, Totp, User
from kernel.auth.routes import failed_step_up
from kernel.auth.sessions import Resumed
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import queue_message
from kernel.errors import Problem

log = logging.getLogger(__name__)

router = APIRouter()

#: The answers that hold a secret.
_NO_STORE = {"Cache-Control": "no-store"}
#: Every way in a removal ends besides sessions, as a password change does.
_ENDED = ("sign_in_code", "magic_link", "reset_password", "second_factor")


class TotpCode(BaseModel):
    model_config = ConfigDict(strict=True)

    code: str = Field(max_length=16)


def _unverified() -> Problem:
    return Problem("auth.email_unverified", 403, "Verify your email address first.")


def _config(request: Request) -> KernelConfig:
    return cast(KernelConfig, request.app.state.config)


@router.post("/totp/setup", response_model=TotpSetup)
async def set_up_totp(
    request: Request,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
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
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name=_config(request).site_name
    )
    await db.commit()
    return answer(TotpSetup, {"secret": secret, "otpauth_uri": uri}, headers=_NO_STORE)


@router.post("/totp/confirm", response_model=RecoveryCodes)
async def confirm_totp(
    body: TotpCode,
    request: Request,
    user: User = Depends(current_user),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
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
    undo = await factor_undo.for_totp(db, user, now)  # for whoever didn't add it (0030)
    audit.record(db, request, "auth.totp_confirmed", "success", actor=user.id, subject=user.id)
    to = user.email
    await queue_message(db, to, *_added(_config(request), now, undo))
    await db.commit()
    return answer(RecoveryCodes, {"recovery_codes": codes}, headers=_NO_STORE)


@router.delete("/totp", status_code=204)
async def remove_totp(
    request: Request,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
    totp = await db.get(Totp, user.id, populate_existing=True)
    response = Response(status_code=204)
    if totp is None:  # nothing to remove
        await db.rollback()
        return response
    confirmed = totp.confirmed_at is not None
    await db.delete(totp)
    audit.record(
        db,
        request,
        "auth.totp_removed",
        "success",
        actor=user.id,
        subject=user.id,
        details={"confirmed": confirmed},
    )
    if not confirmed:  # a setup never confirmed was no factor: nothing else ends
        await db.commit()
        return response
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await sessions.end_all_but(db, user, resumed.session)  # the second-factor reset
    await tokens.void(db, user.id, _ENDED)
    to, now = user.email, clock.now()
    await queue_message(db, to, *_removed(_config(request), now))
    await db.commit()
    sessions.set_device_cookie(response, user)  # signed over the new epoch
    return response


@router.post("/recovery-codes", response_model=RecoveryCodes)
async def replace_recovery_codes(
    request: Request,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
    confirmed = await db.scalar(
        select(Totp.user_id).where(Totp.user_id == user.id, Totp.confirmed_at.is_not(None))
    )
    if confirmed is None:
        await db.rollback()
        raise Problem("auth.no_second_factor", 409, "Set up two-step sign-in first.")
    codes = await second_factor.new_recovery_codes(db, user.id)
    audit.record(
        db, request, "auth.recovery_codes_replaced", "success", actor=user.id, subject=user.id
    )
    to, now = user.email, clock.now()
    await queue_message(db, to, *_replaced(_config(request), now))
    await db.commit()
    return answer(RecoveryCodes, {"recovery_codes": codes}, headers=_NO_STORE)


# --- security mail ------------------------------------------------------------------


def _added(config: KernelConfig, at: datetime, undo: str) -> mails.Mail:
    return mails.rendered(
        "kernel.totp_added",
        when=mails.when(at),
        undo_link=factor_undo.link(config, undo),
        days=factor_undo.UNDO_LIFETIME.days,
    )


def _removed(config: KernelConfig, at: datetime) -> mails.Mail:
    return mails.rendered("kernel.totp_removed", when=mails.when(at))


def _replaced(config: KernelConfig, at: datetime) -> mails.Mail:
    return mails.rendered("kernel.recovery_codes_replaced", when=mails.when(at))

"""Changing the password of the signed-in account at /api/auth (SPEC.md 14.4,
14.5 and 14.6; docs/contracts/auth-api.md; decision 0025).

**`POST /password/change {current_password, new_password}`**, step-up. The
current password is checked first: a wrong one answers 401
`auth.invalid_credentials` and counts as a failed step-up, so the fifth in
15 minutes ends the session, as at step-up. An account with no password (a
passkey or a provider only) is refused the same way and sets one by reset.
Then the new password is judged (rules, list, breach lookup): a refused one
answers 422 `auth.password_rejected` with the reason and changes nothing.

**What a change ends** (14.5): the session epoch goes up, so every other
session ends and this one carries on at the new epoch, with a fresh device
cookie, since the old one was signed over the old epoch. Every live sign-in
code and link, reset link and second-factor challenge of the account is
voided, and a pending email change dies by the epoch (decision 0024). A
security mail follows the answer.

**Order:** no database connection is held through the breach lookup or the
hash. Then the account row is locked before any session or token row, as on
every route, and the account is looked at again: a reset, another change,
an email undo or a suspension that ended this session meanwhile wins, and
this change answers 401 `kernel.not_signed_in`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from kernel import clock
from kernel.auth import accounts, audit, sessions, tokens
from kernel.auth.dependencies import require_recent_auth, signed_in
from kernel.auth.models import Session, User
from kernel.auth.passwords import Passwords, refusal, site_context
from kernel.auth.routes import failed_step_up
from kernel.auth.sessions import Resumed
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import Mailer
from kernel.errors import Problem

log = logging.getLogger(__name__)

router = APIRouter()

#: Every way in a change ends besides sessions: what was sent or opened before it.
_ENDED = ("sign_in_code", "magic_link", "reset_password", "second_factor")


class PasswordChange(BaseModel):
    model_config = ConfigDict(strict=True)

    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


def _wrong_password() -> Problem:
    return Problem("auth.invalid_credentials", 401, "That password isn't right.")


@router.post("/password/change")
async def change_password(
    body: PasswordChange,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    passwords = cast(Passwords, request.app.state.passwords)
    config = cast(KernelConfig, request.app.state.config)
    checked = user.password_hash
    # A missing hash costs the same dummy verify (`Passwords.check`).
    if not await passwords.check(body.current_password, checked):
        await failed_step_up(request, db, user, resumed.session)  # the fifth ends it
        raise _wrong_password()
    user_id, session_id, email = user.id, resumed.session.id, user.email
    await db.rollback()  # no connection held through the lookup and the hash
    reason = await refusal(
        body.new_password, site_context(config, email), lookup=request.app.state.breach_lookup
    )
    if reason is not None:
        raise Problem("auth.password_rejected", 422, reason)
    hashed = await passwords.hash(body.new_password)
    return await _change(request, db, background, user_id, session_id, hashed)


async def _change(
    request: Request,
    db: AsyncSession,
    background: BackgroundTasks,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    hashed: str,
) -> Response:
    """Under the account lock, if nothing changed meanwhile: the new password,
    every other session ended, the live ways in voided."""
    await accounts.lock(db, user_id)  # before any session or token row
    user = await db.get(User, user_id, populate_existing=True)
    session = await db.get(Session, session_id, populate_existing=True)
    if (
        user is None
        or user.status not in accounts.SIGNS_IN
        or session is None
        or session.epoch != user.session_epoch
    ):
        # A reset, another change, an email undo or a suspension ended this
        # session meanwhile: every route that changes a password raises the
        # epoch, so this sees them all, and the other change stands.
        await db.rollback()
        raise Problem("kernel.not_signed_in", 401, "Sign in to continue.")
    now = clock.now()
    user.password_hash = hashed
    await sessions.end_all_but(db, user, session)
    await tokens.void(db, user.id, _ENDED)
    audit.record(db, request, "auth.password_changed", "success", actor=user.id, subject=user.id)
    to = user.email
    await db.commit()
    response = JSONResponse({"status": "password_changed"})
    sessions.set_device_cookie(response, user)  # signed over the new epoch
    config = cast(KernelConfig, request.app.state.config)
    background.add_task(_send, request.app.state.mailer, to, *_notice(config, now))
    return response


def _notice(config: KernelConfig, at: datetime) -> tuple[str, str]:
    when = f"{at.day} {at:%B %Y} at {at:%H:%M} UTC"
    site = config.site_url.rstrip("/")
    return (
        f"Your {config.site_name} password was changed",
        f"The password of your {config.site_name} account was changed on {when}, and "
        "every other device was signed out.\n\n"
        "If that was you, there's nothing to do.\n\n"
        f"If it wasn't, reset your password now at {site}/sign-in: that signs every "
        "device out, this one too.\n",
    )


async def _send(mailer: Mailer, to: str, subject: str, text: str) -> None:
    try:
        await mailer.send(to, subject, text)
    except Exception as error:
        log.warning("A password-change mail wasn't sent (%s).", type(error).__name__)

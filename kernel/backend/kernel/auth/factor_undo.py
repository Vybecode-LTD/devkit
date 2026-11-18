"""Undoing a second factor someone else added, from its mail, at /api/auth
(SPEC.md 14.7; docs/contracts/auth-api.md; decision 0030).

A reset leaves the second factors in place, and a passkey signs in on its own,
so whoever stole the password and added one would keep a way in after the
owner's reset. The mail sent when a passkey is registered or a TOTP is
confirmed carries a link, valid 7 days, to the site's page
`/auth/second-factor/undo?token=…`, whose POST is here.

**`POST /second-factor/undo {token}`**, public. The factor the link was mailed
for goes if it is still there: a passkey by its id, a TOTP with its recovery
codes only if it is the one confirmed when the link was sent, so an old link
never takes away a TOTP set up since. Either way the epoch goes up, every
session ends and every live way in is voided, and a notice follows. 400
`auth.token_invalid` for a bad, used or expired link, or an account that
can't sign in. It signs nobody in.

Undo links have a purpose of their own, `factor_undo`, which no reset, change
or other undo voids: the owner can undo each factor a thief added, one link
each, after resetting. The route finds whose link it is, locks the account,
then uses the link and touches the factor, session and token rows, as every
route takes the account first (decision 0021).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.access import public
from kernel.auth import accounts, audit, mails, sessions, tokens
from kernel.auth.answers import SecondFactorUndone
from kernel.auth.models import Passkey, RecoveryCode, Totp, User
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import queue_message
from kernel.errors import Problem

log = logging.getLogger(__name__)

router = APIRouter()

UNDO_LIFETIME = timedelta(days=7)
_UNDO = "factor_undo"
#: Every way in an undo ends besides sessions, as a second-factor reset does.
_ENDED = ("sign_in_code", "magic_link", "reset_password", "second_factor")


class UndoLink(BaseModel):
    model_config = ConfigDict(strict=True)

    token: str = Field(max_length=128)


async def for_passkey(db: AsyncSession, user: User, passkey_id: uuid.UUID) -> str:
    """The undo link's token for a passkey just registered. The row joins the
    caller's transaction."""
    return await _issue(db, user, {"method": "passkey", "passkey": str(passkey_id)})


async def for_totp(db: AsyncSession, user: User, confirmed_at: datetime) -> str:
    """The undo link's token for the TOTP confirmed at `confirmed_at`."""
    return await _issue(db, user, {"method": "totp", "confirmed_at": confirmed_at.isoformat()})


async def _issue(db: AsyncSession, user: User, data: dict[str, Any]) -> str:
    return await tokens.issue(
        db, _UNDO, user.id, user.email_normal, lifetime=UNDO_LIFETIME, data=data
    )


def link(config: KernelConfig, token: str) -> str:
    return f"{config.site_url.rstrip('/')}/auth/second-factor/undo?token={token}"


def _token_invalid() -> Problem:
    return Problem("auth.token_invalid", 400, "This link has expired or has already been used.")


@router.post(
    "/second-factor/undo", dependencies=[Depends(public)], response_model=SecondFactorUndone
)
async def undo_second_factor(
    body: UndoLink,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    owner = await tokens.owner_of(db, _UNDO, body.token)
    if owner is None:
        await db.rollback()
        raise _token_invalid()
    await accounts.lock(db, owner)  # before the link's row, as every route does
    redeemed = await tokens.redeem(db, _UNDO, body.token)
    user = await db.get(User, owner, populate_existing=True)
    if redeemed is None or user is None or user.status not in accounts.SIGNS_IN:
        await db.rollback()
        raise _token_invalid()
    method = str(redeemed.data.get("method"))
    removed = await _remove(db, user.id, redeemed.data)
    await sessions.end_all(db, user)
    await tokens.void(db, user.id, _ENDED)
    audit.record(
        db,
        request,
        "auth.second_factor_undone",
        "success",
        actor=user.id,
        subject=user.id,
        details={"method": method, "removed": removed},
    )
    to = user.email
    config = cast(KernelConfig, request.app.state.config)
    await queue_message(db, to, *_undone(config, method))
    await db.commit()
    return {"status": "second_factor_undone"}


async def _remove(db: AsyncSession, user_id: uuid.UUID, data: dict[str, Any]) -> bool:
    """Take away the factor the link was mailed for, if it is still there."""
    if data.get("method") == "passkey":
        result = await db.execute(
            delete(Passkey).where(
                Passkey.id == uuid.UUID(str(data["passkey"])), Passkey.user_id == user_id
            )
        )
        return cast(CursorResult[Any], result).rowcount == 1
    if data.get("method") == "totp":
        totp = await db.get(Totp, user_id, populate_existing=True)
        if totp is None or totp.confirmed_at != datetime.fromisoformat(str(data["confirmed_at"])):
            return False  # removed since, or another one set up
        await db.delete(totp)
        await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
        return True
    return False


# --- mail ---------------------------------------------------------------------------


def _undone(config: KernelConfig, method: str) -> mails.Mail:
    return mails.rendered("kernel.passkey_undone" if method == "passkey" else "kernel.totp_undone")

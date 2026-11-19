"""What the account page shows of the account's ways in, at /api/auth
(docs/contracts/auth-api.md, `GET /security`; K4.5): whether it has a
password, its confirmed TOTP and since when, and how many recovery codes are
unused. The passkeys have their own list (`GET /passkeys`), the email and
whether it's verified are the session's, and the devices `GET /sessions`.

A TOTP set up but not confirmed isn't a second factor yet (14.4), so it shows
as none, and its recovery codes don't exist until it's confirmed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.auth.answers import Security
from kernel.auth.dependencies import current_user
from kernel.auth.models import RecoveryCode, Totp, User
from kernel.db import get_db

router = APIRouter()


@router.get("/security", response_model=Security)
async def security(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    confirmed = await db.scalar(
        select(Totp.confirmed_at).where(Totp.user_id == user.id, Totp.confirmed_at.is_not(None))
    )
    left = 0
    if confirmed is not None:
        left = int(
            await db.scalar(
                select(func.count())
                .select_from(RecoveryCode)
                .where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
            )
            or 0
        )
    return {
        "password": user.password_hash is not None,
        "totp": {"since": confirmed.isoformat()} if confirmed is not None else None,
        "recovery_codes_left": left,
    }

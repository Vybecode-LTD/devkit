"""One-time link tokens (SPEC.md 14.7, 14.11 and 14.12): the 32 random bytes
in an email's link, for verifying an address now and for resets, magic links
and email changes after it.

A token is kept only as a keyed hash over its purpose and value (decision
0012, amended), unique by that hash, so it is found by hashing what the link
carries: whose it is can't be known before the row is.
The address it was sent to is kept beside it, so a token sent to an address
the account has since left proves nothing about the new one. Redeeming is one
UPDATE that marks the row used only while it is unused and unexpired, so two
requests holding the same link can't both succeed.
"""

from __future__ import annotations

import re
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.auth.hashing import keyed_hash
from kernel.auth.models import Token

#: What `secrets.token_urlsafe(32)` gives: anything else was never issued.
_LINK_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def token_hash(purpose: str, token: str) -> str:
    return keyed_hash(purpose, token)


async def issue(
    db: AsyncSession,
    purpose: str,
    user_id: uuid.UUID,
    email_normal: str,
    *,
    lifetime: timedelta,
    data: dict[str, Any] | None = None,
) -> str:
    """A new token for the link; the row joins the caller's transaction.
    `data` is kept beside it, never anything secret."""
    token = secrets.token_urlsafe(32)
    now = clock.now()
    db.add(
        Token(
            purpose=purpose,
            token_hash=token_hash(purpose, token),
            user_id=user_id,
            email_normal=email_normal,
            data=data or {},
            created_at=now,
            expires_at=now + lifetime,
        )
    )
    await db.flush()
    return token


async def void(db: AsyncSession, user_id: uuid.UUID, purposes: Iterable[str]) -> None:
    """Use up every live token of these purposes the account has. The caller
    holds the account's row lock (`accounts.lock`) and commits."""
    await db.execute(
        update(Token)
        .where(
            Token.user_id == user_id,
            Token.purpose.in_(tuple(purposes)),
            Token.used_at.is_(None),
        )
        .values(used_at=clock.now())
        .execution_options(synchronize_session=False)
    )


async def owner_of(db: AsyncSession, purpose: str, token: str) -> uuid.UUID | None:
    """Whose live token this is, locking nothing: a route that must lock the
    account before the token (so every path takes rows in one order) asks
    this first, then redeems. None when it was never issued, is used or has
    expired."""
    if not _LINK_TOKEN.fullmatch(token):
        return None
    owner: uuid.UUID | None = await db.scalar(
        select(Token.user_id).where(
            Token.purpose == purpose,
            Token.token_hash == token_hash(purpose, token),
            Token.used_at.is_(None),
            Token.expires_at > clock.now(),
        )
    )
    return owner


@dataclass(frozen=True)
class Redeemed:
    user_id: uuid.UUID
    email_normal: str | None
    #: What was kept beside the token at issue (never a secret).
    data: dict[str, Any] = field(default_factory=dict)


async def redeem(db: AsyncSession, purpose: str, token: str) -> Redeemed | None:
    """Mark the token used and give whose it is, or None when it was never
    issued, is used or has expired. The caller commits, or rolls back to leave
    it unused."""
    if not _LINK_TOKEN.fullmatch(token):
        return None
    now = clock.now()
    row = (
        await db.execute(
            update(Token)
            .where(
                Token.purpose == purpose,
                Token.token_hash == token_hash(purpose, token),
                Token.used_at.is_(None),
                Token.expires_at > now,
                Token.user_id.is_not(None),
            )
            .values(used_at=now)
            .returning(Token.user_id, Token.email_normal, Token.data)
        )
    ).first()
    if row is None or row.user_id is None:
        return None
    return Redeemed(row.user_id, row.email_normal, dict(row.data or {}))

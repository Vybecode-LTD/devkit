"""Accounts as the auth routes see them (SPEC.md 14.1 and 14.8;
docs/contracts/auth-api.md, `GET /api/auth/session`).

An address is looked up trimmed and lowercased (`auth_user.email_normal`), so
case variants find one account and share one rate-limit budget (14.6).

`view` is what a client is shown of an account: its roles, the permissions it
holds everywhere (resource overrides aside: those are asked per thing,
`kernel.auth.permissions.can`), and whether its address is verified and it
has a second factor. An owner holds every permission (14.8): every one a role
grants, and every one an installed module declares.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.auth.dependencies import has_second_factor
from kernel.auth.models import RolePermission, Session, User
from kernel.auth.permissions import OWNER, roles_of
from kernel.errors import Problem

#: The statuses that may sign in. Signing in cancels a pending deletion (14.7).
SIGNS_IN = frozenset({"active", "deleting"})


def normal_email(email: str) -> str:
    return email.strip().lower()


async def by_email(db: AsyncSession, email: str) -> User | None:
    found: User | None = await db.scalar(
        select(User).where(User.email_normal == normal_email(email))
    )
    return found


async def lock(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Lock the account row until the commit. A route that touches the
    account's one-time token rows takes this first, so every route takes
    rows in one order and none deadlocks another (decision 0021)."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


async def held(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> User:
    """Lock the account, before its factor, session and token rows, and look
    at it again: if this session ended meanwhile (a reset, a password change,
    a suspension), the other request stands and this one answers 401
    (decisions 0026 and 0027).

    The session's epoch is read on its own, and the loaded session row is left
    as it was: refreshing it would swap in the token hash another step-up just
    wrote, and a step-up replaces the token only while the hash this request
    came with is still current (Codex on #52)."""
    await lock(db, user_id)
    user = await db.get(User, user_id, populate_existing=True)
    epoch = await db.scalar(select(Session.epoch).where(Session.id == session_id))
    if user is None or user.status not in SIGNS_IN or epoch is None or epoch != user.session_epoch:
        await db.rollback()
        raise Problem("kernel.not_signed_in", 401, "Sign in to continue.")
    return user


async def permissions_of(
    db: AsyncSession, user_id: uuid.UUID, roles: set[str], declared: Iterable[str] = ()
) -> list[str]:
    """Every permission the account holds, sorted."""
    query = select(RolePermission.permission).distinct()
    if OWNER in roles:
        return sorted(set(await db.scalars(query)) | set(declared))
    if not roles:
        return []
    return sorted(set(await db.scalars(query.where(RolePermission.role_id.in_(roles)))))


async def view(db: AsyncSession, user: User, *, declared: Iterable[str] = ()) -> dict[str, Any]:
    roles = await roles_of(db, user.id)
    return {
        "id": str(user.id),
        "email": user.email,
        "roles": sorted(roles),
        "permissions": await permissions_of(db, user.id, roles, declared),
        "verified": user.email_verified_at is not None,
        "second_factor": await has_second_factor(db, user.id),
    }

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
from kernel.auth.models import RolePermission, User
from kernel.auth.permissions import OWNER, roles_of

#: The statuses that may sign in. Signing in cancels a pending deletion (14.7).
SIGNS_IN = frozenset({"active", "deleting"})


def normal_email(email: str) -> str:
    return email.strip().lower()


async def by_email(db: AsyncSession, email: str) -> User | None:
    found: User | None = await db.scalar(
        select(User).where(User.email_normal == normal_email(email))
    )
    return found


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

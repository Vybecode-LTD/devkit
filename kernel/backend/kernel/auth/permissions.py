"""Who holds which permission (SPEC.md 14.1 and 14.8).

Lifted from VybeMindz's per-resource overrides, reshaped to one `auth_user`
table and roles. The answer, in order:

1. An owner holds every permission, and no override takes one away.
2. On a resource, the person's own overrides decide first, then their roles'.
   At each level a denial beats a grant. With no override at either level,
   the roles' permissions decide, as they do with no resource.
3. A permission none of the person's roles holds is refused (deny by default).

Overrides are per resource: a grant on one forum category gives nothing
anywhere else, and a denial there takes nothing away elsewhere.
"""

from __future__ import annotations

import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel.auth.models import PermissionOverride, RolePermission, UserRole

OWNER = "owner"

#: `(resource_type, resource_id)`, such as `("community.category", "42")`.
Resource = tuple[str, str]


async def roles_of(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id))
    return set(rows)


async def can(
    db: AsyncSession,
    user_id: uuid.UUID,
    permission: str,
    *,
    resource: Resource | None = None,
) -> bool:
    """Whether the person holds `permission`, on `resource` when one is given."""
    roles = await roles_of(db, user_id)
    if OWNER in roles:
        return True
    if resource is not None:
        decided = await _override(db, user_id, roles, permission, resource)
        if decided is not None:
            return decided
    if not roles:
        return False
    held = await db.scalar(
        select(
            exists().where(
                RolePermission.role_id.in_(roles), RolePermission.permission == permission
            )
        )
    )
    return bool(held)


async def _override(
    db: AsyncSession,
    user_id: uuid.UUID,
    roles: set[str],
    permission: str,
    resource: Resource,
) -> bool | None:
    """What the overrides on this resource say, or None when they say nothing."""
    resource_type, resource_id = resource
    subject = PermissionOverride.user_id == user_id
    if roles:
        subject = or_(subject, PermissionOverride.role_id.in_(roles))
    rows = await db.execute(
        select(PermissionOverride.user_id, PermissionOverride.effect).where(
            PermissionOverride.permission == permission,
            PermissionOverride.resource_type == resource_type,
            PermissionOverride.resource_id == resource_id,
            subject,
        )
    )
    own: set[str] = set()
    theirs: set[str] = set()
    for person, effect in rows:
        (own if person is not None else theirs).add(effect)
    for effects in (own, theirs):
        if "deny" in effects:
            return False
        if "grant" in effects:
            return True
    return None

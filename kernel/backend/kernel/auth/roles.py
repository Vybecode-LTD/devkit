"""People and roles in the admin, at /api/auth/admin (K4 contract §2,
additions 4 and 5; SPEC.md 14.1 and 14.8; docs/contracts/auth-api.md, Staff).

- **`GET /admin/users?q=&cursor=&limit=`** (`auth.user.manage`): every account
  but a deleted one, the newest first, in pages (SPEC 7). `q` finds the
  addresses holding it, as typed, never as a pattern.
- **`PUT /admin/users/{id}/roles`** (`auth.role.assign`, step-up): the
  person's roles become the ones sent, and their next request gets a new
  session token (14.5).
- **`GET /admin/roles`** (`auth.user.manage`): every role with its permissions
  and how many hold it, and every permission declared.
- **`POST /admin/roles`, `PUT` and `DELETE /admin/roles/{id}`**
  (`auth.role.manage`, step-up): the site's own roles. The built-in ones stay
  as the manifests declare them.

**Who can grant what** (decision 0013). A role is granted or removed only by
someone holding every permission it carries; only an owner grants or removes
`owner`, and the last active owner keeps it. Only the roles a change adds or
removes are judged, so a role the caller couldn't grant may stay where it is.
`member`, which anyone gets by signing up, is no rank: a module's permission
for members never stops staff granting or removing it (as with suspensions,
`kernel.moderation`). Editing a role follows the same rule: every permission
the role has or would have must be the caller's.

**Locks.** A grant locks the caller's and the person's rows, in id order, as
a suspension does (`kernel.moderation`), and reads both again, so two grants
to one person take turns. Then it takes `owner`'s row for update when it
removes `owner`, so two people removing the last two owners at once can't both
count two, and a key-share lock on every other role it adds or removes. Deleting a role locks its row
for update, which waits for a grant of it being written and is waited for, so
a role never goes from under a grant (the grant finds it gone,
`auth.role_unknown`) and its holders are counted after. Changing a role locks
its row against other changes only (no key update), then raises its holders'
role versions.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from kernel import audit, events
from kernel.answers import answer
from kernel.auth.accounts import permissions_of
from kernel.auth.answers import People, Person, Roles, RoleView
from kernel.auth.dependencies import current_user, require_permission, require_recent_auth
from kernel.auth.models import Passkey, Role, RolePermission, Session, Totp, User, UserRole
from kernel.auth.permissions import OWNER, roles_of
from kernel.db import get_db
from kernel.errors import Problem

router = APIRouter()

MEMBER = "member"
#: The built-in roles in the order the Roles page shows them; any other
#: built-in role follows, then the site's own, by name.
BUILTIN_ORDER = ("owner", "admin", "editor", "member")
ROLE_ID = r"^[a-z][a-z0-9-]{1,63}$"
MAX_ROLES = 20
MAX_PERMISSIONS = 200

#: First, so a member is refused before being asked to confirm it's them.
_READER = [Depends(require_permission("auth.user.manage"))]
_ASSIGNER = [Depends(require_permission("auth.role.assign")), Depends(require_recent_auth())]
_EDITOR = [Depends(require_permission("auth.role.manage")), Depends(require_recent_auth())]

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_CURSOR = re.compile(r"([0-9]{1,19})\.([0-9a-f]{32})")

RoleId = Annotated[str, Path(alias="id", max_length=64)]


# --- what goes out ------------------------------------------------------------------


async def _people(db: AsyncSession, users: Sequence[User]) -> list[dict[str, Any]]:
    """The People list's items for `users`, in their order: four reads for
    the whole page, never one per person."""
    ids = [user.id for user in users]
    if not ids:
        return []
    roles: dict[uuid.UUID, list[str]] = {user_id: [] for user_id in ids}
    for user_id, role_id in await db.execute(
        select(UserRole.user_id, UserRole.role_id).where(UserRole.user_id.in_(ids))
    ):
        roles[user_id].append(role_id)
    totp = set(
        await db.scalars(
            select(Totp.user_id).where(Totp.user_id.in_(ids), Totp.confirmed_at.is_not(None))
        )
    )
    passkeys = set(await db.scalars(select(Passkey.user_id).where(Passkey.user_id.in_(ids))))
    seen: dict[uuid.UUID, datetime] = {  # noqa: C416 (a Result has keys(): dict() misreads it)
        user_id: last
        for user_id, last in await db.execute(
            select(Session.user_id, func.max(Session.last_seen_at))
            .where(Session.user_id.in_(ids))
            .group_by(Session.user_id)
        )
    }
    return [
        {
            "id": str(user.id),
            "email": user.email,
            "name": user.display_name or None,
            "roles": sorted(roles[user.id]),
            "verified": user.email_verified_at is not None,
            "second_factor": user.id in totp or user.id in passkeys,
            "status": user.status,
            "created_at": user.created_at.isoformat(),
            "last_seen_at": seen[user.id].isoformat() if user.id in seen else None,
        }
        for user in users
    ]


async def _role_views(
    db: AsyncSession, roles: Sequence[Role], declared: Iterable[str]
) -> list[dict[str, Any]]:
    """Each role with its permissions (an owner's are every one declared)
    and how many hold it."""
    ids = [role.id for role in roles]
    grants: dict[str, set[str]] = {role_id: set() for role_id in ids}
    for role_id, permission in await db.execute(
        select(RolePermission.role_id, RolePermission.permission).where(
            RolePermission.role_id.in_(ids)
        )
    ):
        grants[role_id].add(permission)
    if OWNER in grants:
        grants[OWNER] |= set(declared)
    people: dict[str, int] = {  # noqa: C416 (a Result has keys(): dict() misreads it)
        role_id: count
        for role_id, count in await db.execute(
            select(UserRole.role_id, func.count())
            .where(UserRole.role_id.in_(ids))
            .group_by(UserRole.role_id)
        )
    }
    return [
        {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "permissions": sorted(grants[role.id]),
            "people": people.get(role.id, 0),
            "builtin": role.builtin,
        }
        for role in roles
    ]


def _order(role: Role) -> tuple[int, int, str, str]:
    if role.id in BUILTIN_ORDER:
        return (0, BUILTIN_ORDER.index(role.id), "", "")
    return (1 if role.builtin else 2, 0, role.name.casefold(), role.id)


# --- People -------------------------------------------------------------------------


def _cursor_of(user: User) -> str:
    micros = (user.created_at - _EPOCH) // timedelta(microseconds=1)
    return f"{micros}.{user.id.hex}"


def _after(cursor: str) -> tuple[datetime, uuid.UUID]:
    found = _CURSOR.fullmatch(cursor)
    try:
        if found is None:
            raise ValueError(cursor)
        return _EPOCH + timedelta(microseconds=int(found[1])), uuid.UUID(hex=found[2])
    except (ValueError, OverflowError):
        raise Problem(
            "kernel.invalid_request",
            422,
            "Some of what was sent isn't valid.",
            errors={"cursor": ["Not a page of people."]},
        ) from None


@router.get("/admin/users", dependencies=_READER, response_model=People)
async def list_people(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=254),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    query = select(User).where(User.status != "deleted")
    if q:
        query = query.where(func.lower(User.email).contains(q.lower(), autoescape=True))
    if cursor is not None:
        at, last = _after(cursor)
        query = query.where((User.created_at < at) | ((User.created_at == at) & (User.id < last)))
    found = list(
        await db.scalars(query.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1))
    )
    page = found[:limit]
    return {
        "items": await _people(db, page),
        "next_cursor": _cursor_of(page[-1]) if len(found) > limit else None,
    }


class RolesOf(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    roles: list[Annotated[str, Field(max_length=64)]] = Field(max_length=MAX_ROLES)


def _not_yours(what: str) -> Problem:
    return Problem("auth.role_not_yours", 403, what)


async def _held(db: AsyncSession, request: Request, user_id: uuid.UUID) -> tuple[set[str], bool]:
    """What the caller holds now, and whether they're an owner."""
    roles = await roles_of(db, user_id)
    declared = request.app.state.declared_permissions
    return set(await permissions_of(db, user_id, roles, declared)), OWNER in roles


async def _grants(db: AsyncSession, role_ids: Iterable[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {role_id: set() for role_id in role_ids}
    for role_id, permission in await db.execute(
        select(RolePermission.role_id, RolePermission.permission).where(
            RolePermission.role_id.in_(list(found))
        )
    ):
        found[role_id].add(permission)
    return found


@router.put("/admin/users/{id}/roles", dependencies=_ASSIGNER, response_model=Person)
async def set_roles(
    request: Request,
    user_id: Annotated[uuid.UUID, Path(alias="id")],
    body: RolesOf,
    actor: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The person's roles become `roles`; see the module's docstring for who
    may grant what, and the locks."""
    wanted = set(body.roles)
    rows = await db.scalars(
        select(User)
        .where(User.id.in_({actor.id, user_id}))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    found = {row.id: row for row in rows}
    person = found.get(user_id)
    if person is None or person.status == "deleted":
        await db.rollback()
        raise Problem("kernel.not_found", 404, "There's no such person.")
    acting = found.get(actor.id)
    if acting is None or acting.status != "active":
        await db.rollback()
        raise Problem("auth.account_not_active", 409, "Your account is no longer active.")
    if person.status not in {"active", "suspended"}:
        await db.rollback()
        raise Problem("auth.account_not_active", 409, "This account is being deleted.")
    current = await roles_of(db, user_id)
    added, removed = sorted(wanted - current), sorted(current - wanted)
    if added or removed:
        await _lock_roles(db, added, removed)
        await _may_grant(db, request, actor.id, added, removed)
        if OWNER in removed and not await _others_active_owners(db, user_id):
            await db.rollback()
            raise Problem("auth.last_owner", 409, "The site's last owner stays an owner.")
        if removed:
            await db.execute(
                delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id.in_(removed))
            )
        if added:
            await db.execute(
                insert(UserRole),
                [
                    {"user_id": user_id, "role_id": role, "granted_by_id": actor.id}
                    for role in added
                ],
            )
        person.role_version += 1
        audit.record(
            db,
            "auth.user.roles_changed",
            actor=actor.id,
            target=("auth.user", user_id),
            subject=user_id,
            details={"added": added, "removed": removed},
            request=request,
        )
        await events.emit(
            db,
            "auth.user.role_changed",
            events.UserRoleChanged(user_id=user_id, added=added, removed=removed),
        )
        await db.flush()
    (item,) = await _people(db, [person])
    await db.commit()
    return item


async def _others_active_owners(db: AsyncSession, user_id: uuid.UUID) -> int:
    """How many active owners there are besides the person."""
    found = await db.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(User, User.id == UserRole.user_id)
        .where(UserRole.role_id == OWNER, User.status == "active", User.id != user_id)
    )
    return int(found or 0)


async def _lock_roles(db: AsyncSession, added: list[str], removed: list[str]) -> None:
    """`owner`'s row for update when it's removed, then a key-share lock on
    every other role added or removed; 422 for one that doesn't exist."""
    locking = sorted(set(added) | set(removed))
    if OWNER in removed:
        await db.execute(select(Role.id).where(Role.id == OWNER).with_for_update())
        locking.remove(OWNER)
    existing = set(
        await db.scalars(
            select(Role.id)
            .where(Role.id.in_(locking))
            .order_by(Role.id)
            .with_for_update(read=True, key_share=True)
        )
    )
    unknown = sorted(set(added) - existing - {OWNER})
    if unknown:
        await db.rollback()
        raise Problem(
            "auth.role_unknown",
            422,
            "There's no such role.",
            errors={"roles": [f"No role is called {role}." for role in unknown]},
        )


async def _may_grant(
    db: AsyncSession, request: Request, actor: uuid.UUID, added: list[str], removed: list[str]
) -> None:
    """403 unless the caller may grant every role added and remove every
    role removed (decision 0013; `member` is no rank)."""
    held, owner = await _held(db, request, actor)
    if owner:
        return
    if OWNER in added or OWNER in removed:
        await db.rollback()
        raise _not_yours("Only an owner grants or removes the owner role.")
    judged = [role for role in added + removed if role != MEMBER]
    if any(not permissions <= held for permissions in (await _grants(db, judged)).values()):
        await db.rollback()
        raise _not_yours("You can grant or remove only a role whose permissions you all hold.")


# --- Roles --------------------------------------------------------------------------


@router.get("/admin/roles", dependencies=_READER, response_model=Roles)
async def list_roles(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    roles = sorted(await db.scalars(select(Role)), key=_order)
    listed = request.app.state.permissions_listed
    return {
        "roles": await _role_views(db, roles, request.app.state.declared_permissions),
        "permissions": [dict(item) for item in listed],
    }


class RoleChange(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=500)
    permissions: list[Annotated[str, Field(max_length=128)]] = Field(max_length=MAX_PERMISSIONS)

    @field_validator("name")
    @classmethod
    def _named(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("A role needs a name.")
        return name

    @field_validator("description")
    @classmethod
    def _described(cls, description: str) -> str:
        return description.strip()


class NewRole(RoleChange):
    id: str = Field(pattern=ROLE_ID)


def _known(request: Request, permissions: Iterable[str]) -> set[str]:
    """The permissions, each once, all declared; else 422."""
    wanted = set(permissions)
    unknown = sorted(wanted - request.app.state.declared_permissions)
    if unknown:
        raise Problem(
            "auth.permission_unknown",
            422,
            "No module declares that permission.",
            errors={"permissions": [f"Nothing declares {key}." for key in unknown]},
        )
    return wanted


async def _yours(db: AsyncSession, request: Request, actor: User, permissions: set[str]) -> None:
    held, owner = await _held(db, request, actor.id)
    if not owner and not permissions <= held:
        await db.rollback()
        raise _not_yours("A role can carry only permissions you hold.")


async def _role(db: AsyncSession, role_id: str, *, lock: str) -> Role:
    """The site's own role, locked; 404 or 409 for a built-in one."""
    found = await db.scalar(select(Role).where(Role.id == role_id))
    if found is None:
        raise Problem("auth.role_not_found", 404, "There's no such role.")
    if found.builtin:
        raise Problem(
            "auth.role_builtin",
            409,
            "A built-in role stays as the site's modules declare it.",
        )
    locked = select(Role).where(Role.id == role_id).execution_options(populate_existing=True)
    # FOR NO KEY UPDATE keeps out other changes but not grants of the role;
    # FOR UPDATE keeps out grants too (their key-share lock).
    locked = locked.with_for_update(key_share=lock == "no_key")
    role = await db.scalar(locked)
    if role is None:  # deleted while this waited
        raise Problem("auth.role_not_found", 404, "There's no such role.")
    return role


async def _one_view(db: AsyncSession, request: Request, role: Role) -> dict[str, Any]:
    (view,) = await _role_views(db, [role], request.app.state.declared_permissions)
    return view


@router.post("/admin/roles", dependencies=_EDITOR, status_code=201, response_model=RoleView)
async def create_role(
    request: Request,
    body: NewRole,
    actor: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    permissions = _known(request, body.permissions)
    await _yours(db, request, actor, permissions)
    made = await db.scalar(
        pg_insert(Role)
        .values(id=body.id, name=body.name, description=body.description, builtin=False)
        .on_conflict_do_nothing(index_elements=[Role.id])
        .returning(Role.id)
    )
    if made is None:
        await db.rollback()
        raise Problem("auth.role_exists", 409, "A role already has that id.")
    if permissions:
        await db.execute(
            insert(RolePermission),
            [{"role_id": body.id, "permission": key} for key in sorted(permissions)],
        )
    audit.record(
        db,
        "auth.role.created",
        actor=actor.id,
        target=("auth.role", body.id),
        details={"permissions": sorted(permissions)},
        request=request,
    )
    await db.commit()
    view = {
        "id": body.id,
        "name": body.name,
        "description": body.description,
        "permissions": sorted(permissions),
        "people": 0,
        "builtin": False,
    }
    return answer(RoleView, view, status_code=201)


@router.put("/admin/roles/{id}", dependencies=_EDITOR, response_model=RoleView)
async def change_role(
    request: Request,
    role_id: RoleId,
    body: RoleChange,
    actor: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    role = await _role(db, role_id, lock="no_key")
    permissions = _known(request, body.permissions)
    before = (await _grants(db, [role_id]))[role_id]
    await _yours(db, request, actor, before | permissions)
    added, removed = sorted(permissions - before), sorted(before - permissions)
    renamed = (role.name, role.description) != (body.name, body.description)
    if removed:
        await db.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id, RolePermission.permission.in_(removed)
            )
        )
    if added:
        await db.execute(
            insert(RolePermission), [{"role_id": role_id, "permission": key} for key in added]
        )
    if added or removed:
        holders = select(UserRole.user_id).where(UserRole.role_id == role_id)
        await db.execute(
            update(User)
            .where(User.id.in_(holders))
            .values(role_version=User.role_version + 1)
            .execution_options(synchronize_session=False)
        )
    role.name, role.description = body.name, body.description
    if added or removed or renamed:
        audit.record(
            db,
            "auth.role.changed",
            actor=actor.id,
            target=("auth.role", role_id),
            details={"added": added, "removed": removed},
            request=request,
        )
    await db.flush()
    view = await _one_view(db, request, role)
    await db.commit()
    return view


@router.delete("/admin/roles/{id}", dependencies=_EDITOR, status_code=204)
async def delete_role(
    request: Request,
    role_id: RoleId,
    actor: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _role(db, role_id, lock="update")
    await _yours(db, request, actor, (await _grants(db, [role_id]))[role_id])
    held_by = await db.scalar(
        select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
    )
    if held_by:
        await db.rollback()
        raise Problem(
            "auth.role_in_use",
            409,
            "Someone holds this role. Take it from them first.",
            extra={"people": held_by},
        )
    await db.execute(delete(Role).where(Role.id == role_id))
    audit.record(
        db, "auth.role.deleted", actor=actor.id, target=("auth.role", role_id), request=request
    )
    await db.commit()
    return Response(status_code=204)

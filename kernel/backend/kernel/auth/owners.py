"""The site's first owner, made from the server (SPEC.md 14.1; the K5 contract
§2 and §8 answer 2; decision 0051): `python -m app.owner <email>`, and
`mechframe create-owner`, which runs it.

`create_owner(db, email)` answers a one-time link token to set the account's
password: the reset's own (`/auth/reset?token=…`, valid 30 minutes, single
use), so the reset screen and its checks take it from there. Nothing is
mailed and no password is typed into a terminal: whoever ran the command is
shown the link. Using it marks the address verified (`resets.py`).

- **No active owner yet:** the address's account gets the owner role (and
  `member`, as every account has). With no account for it, one is made.
- **An owner already:** only an owner's own address goes on, and gets a fresh
  link, recovery from the server; any other address is refused, since owners
  are then granted in Admin, People (the owner, 2026-11-20).
- **Either way** the account's password is cleared, every session ends and
  every live way in is voided before the link is issued, so whoever held the
  account (someone who signed up with the address first) holds nothing until
  the link is used. A second factor stays, as a reset leaves it.

`owner`'s role row is locked first, so two runs at once take turns: the
second finds the first's owner. A suspended or deleted account isn't made an
owner. Every run is audited as `ACTION`: `made`, `granted`, `renewed` or
`refused`.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, events
from kernel.auth import accounts, resets, sessions, tokens
from kernel.auth.models import Role, User, UserRole
from kernel.auth.permissions import OWNER
from kernel.email import MAX_ADDRESS, is_address

ACTION = "auth.user.owner_link_issued"
_MEMBER = "member"
_RESET = "reset_password"
#: Every way in a run ends, as a reset does, before its link.
_ENDED = ("sign_in_code", "magic_link", _RESET, "second_factor")


class OwnerRefused(Exception):
    """No owner was made and no link issued; the message says why."""


def _record(db: AsyncSession, result: str, subject: User | None) -> None:
    audit.record(
        db,
        ACTION,
        actor=None,
        subject=subject.id if subject is not None else None,
        target=("auth.user", subject.id) if subject is not None else None,
        result=result,
    )


async def _active_owner(db: AsyncSession) -> bool:
    found = exists().where(
        UserRole.role_id == OWNER, UserRole.user_id == User.id, User.status == "active"
    )
    return bool(await db.scalar(select(found)))


async def _is_owner(db: AsyncSession, user: User) -> bool:
    found = exists().where(UserRole.user_id == user.id, UserRole.role_id == OWNER)
    return bool(await db.scalar(select(found)))


async def create_owner(db: AsyncSession, email: str) -> str:
    """Make `email`'s account the site's owner and answer its one-time link
    token. Commits. Raises OwnerRefused, having changed nothing but the audit."""
    written = email.strip()
    if len(written) > MAX_ADDRESS or not is_address(written):
        raise OwnerRefused(f"{email!r} isn't an email address, like name@example.com.")
    normal = accounts.normal_email(written)
    await db.execute(select(Role.id).where(Role.id == OWNER).with_for_update())
    user: User | None = await db.scalar(
        select(User).where(User.email_normal == normal).with_for_update()
    )
    is_owner = user is not None and await _is_owner(db, user)
    if not is_owner and await _active_owner(db):
        _record(db, "refused", user)
        await db.commit()
        raise OwnerRefused(
            f"The site has an owner already, and {written} isn't one: only an owner's own "
            "address gets a new link here. An owner grants the role in Admin, People."
        )
    if user is not None and user.status not in accounts.SIGNS_IN:
        _record(db, "refused", user)
        await db.commit()
        raise OwnerRefused(
            f"The account for {written} is {user.status}: it can't be made the owner."
        )
    if user is None:
        user = User(email=written, email_normal=normal)
        db.add(user)
        await db.flush()
        await db.refresh(user)  # the columns the database fills in
        db.add_all([UserRole(user_id=user.id, role_id=role) for role in (_MEMBER, OWNER)])
        await events.emit(db, "auth.user.created", events.UserCreated(user_id=user.id))
        await events.emit(
            db,
            "auth.user.role_changed",
            events.UserRoleChanged(user_id=user.id, added=[OWNER, _MEMBER], removed=[]),
        )
        result = "made"
    elif not is_owner:
        db.add(UserRole(user_id=user.id, role_id=OWNER))
        user.role_version += 1
        await events.emit(
            db,
            "auth.user.role_changed",
            events.UserRoleChanged(user_id=user.id, added=[OWNER], removed=[]),
        )
        result = "granted"
    else:
        result = "renewed"
    user.password_hash = None
    await sessions.end_all(db, user)
    await tokens.void(db, user.id, _ENDED)
    token = await tokens.issue(db, _RESET, user.id, normal, lifetime=resets.LIFETIME)
    _record(db, result, user)
    await db.commit()
    return token


def link(site_url: str, token: str) -> str:
    """Where `token` is used: the reset screen, on `site_url` when it's set."""
    return f"{site_url.rstrip('/')}/auth/reset?token={token}"

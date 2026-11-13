"""The access dependencies every route declares (SPEC.md 6, 7, 14.4, 14.5, 14.8).

    @router.get("/drafts", dependencies=[Depends(require_permission("blog.post.edit"))])
    @router.post("/me/email", dependencies=[Depends(require_recent_auth())])
    async def mine(user: User = Depends(current_user)) -> ...

- `current_user`: the signed-in account, or 401 `kernel.not_signed_in`.
- `optional_user`: the same, or None. A route using it is public.
- `require_permission(key)`: 403 `kernel.forbidden` unless the account holds
  `key` (`permissions.can`; owners hold everything).
- `require_owner_or(permission)`: a guard whose `check(owner_id)` lets through
  the resource's owner, or staff holding the permission, else 403.
- `require_recent_auth(minutes=10)`: 403 `auth.step_up_required` unless the
  session signed in or stepped up that recently (14.4).

Each one sets its access mark (`kernel.access`), so the route audit can tell a
declared route from an open one.

**The admin gate.** Under `/api/<id>/admin`, every dependency above but
`optional_user` (which marks a route public, and an admin route can't be) also
wants a staff role, else 403 `kernel.forbidden`, and a confirmed second factor
on the account (a confirmed TOTP or a passkey), else 403
`auth.second_factor_required`. Only then does the route's own permission count.

**Rate limits by account.** Signing in sets `request.state.user_id`, which
`rate_limit(key="account")` reads. FastAPI runs a route's dependencies in
order, so list the access dependency before the limit.

**A replaced token.** When `sessions.resume` replaces the token (after a role
change), the old one is already dead, so the new cookie has to reach the
browser whatever the route answers, a 403 or a 404 included. The dependency
leaves it on the request, and `SessionCookies`, a middleware that wraps the
error handlers, adds it to the response.

Session lifetimes come from `app.state.session_lifetimes` when it's set, else
the spec's defaults; the site settings (Q6) arrive with their admin page.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kernel.access import ACCESS_MARK, STEP_UP_MARK
from kernel.auth import sessions
from kernel.auth.models import Passkey, Totp, User
from kernel.auth.permissions import Resource, can
from kernel.auth.sessions import DEFAULT_LIFETIMES, Lifetimes, Resumed
from kernel.db import get_db
from kernel.errors import Problem

#: Where a replaced token waits on the request for `SessionCookies`.
_REPLACED = "devkit_replaced_session"


def _mark[F: Callable[..., Any]](dependency: F, access: str, *, step_up: bool = False) -> F:
    setattr(dependency, ACCESS_MARK, access)
    if step_up:
        setattr(dependency, STEP_UP_MARK, True)
    return dependency


def lifetimes_of(request: Request) -> Lifetimes:
    found = getattr(request.app.state, "session_lifetimes", None)
    return found if isinstance(found, Lifetimes) else DEFAULT_LIFETIMES


def route_path(request: Request) -> str:
    """The path the router matched: without the ASGI `root_path` a proxy's
    prefix adds (`--root-path /site`). Starlette's own rule (`get_route_path`):
    the prefix comes off only at a segment boundary, so with root "/a" the path
    "/api/x" stays whole, as the router reads it."""
    path: str = request.scope["path"]
    root: str = request.scope.get("root_path", "")
    if not root or not path.startswith(root):
        return path
    if path == root:
        return ""
    if path[len(root)] == "/":
        return path[len(root) :]
    return path


def is_admin_path(path: str) -> bool:
    """`/api/<id>/admin` and below: the segment after the module's, never any
    later segment, so `/api/blog/posts/admin` is an ordinary path. Pass it the
    route's path (`route_path`), never the URL's."""
    parts = path.split("/")
    return len(parts) > 3 and parts[1] == "api" and parts[3] == "admin"


async def has_second_factor(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """A confirmed TOTP or a passkey (14.4); recovery codes alone aren't one."""
    totp = exists().where(Totp.user_id == user_id, Totp.confirmed_at.is_not(None))
    passkey = exists().where(Passkey.user_id == user_id)
    return bool(await db.scalar(select(or_(totp, passkey))))


async def _resume(request: Request, db: AsyncSession) -> Resumed | None:
    token = request.cookies.get(sessions.SESSION_COOKIE)
    if not token:
        return None
    resumed = await sessions.resume(db, token, lifetimes=lifetimes_of(request))
    if resumed is None:
        return None
    if resumed.token is not None:
        setattr(request.state, _REPLACED, (resumed.token, resumed.session))
    request.state.user_id = str(resumed.user.id)
    return resumed


async def signed_in(request: Request, db: AsyncSession = Depends(get_db)) -> Resumed:
    """The live session, through the admin gate on admin paths."""
    resumed = await _resume(request, db)
    if resumed is None:
        raise Problem("kernel.not_signed_in", 401, "Sign in to continue.")
    if is_admin_path(route_path(request)):
        if not resumed.staff:
            raise Problem("kernel.forbidden", 403, "The admin is for staff.")
        if not await has_second_factor(db, resumed.user.id):
            raise Problem(
                "auth.second_factor_required",
                403,
                "Set up a second factor before using the admin.",
            )
    return resumed


async def current_user(resumed: Resumed = Depends(signed_in)) -> User:
    """The signed-in account, or 401."""
    return resumed.user


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    """The signed-in account, or None. A route using it is public."""
    resumed = await _resume(request, db)
    return resumed.user if resumed else None


_mark(current_user, "member")
_mark(optional_user, "public")


def require_permission(key: str) -> Callable[..., Awaitable[User]]:
    """403 unless the signed-in account holds `key`; gives the account."""

    async def dependency(
        resumed: Resumed = Depends(signed_in), db: AsyncSession = Depends(get_db)
    ) -> User:
        if not await can(db, resumed.user.id, key):
            raise Problem("kernel.forbidden", 403, "You don't have permission to do that.")
        return resumed.user

    return _mark(dependency, "permission")


class OwnerOr:
    """The guard `require_owner_or` gives a route. The route loads the thing,
    then calls `await guard.check(thing.owner_id)` before touching it."""

    def __init__(self, user: User, permission: str, db: AsyncSession, *, staff: bool) -> None:
        self.user = user
        self.permission = permission
        self.staff = staff
        self._db = db

    async def check(self, owner_id: uuid.UUID | None, *, resource: Resource | None = None) -> None:
        """Returns for the owner, or for staff holding the permission (on
        `resource`, when given; 14.8); otherwise 403. A member's personal grant
        never opens someone else's thing."""
        if owner_id is not None and owner_id == self.user.id:
            return
        if self.staff and await can(self._db, self.user.id, self.permission, resource=resource):
            return
        raise Problem("kernel.forbidden", 403, "You don't have permission to do that.")


def require_owner_or(permission: str) -> Callable[..., Awaitable[OwnerOr]]:
    """Your own, or staff with the permission (14.8): gives an `OwnerOr`."""

    async def dependency(
        resumed: Resumed = Depends(signed_in), db: AsyncSession = Depends(get_db)
    ) -> OwnerOr:
        return OwnerOr(resumed.user, permission, db, staff=resumed.staff)

    return _mark(dependency, "owner_or")


def require_recent_auth(minutes: int = 10) -> Callable[..., Awaitable[User]]:
    """403 `auth.step_up_required` unless the session signed in or stepped up
    within `minutes` (14.4); gives the account."""
    within = timedelta(minutes=minutes)

    async def dependency(resumed: Resumed = Depends(signed_in)) -> User:
        if not sessions.recent(resumed.session, within=within):
            raise Problem("auth.step_up_required", 403, "Confirm it's you to continue.")
        return resumed.user

    return _mark(dependency, "member", step_up=True)


class SessionCookies:
    """Sets the session cookie a dependency replaced during this request, on
    whatever response goes out (see the module's docstring)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                waiting = scope.get("state", {}).get(_REPLACED)
                if waiting is not None:
                    carrier = Response()
                    sessions.set_session_cookie(carrier, *waiting)
                    headers = MutableHeaders(scope=message)
                    for value in carrier.headers.getlist("set-cookie"):
                        headers.append("set-cookie", value)
            await send(message)

        await self.app(scope, receive, send_with_cookie)

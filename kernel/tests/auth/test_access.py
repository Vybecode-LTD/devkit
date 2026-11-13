"""The access dependencies and who holds which permission (SPEC.md 6, 7, 14.1,
14.4, 14.5 and 14.8; docs/contracts/auth-api.md, "Staff").

Each HTTP test signs a person in with `sessions.start` and calls a small demo
router mounted on a real app, so the cookie, the problem details and the
middleware run as they will on a site."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Receive, Scope, Send

from kernel import clock
from kernel.access import STEP_UP_MARK, access_of, undeclared
from kernel.auth import sessions
from kernel.auth.dependencies import (
    OwnerOr,
    SessionCookies,
    current_user,
    optional_user,
    require_owner_or,
    require_permission,
    require_recent_auth,
)
from kernel.auth.models import (
    Passkey,
    PermissionOverride,
    Role,
    RolePermission,
    Totp,
    User,
    UserRole,
)
from kernel.auth.permissions import can
from kernel.errors import Problem
from kernel.ratelimit import rate_limit

from ..conftest import SITE, AppFactory, Client

PUBLISH = "demo.post.publish"
STATS = "demo.stats.read"
EDIT = "demo.comment.edit"
CATEGORY = "demo.category"


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


# --- people, roles and sessions ----------------------------------------------------


async def _user(db: AsyncSession, *roles: str) -> User:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@site.test"
    user = User(id=user_id, email=email, email_normal=email, session_epoch=0, role_version=0)
    db.add(user)
    await db.flush()
    for role in roles or ("member",):
        db.add(UserRole(user_id=user_id, role_id=role))
    await db.commit()
    return user


async def _role(db: AsyncSession, *permissions: str) -> str:
    """A custom role of this test's own, holding these permissions."""
    role_id = f"role-{uuid.uuid4().hex[:10]}"
    db.add(Role(id=role_id, name=role_id))
    await db.flush()
    for permission in permissions:
        db.add(RolePermission(role_id=role_id, permission=permission))
    await db.commit()
    return role_id


async def _override(
    db: AsyncSession,
    effect: str,
    resource: str,
    *,
    user: User | None = None,
    role: str | None = None,
    permission: str = PUBLISH,
) -> None:
    db.add(
        PermissionOverride(
            user_id=user.id if user else None,
            role_id=role,
            permission=permission,
            resource_type=CATEGORY,
            resource_id=resource,
            effect=effect,
        )
    )
    await db.commit()


async def _token(db: AsyncSession, user: User) -> str:
    token, _ = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    return token


async def _totp(db: AsyncSession, user: User, *, confirmed: bool = True) -> None:
    db.add(
        Totp(
            user_id=user.id,
            secret_sealed="sealed",
            confirmed_at=clock.now() if confirmed else None,
        )
    )
    await db.commit()


async def _passkey(db: AsyncSession, user: User) -> None:
    db.add(Passkey(user_id=user.id, credential_id=os.urandom(16), public_key=b"key", name="Laptop"))
    await db.commit()


def _as(token: str) -> dict[str, str]:
    return {"cookie": f"{sessions.SESSION_COOKIE}={token}"}


def _code(response: httpx.Response) -> str:
    assert response.headers["content-type"].startswith("application/problem+json")
    code: str = response.json()["code"]
    return code


def _session_cookie(response: httpx.Response) -> str | None:
    for value in response.headers.get_list("set-cookie"):
        name, _, rest = value.partition("=")
        if name == sessions.SESSION_COOKIE:
            return rest.split(";", 1)[0]
    return None


# --- the demo app ------------------------------------------------------------------


def _demo_router() -> APIRouter:
    router = APIRouter()

    @router.get("/me")
    async def me(user: User = Depends(current_user)) -> dict[str, str]:
        return {"id": str(user.id)}

    @router.get("/maybe")
    async def maybe(user: User | None = Depends(optional_user)) -> dict[str, str | None]:
        return {"id": str(user.id) if user else None}

    @router.get("/publish")
    async def publish(user: User = Depends(require_permission(PUBLISH))) -> dict[str, str]:
        return {"id": str(user.id)}

    @router.get("/fresh", dependencies=[Depends(require_recent_auth())])
    async def fresh() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/admin/stats", dependencies=[Depends(require_permission(STATS))])
    async def stats() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/admin/ping", dependencies=[Depends(current_user)])
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/posts/{slug}", dependencies=[Depends(current_user)])
    async def post(slug: str) -> dict[str, str]:
        return {"slug": slug}

    @router.get(
        "/limited",
        dependencies=[Depends(current_user), Depends(rate_limit("1/1m", key="account"))],
    )
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/missing", dependencies=[Depends(current_user)])
    async def missing() -> None:
        raise Problem("demo.post_not_found", 404)

    @router.get("/comments/{owner_id}")
    async def comment(
        owner_id: uuid.UUID, guard: OwnerOr = Depends(require_owner_or(EDIT))
    ) -> dict[str, bool]:
        await guard.check(owner_id)
        return {"ok": True}

    return router


@pytest.fixture
def demo_app(app_factory: AppFactory) -> object:
    app = app_factory()
    app.include_router(_demo_router(), prefix="/api/demo")
    return app


@pytest_asyncio.fixture(loop_scope="session")
async def client(demo_app: object) -> AsyncIterator[httpx.AsyncClient]:
    async with Client(demo_app) as http:  # type: ignore[arg-type]
        yield http


# --- permissions (14.8) ------------------------------------------------------------


async def test_the_owner_holds_every_permission_and_no_override_takes_one(
    db: AsyncSession,
) -> None:
    owner = await _user(db, "owner")
    await _override(db, "deny", "c1", user=owner)
    assert await can(db, owner.id, "anything.at.all")
    assert await can(db, owner.id, PUBLISH, resource=(CATEGORY, "c1"))


async def test_a_role_grants_its_permissions_and_nothing_else(db: AsyncSession) -> None:
    role = await _role(db, PUBLISH)
    writer = await _user(db, role)
    member = await _user(db)
    assert await can(db, writer.id, PUBLISH)
    assert not await can(db, writer.id, STATS)
    assert not await can(db, member.id, PUBLISH)


async def test_a_role_override_grants_on_that_one_resource(db: AsyncSession) -> None:
    role = await _role(db)
    await _override(db, "grant", "c1", role=role)
    user = await _user(db, role)
    assert await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))
    assert not await can(db, user.id, PUBLISH, resource=(CATEGORY, "c2"))
    assert not await can(db, user.id, PUBLISH)


async def test_a_role_override_denies_on_that_one_resource(db: AsyncSession) -> None:
    role = await _role(db, PUBLISH)
    await _override(db, "deny", "c1", role=role)
    user = await _user(db, role)
    assert not await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))
    assert await can(db, user.id, PUBLISH, resource=(CATEGORY, "c2"))
    assert await can(db, user.id, PUBLISH)


async def test_between_roles_a_denial_beats_a_grant(db: AsyncSession) -> None:
    granting, denying = await _role(db), await _role(db)
    await _override(db, "grant", "c1", role=granting)
    await _override(db, "deny", "c1", role=denying)
    user = await _user(db, granting, denying)
    assert not await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))


async def test_a_persons_own_grant_beats_their_roles_denial(db: AsyncSession) -> None:
    role = await _role(db, PUBLISH)
    await _override(db, "deny", "c1", role=role)
    user = await _user(db, role)
    await _override(db, "grant", "c1", user=user)
    assert await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))


async def test_a_persons_own_denial_beats_their_roles_grant(db: AsyncSession) -> None:
    role = await _role(db, PUBLISH)
    await _override(db, "grant", "c1", role=role)
    user = await _user(db, role)
    await _override(db, "deny", "c1", user=user)
    assert not await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))
    assert await can(db, user.id, PUBLISH, resource=(CATEGORY, "c2"))


async def test_a_persons_own_denial_beats_their_own_grant(db: AsyncSession) -> None:
    user = await _user(db)
    await _override(db, "grant", "c1", user=user)
    await _override(db, "deny", "c1", user=user)
    assert not await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))


async def test_an_account_with_no_role_holds_nothing(db: AsyncSession) -> None:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@site.test"
    db.add(User(id=user_id, email=email, email_normal=email, session_epoch=0, role_version=0))
    await db.commit()
    assert not await can(db, user_id, PUBLISH)
    assert not await can(db, user_id, PUBLISH, resource=(CATEGORY, "c1"))


async def test_an_override_for_another_permission_changes_nothing(db: AsyncSession) -> None:
    user = await _user(db)
    await _override(db, "grant", "c1", user=user, permission=STATS)
    assert not await can(db, user.id, PUBLISH, resource=(CATEGORY, "c1"))


# --- marks (section 7) -------------------------------------------------------------


def test_each_dependency_declares_its_access() -> None:
    assert access_of(current_user) == "member"
    assert access_of(optional_user) == "public"
    assert access_of(require_permission(PUBLISH)) == "permission"
    assert access_of(require_owner_or(EDIT)) == "owner_or"
    step_up = require_recent_auth()
    assert access_of(step_up) == "member"
    assert getattr(step_up, STEP_UP_MARK) is True
    assert not getattr(current_user, STEP_UP_MARK, False)


async def test_session_cookies_passes_other_traffic_through_untouched() -> None:
    seen: list[Scope] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    scope: Scope = {"type": "websocket", "state": {}}
    await SessionCookies(inner)(scope, _never, _never)
    assert seen == [scope]


async def _never(*_: object) -> Any:
    raise AssertionError("not called")


def test_routes_using_them_pass_the_route_audit(demo_app: object) -> None:
    assert undeclared(demo_app) == []  # type: ignore[arg-type]


# --- current_user and optional_user ------------------------------------------------


async def test_no_cookie_a_wrong_one_or_an_ended_session_is_not_signed_in(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    token = await _token(db, user)
    assert (await client.get("/api/demo/me", headers=_as(token))).status_code == 200
    await sessions.end_all(db, user)
    await db.commit()
    for headers in ({}, _as("not-a-token"), _as(token)):
        response = await client.get("/api/demo/me", headers=headers)
        assert response.status_code == 401
        assert _code(response) == "kernel.not_signed_in"


async def test_current_user_is_the_sessions_account(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    response = await client.get("/api/demo/me", headers=_as(await _token(db, user)))
    assert response.json() == {"id": str(user.id)}


async def test_optional_user_is_none_rather_than_401(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    token = await _token(db, user)
    assert (await client.get("/api/demo/maybe")).json() == {"id": None}
    assert (await client.get("/api/demo/maybe", headers=_as("stale"))).json() == {"id": None}
    assert (await client.get("/api/demo/maybe", headers=_as(token))).json() == {"id": str(user.id)}


async def test_a_role_change_sends_a_new_cookie_and_the_old_one_dies(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    old = await _token(db, user)
    await db.execute(update(User).where(User.id == user.id).values(role_version=1))
    await db.commit()
    response = await client.get("/api/demo/me", headers=_as(old))
    assert response.status_code == 200
    new = _session_cookie(response)
    assert new
    assert new != old
    cookie = next(v for v in response.headers.get_list("set-cookie") if v.startswith("__Host-"))
    attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")[1:]}
    assert {"httponly", "secure", "samesite", "path", "max-age"} <= attributes
    client.cookies.clear()
    assert (await client.get("/api/demo/me", headers=_as(old))).status_code == 401
    assert (await client.get("/api/demo/me", headers=_as(new))).status_code == 200


async def test_the_new_cookie_goes_out_even_when_the_route_answers_an_error(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    old = await _token(db, user)
    await db.execute(update(User).where(User.id == user.id).values(role_version=1))
    await db.commit()
    response = await client.get("/api/demo/missing", headers=_as(old))
    assert response.status_code == 404
    new = _session_cookie(response)
    assert new
    assert new != old
    client.cookies.clear()
    assert (await client.get("/api/demo/me", headers=_as(new))).status_code == 200


async def test_an_unchanged_session_sets_no_cookie(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    response = await client.get("/api/demo/me", headers=_as(await _token(db, user)))
    assert _session_cookie(response) is None


async def test_account_rate_limits_count_per_person_not_per_address(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    first, second = await _user(db), await _user(db)
    first_token, second_token = await _token(db, first), await _token(db, second)
    assert (await client.get("/api/demo/limited", headers=_as(first_token))).status_code == 200
    over = await client.get("/api/demo/limited", headers=_as(first_token))
    assert over.status_code == 429
    assert (await client.get("/api/demo/limited", headers=_as(second_token))).status_code == 200


# --- require_permission and require_owner_or ---------------------------------------


async def test_require_permission_answers_403_without_it(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    writer = await _user(db, await _role(db, PUBLISH))
    member = await _user(db)
    owner = await _user(db, "owner")
    refused = await client.get("/api/demo/publish", headers=_as(await _token(db, member)))
    assert refused.status_code == 403
    assert _code(refused) == "kernel.forbidden"
    for person in (writer, owner):
        response = await client.get("/api/demo/publish", headers=_as(await _token(db, person)))
        assert response.status_code == 200
    assert (await client.get("/api/demo/publish")).status_code == 401


async def test_require_owner_or_lets_the_owner_or_a_permission_holder_through(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    author, other = await _user(db), await _user(db)
    moderator = await _user(db, await _role(db, EDIT))
    as_author = _as(await _token(db, author))
    assert (
        await client.get(f"/api/demo/comments/{author.id}", headers=as_author)
    ).status_code == 200
    refused = await client.get(f"/api/demo/comments/{other.id}", headers=as_author)
    assert refused.status_code == 403
    assert _code(refused) == "kernel.forbidden"
    as_moderator = _as(await _token(db, moderator))
    assert (
        await client.get(f"/api/demo/comments/{other.id}", headers=as_moderator)
    ).status_code == 200
    assert (await client.get(f"/api/demo/comments/{author.id}")).status_code == 401


# --- require_recent_auth (14.4) ----------------------------------------------------


async def test_require_recent_auth_wants_a_sign_in_within_ten_minutes(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    user = await _user(db)
    token, session = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    assert (await client.get("/api/demo/fresh", headers=_as(token))).status_code == 200
    clock.advance(11 * 60)
    stale = await client.get("/api/demo/fresh", headers=_as(token))
    assert stale.status_code == 403
    assert _code(stale) == "auth.step_up_required"
    fresh = await sessions.step_up(db, session)
    await db.commit()
    assert fresh is not None
    assert (await client.get("/api/demo/fresh", headers=_as(fresh))).status_code == 200


# --- the admin gate (contract, "Staff") --------------------------------------------


async def test_admin_routes_need_a_session_then_staff_then_a_second_factor(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    member = await _user(db)
    editor = await _user(db, "editor")
    path = "/api/demo/admin/ping"
    nobody = await client.get(path)
    assert (nobody.status_code, _code(nobody)) == (401, "kernel.not_signed_in")
    as_member = await client.get(path, headers=_as(await _token(db, member)))
    assert (as_member.status_code, _code(as_member)) == (403, "kernel.forbidden")
    as_editor = _as(await _token(db, editor))
    no_factor = await client.get(path, headers=as_editor)
    assert (no_factor.status_code, _code(no_factor)) == (403, "auth.second_factor_required")
    await _totp(db, editor, confirmed=False)
    unconfirmed = await client.get(path, headers=as_editor)
    assert (unconfirmed.status_code, _code(unconfirmed)) == (403, "auth.second_factor_required")


async def test_a_confirmed_totp_or_a_passkey_opens_the_admin(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    with_totp, with_passkey = await _user(db, "editor"), await _user(db, "editor")
    await _totp(db, with_totp)
    await _passkey(db, with_passkey)
    for person in (with_totp, with_passkey):
        response = await client.get("/api/demo/admin/ping", headers=_as(await _token(db, person)))
        assert response.status_code == 200


async def test_past_the_gate_an_admin_route_still_needs_its_permission(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    editor, owner = await _user(db, "editor"), await _user(db, "owner")
    await _totp(db, editor)
    await _totp(db, owner)
    refused = await client.get("/api/demo/admin/stats", headers=_as(await _token(db, editor)))
    assert (refused.status_code, _code(refused)) == (403, "kernel.forbidden")
    allowed = await client.get("/api/demo/admin/stats", headers=_as(await _token(db, owner)))
    assert allowed.status_code == 200


async def test_the_gate_is_the_admin_segment_after_the_module_not_any_path_text(
    db: AsyncSession, client: httpx.AsyncClient
) -> None:
    member = await _user(db)
    response = await client.get("/api/demo/posts/admin", headers=_as(await _token(db, member)))
    assert response.status_code == 200
    assert response.json() == {"slug": "admin"}


async def test_the_gate_holds_when_the_site_is_served_under_a_root_path(
    db: AsyncSession, demo_app: FastAPI
) -> None:
    """Behind a proxy that strips a prefix (`--root-path /site`), the path a
    request carries starts with the prefix; the gate reads the route's path."""
    member = await _user(db)
    token = await _token(db, member)
    transport = httpx.ASGITransport(app=demo_app, root_path="/site")
    async with (
        demo_app.router.lifespan_context(demo_app),
        httpx.AsyncClient(transport=transport, base_url=SITE) as http,
    ):
        response = await http.get("/site/api/demo/admin/ping", headers=_as(token))
        assert (response.status_code, _code(response)) == (403, "kernel.forbidden")
        mine = await http.get("/site/api/demo/me", headers=_as(token))
        assert mine.status_code == 200

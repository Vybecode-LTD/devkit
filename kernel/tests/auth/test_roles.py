"""People and roles in the admin (`kernel.auth.roles`; K4.7): what the
contract suite can't see from outside. Two owners stepping down at once, a
role deleted while a grant of it is being written, `member` being no rank, and
the permissions list a site's modules add to.

The races hold the moment that matters open: a request paused after its check,
or a grant written but not committed, and wait until the other side is
blocked on a lock (`pg_stat_activity`), so each can only pass if the lock is
there. Each was checked with the lock taken out, and failed."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.app import _permissions_listed, create_app
from kernel.auth import roles
from kernel.auth.accounts import normal_email
from kernel.auth.models import Role, RolePermission, Totp, User, UserRole
from kernel.email import CapturingMailer

from ..conftest import SITE, Client, Draining, Heard, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
USERS = "/api/auth/admin/users"
ROLES = "/api/auth/admin/roles"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}


@pytest.fixture(autouse=True)
def _clock() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


@dataclass
class Site:
    app: FastAPI

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made

    def browser(self) -> httpx.AsyncClient:
        transport = Draining(app=self.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=SITE, headers=_SAME_ORIGIN)


@dataclass
class Person:
    id: uuid.UUID
    email: str
    totp_secret: str


@pytest_asyncio.fixture
async def site(migrated_url: str) -> AsyncIterator[Site]:
    app = create_app(config=make_config(database_url=migrated_url), mailer=CapturingMailer())
    async with Client(app):
        yield Site(app)


async def _person(site: Site, *role_ids: str) -> Person:
    email = f"Ro.{uuid.uuid4().hex[:10]}@Site.test"
    secret = pyotp.random_base32()
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            password_hash=await site.app.state.passwords.hash(PASSWORD),
            email_verified_at=clock.now(),
        )
        db.add(user)
        await db.flush()
        for role in role_ids or ("member",):
            db.add(UserRole(user_id=user.id, role_id=role))
        db.add(Totp(user_id=user.id, secret_sealed=crypto.seal(secret), confirmed_at=clock.now()))
        await db.commit()
        return Person(user.id, email, secret)


async def _role(site: Site, *permissions: str) -> str:
    role_id = f"r-{uuid.uuid4().hex[:10]}"
    async with site.db() as db:
        db.add(Role(id=role_id, name="Helper"))
        await db.flush()
        for key in permissions:
            db.add(RolePermission(role_id=role_id, permission=key))
        await db.commit()
    return role_id


async def _signed_in(site: Site, person: Person) -> httpx.AsyncClient:
    browser = site.browser()
    body = (
        await browser.post("/api/auth/sign-in", json={"email": person.email, "password": PASSWORD})
    ).json()
    body = (
        await browser.post(
            "/api/auth/sign-in/second-factor",
            json={"challenge": body["challenge"], "totp": pyotp.TOTP(person.totp_secret).now()},
        )
    ).json()
    assert body["status"] == "signed_in", body
    return browser


async def _until_one_waits_on_a_lock(site: Site, *, seconds: float = 5.0) -> bool:
    """True once a query of this database waits on a lock; False if none has
    by the deadline (a mutant without the lock never waits)."""
    deadline = time.monotonic() + seconds
    async with site.db() as db:
        while time.monotonic() < deadline:
            waiting = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            await db.rollback()
            if waiting:
                return True
            await asyncio.sleep(0.02)
    return False


def _code(response: httpx.Response) -> tuple[int, str | None]:
    return response.status_code, response.json().get("code") if response.content else None


async def test_two_owners_stepping_down_at_once_leave_one(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each removes `owner` from themself, so their account locks never meet:
    only `owner`'s role row, locked for update, makes the second count after
    the first."""
    a, b = await _person(site, "owner"), await _person(site, "owner")
    async with site.db() as db:  # only these two own the site, for this test
        others = list(
            await db.scalars(
                delete(UserRole)
                .where(UserRole.role_id == "owner", UserRole.user_id.not_in([a.id, b.id]))
                .returning(UserRole.user_id)
            )
        )
        await db.commit()
    try:
        first_side, second_side = await _signed_in(site, a), await _signed_in(site, b)
        counted, go = asyncio.Event(), asyncio.Event()
        original = roles._others_active_owners

        async def paused(db: AsyncSession, user_id: uuid.UUID) -> int:
            found = await original(db, user_id)
            if not counted.is_set():
                counted.set()
                await go.wait()
            return found

        monkeypatch.setattr(roles, "_others_active_owners", paused)
        first = asyncio.create_task(
            first_side.put(f"{USERS}/{a.id}/roles", json={"roles": ["admin"]})
        )
        await asyncio.wait_for(counted.wait(), 10)
        second = asyncio.create_task(
            second_side.put(f"{USERS}/{b.id}/roles", json={"roles": ["admin"]})
        )
        await _until_one_waits_on_a_lock(site)
        go.set()
        answers = [await first, await second]
        assert [_code(r) for r in answers] == [(200, None), (409, "auth.last_owner")]
        async with site.db() as db:
            owners = set(
                await db.scalars(select(UserRole.user_id).where(UserRole.role_id == "owner"))
            )
        assert owners == {b.id}
    finally:
        async with site.db() as db:
            await db.execute(
                delete(UserRole).where(UserRole.role_id == "owner", UserRole.user_id.in_(others))
            )
            if others:
                await db.execute(
                    insert(UserRole), [{"user_id": u, "role_id": "owner"} for u in others]
                )
            await db.commit()


async def test_a_role_isnt_deleted_from_under_a_grant_being_written(site: Site) -> None:
    """The delete waits for the grant's transaction, then counts its holder.
    Without its lock it would count none, wait on the grant's key-share lock
    only to delete the role, and take the new grant with it."""
    owner = await _person(site, "owner")
    role = await _role(site)
    holder = await _person(site)
    browser = await _signed_in(site, owner)
    async with site.db() as grant:
        grant.add(UserRole(user_id=holder.id, role_id=role))
        await grant.flush()
        deleting = asyncio.create_task(browser.delete(f"{ROLES}/{role}"))
        assert await _until_one_waits_on_a_lock(site)
        await grant.commit()
    assert _code(await deleting) == (409, "auth.role_in_use")
    async with site.db() as db:
        assert await db.get(UserRole, (holder.id, role)) is not None


async def test_member_is_no_rank(site: Site) -> None:
    """A module's permission for members never stops staff granting or
    removing `member` (as with suspensions, `kernel.moderation`)."""
    granter = await _person(site, await _role(site, "auth.user.manage", "auth.role.assign"))
    person = await _person(site, "editor")
    browser = await _signed_in(site, granter)
    async with site.db() as db:  # what a module might give every member
        db.add(RolePermission(role_id="member", permission="auth.audit.read"))
        await db.commit()
    try:
        granted = await browser.put(
            f"{USERS}/{person.id}/roles", json={"roles": ["editor", "member"]}
        )
        assert granted.status_code == 200, granted.text
        removed = await browser.put(f"{USERS}/{person.id}/roles", json={"roles": ["editor"]})
        assert removed.status_code == 200, removed.text
        # The control: any other role carrying it is still judged.
        reader = await _role(site, "auth.audit.read")
        refused = await browser.put(
            f"{USERS}/{person.id}/roles", json={"roles": ["editor", reader]}
        )
        assert _code(refused) == (403, "auth.role_not_yours")
    finally:
        async with site.db() as db:
            await db.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == "member",
                    RolePermission.permission == "auth.audit.read",
                )
            )
            await db.commit()


async def test_a_grant_is_heard_with_the_roles_it_added_and_removed(
    site: Site, heard: Heard
) -> None:
    """`auth.user.role_changed` (SPEC 11), emitted in the grant's transaction
    with what changed; a grant that changes nothing is heard by no one."""
    owner = await _person(site, "owner")
    person = await _person(site, "editor")
    browser = await _signed_in(site, owner)
    granted = await browser.put(f"{USERS}/{person.id}/roles", json={"roles": ["admin", "member"]})
    assert granted.status_code == 200, granted.text
    same = await browser.put(f"{USERS}/{person.id}/roles", json={"roles": ["member", "admin"]})
    assert same.status_code == 200, same.text
    assert await heard.drain() == [
        (
            "auth.user.role_changed",
            {"user_id": str(person.id), "added": ["admin", "member"], "removed": ["editor"]},
        )
    ]


def test_the_permissions_list_is_the_kernels_then_each_modules() -> None:
    def module(ident: str, *permissions: object) -> SimpleNamespace:
        return SimpleNamespace(id=ident, manifest=SimpleNamespace(raw={"permissions": permissions}))

    listed = _permissions_listed(
        [
            module(
                "blog",
                {"key": "blog.post.edit", "description": "Edit posts", "default_roles": []},
                {"key": "blog.post.publish"},
                "not a permission",
            ),
            module("shop", {"key": "blog.post.edit", "description": "Again"}),
        ]  # type: ignore[list-item]
    )
    kernels = [item for item in listed if item["owner"] == "kernel"]
    assert listed[: len(kernels)] == tuple(kernels)
    assert {item["key"] for item in kernels} >= {"auth.role.manage", "kernel.jobs.manage"}
    assert listed[len(kernels) :] == (
        {"key": "blog.post.edit", "description": "Edit posts", "owner": "blog"},
        {"key": "blog.post.publish", "description": "", "owner": "blog"},
    )

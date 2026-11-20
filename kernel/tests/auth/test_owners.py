"""The site's first owner, made from the server (`kernel.auth.owners`; SPEC.md
14.1; the K5 contract §2 and §8 answer 2; decision 0051).

`create_owner(db, email)` gives the address's account the owner role (making
the account when there's none) and answers a one-time link token to set its
password, the reset's. Whoever held the account is shut out until the link is
used. With an owner already there, only an owner's own address gets a new
link (the owner, 2026-11-20); any other is refused.

Each test has a database of its own: "no owner yet" can't be seen on the
shared one, where other tests make owners.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from harness.migrations import upgrade
from kernel import clock
from kernel.app import create_app
from kernel.auth import owners
from kernel.auth.accounts import normal_email
from kernel.auth.models import AuditEvent, Session, Token, User, UserRole
from kernel.email import CapturingMailer
from kernel.models import Job

from ..conftest import SITE, Client, make_config

PASSWORD = "quiet orbit lantern 4471 marsh"
NEW = "amber walrus cello 5528 dune"
_SAME_ORIGIN = {"Origin": SITE, "Sec-Fetch-Site": "same-origin"}


@dataclass
class Site:
    app: FastAPI
    http: httpx.AsyncClient
    mail: CapturingMailer

    def db(self) -> AsyncSession:
        made: AsyncSession = self.app.state.database.sessions()
        return made


async def _no_breaches(_prefix: str) -> str:
    return ""


@pytest_asyncio.fixture
async def site(empty_database_url: str) -> AsyncIterator[Site]:
    """A site of its own: a database with every migration and no account."""
    await asyncio.to_thread(upgrade, empty_database_url)
    mail = CapturingMailer()
    app = create_app(
        config=make_config(database_url=empty_database_url),
        mailer=mail,
        breach_lookup=_no_breaches,
    )
    async with Client(app) as http:
        http.headers.update(_SAME_ORIGIN)
        yield Site(app, http, mail)


async def _create(site: Site, email: str) -> str:
    async with site.db() as db:
        return await owners.create_owner(db, email)


async def _account(site: Site, email: str) -> User | None:
    async with site.db() as db:
        found: User | None = await db.scalar(
            select(User).where(User.email_normal == normal_email(email))
        )
        return found


async def _roles(site: Site, user_id: uuid.UUID) -> set[str]:
    async with site.db() as db:
        rows = await db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id))
        return set(rows)


async def _audit(site: Site) -> list[tuple[str, str]]:
    async with site.db() as db:
        rows = await db.execute(
            select(AuditEvent.action, AuditEvent.result)
            .where(AuditEvent.action == owners.ACTION)
            .order_by(AuditEvent.id)
        )
        return [(row.action, row.result) for row in rows]


async def _reset(site: Site, token: str, password: str = NEW) -> httpx.Response:
    return await site.http.post(
        "/api/auth/password/reset", json={"token": token, "password": password}
    )


async def _member(site: Site, email: str, *, verified: bool, status: str = "active") -> User:
    """An account someone made for `email` before the owner did, signed in."""
    async with site.db() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            password_hash=await site.app.state.passwords.hash(PASSWORD),
            status=status,
            email_verified_at=clock.now() if verified else None,
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id="member"))
        await db.commit()
        return user


async def test_a_site_with_no_owner_gets_one_and_a_link_to_set_its_password(site: Site) -> None:
    token = await _create(site, "  Owner@Site.test ")
    user = await _account(site, "owner@site.test")
    assert user is not None
    assert user.email == "Owner@Site.test"  # as typed, trimmed
    assert user.password_hash is None  # nobody signs in before the link is used
    assert user.email_verified_at is None
    assert await _roles(site, user.id) == {"owner", "member"}
    assert await _audit(site) == [(owners.ACTION, "made")]
    async with site.db() as db:  # the link is the caller's to show, not mailed
        queued = await db.scalar(
            select(func.count()).select_from(Job).where(Job.name == "kernel.send_mail")
        )
    assert queued == 0

    answer = await _reset(site, token)
    assert answer.status_code == 200, answer.text
    after = await _account(site, "owner@site.test")
    assert after is not None
    assert after.password_hash is not None
    assert after.email_verified_at is not None  # the link proved who holds it
    assert (await _reset(site, token, "another fine password 8812")).status_code == 400


async def test_an_account_already_there_is_made_the_owner_and_shut_out_until_its_link_is_used(
    site: Site,
) -> None:
    """Someone who signed up with the owner's address first holds nothing after."""
    early = await _member(site, "owner@site.test", verified=False)
    signed = await site.http.post(
        "/api/auth/sign-in", json={"email": "owner@site.test", "password": PASSWORD}
    )
    assert signed.status_code == 200, signed.text
    assert (await site.http.get("/api/auth/session")).status_code == 200  # the control

    token = await _create(site, "owner@site.test")
    assert await _roles(site, early.id) == {"owner", "member"}
    assert (await site.http.get("/api/auth/session")).status_code == 401
    async with site.db() as db:
        assert await db.scalar(select(Session).where(Session.user_id == early.id)) is None
    again = await site.http.post(
        "/api/auth/sign-in", json={"email": "owner@site.test", "password": PASSWORD}
    )
    assert again.status_code == 401  # the old password is gone
    assert await _audit(site) == [(owners.ACTION, "granted")]
    assert (await _reset(site, token)).status_code == 200


async def test_with_an_owner_only_an_owners_own_address_gets_a_new_link(site: Site) -> None:
    """The owner's answer, 2026-11-20: recovery from the server for an owner,
    and every other address refused; owners are then granted in Admin, People."""
    first = await _create(site, "owner@site.test")
    stranger = await _member(site, "lee@site.test", verified=True)
    with pytest.raises(owners.OwnerRefused, match="has an owner already"):
        await _create(site, "lee@site.test")
    with pytest.raises(owners.OwnerRefused, match="has an owner already"):
        await _create(site, "nobody@site.test")
    assert await _roles(site, stranger.id) == {"member"}
    assert await _account(site, "nobody@site.test") is None

    second = await _create(site, "OWNER@site.test")
    assert second != first
    assert (await _reset(site, first)).status_code == 400  # a new link voids the last
    assert (await _reset(site, second)).status_code == 200
    assert await _audit(site) == [
        (owners.ACTION, "made"),
        (owners.ACTION, "refused"),
        (owners.ACTION, "refused"),
        (owners.ACTION, "renewed"),
    ]


async def test_a_site_whose_owners_are_all_suspended_may_be_given_one(site: Site) -> None:
    await _create(site, "owner@site.test")
    async with site.db() as db:
        await db.execute(
            text("UPDATE auth_user SET status = 'suspended' WHERE email_normal = 'owner@site.test'")
        )
        await db.commit()
    token = await _create(site, "next@site.test")
    assert (await _reset(site, token)).status_code == 200


async def test_an_address_that_isnt_one_is_refused(site: Site) -> None:
    for written in ("", "owner", "owner@", "two@site.test other@site.test"):
        with pytest.raises(owners.OwnerRefused, match="isn't an email address"):
            await _create(site, written)
    async with site.db() as db:
        assert await db.scalar(select(User.id)) is None


async def test_a_suspended_account_isnt_made_the_owner(site: Site) -> None:
    held = await _member(site, "owner@site.test", verified=True, status="suspended")
    with pytest.raises(owners.OwnerRefused, match="suspended"):
        await _create(site, "owner@site.test")
    assert await _roles(site, held.id) == {"member"}
    async with site.db() as db:
        assert await db.scalar(select(Token.id).where(Token.user_id == held.id)) is None


async def test_two_runs_wait_for_each_other_on_the_owner_role(site: Site) -> None:
    """Two at once on a site with no owner would each see none: the second waits
    on `owner`'s row until the first commits, then finds an owner. The holder
    takes it FOR SHARE, which the role's own lock waits on but granting the
    role (a foreign key's KEY SHARE) doesn't, so only that lock can stop it."""
    async with site.db() as holding:
        await holding.execute(text("SELECT id FROM auth_role WHERE id = 'owner' FOR SHARE"))
        async with site.db() as db:
            await db.execute(text("SET lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError, match="lock"):
                await owners.create_owner(db, "owner@site.test")
        await holding.rollback()
    assert await _account(site, "owner@site.test") is None


async def test_the_account_is_locked_before_the_owner_role(site: Site) -> None:
    """The admin's role changes lock the account, then `owner`'s row (roles.py):
    a run locks them in the same order, so the two can't deadlock (Codex on #95).
    While another holds the account, a run waits holding nothing of `owner`'s."""
    held = await _member(site, "owner@site.test", verified=True)
    async with site.db() as holding:
        await holding.execute(
            text("SELECT id FROM auth_user WHERE id = :id FOR UPDATE"), {"id": held.id}
        )
        run = asyncio.create_task(_create(site, "owner@site.test"))
        await asyncio.sleep(0.5)  # long enough to reach the account's lock
        assert not run.done()
        async with site.db() as probe:
            await probe.execute(
                text("SELECT id FROM auth_role WHERE id = 'owner' FOR UPDATE NOWAIT")
            )
            await probe.rollback()
        await holding.rollback()
    await run
    assert await _roles(site, held.id) == {"owner", "member"}

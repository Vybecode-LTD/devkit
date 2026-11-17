"""`kernel.remove_unverified`: accounts never verified are removed after 7 days
(SPEC.md 14.7; decision 0035). Staff, verified, suspended and departing
accounts never are, and an account a request holds is left for the next run."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from kernel import clock, jobs
from kernel.auth import unverified
from kernel.auth.accounts import normal_email
from kernel.auth.models import AuditEvent, User, UserRole
from kernel.db import Database
from kernel.email import LogMailer


@pytest.fixture(autouse=True)
def _real_time() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


@pytest_asyncio.fixture(loop_scope="session")
async def database(migrated_url: str) -> AsyncIterator[Database]:
    made = Database(migrated_url, pool_size=3, max_overflow=3)
    yield made
    await made.dispose()


async def _account(
    database: Database,
    *,
    days_old: float,
    verified: bool = False,
    roles: tuple[str, ...] = ("member",),
    status: str = "active",
) -> uuid.UUID:
    email = f"Kim.{uuid.uuid4().hex[:10]}@Site.test"
    async with database.sessions() as db:
        user = User(
            email=email,
            email_normal=normal_email(email),
            status=status,
            email_verified_at=clock.now() if verified else None,
            created_at=clock.now() - timedelta(days=days_old),
        )
        db.add(user)
        await db.flush()
        for role in roles:
            db.add(UserRole(user_id=user.id, role_id=role))
        await db.commit()
        return user.id


async def _exists(database: Database, user_id: uuid.UUID) -> bool:
    async with database.sessions() as db:
        return await db.get(User, user_id) is not None


async def _sweep(database: Database) -> None:
    context = jobs.Context(uuid.uuid4(), unverified.REMOVE.name, 1, database, LogMailer())
    await unverified.REMOVE.run(context, {})


def test_it_runs_hourly_as_a_kernel_job() -> None:
    assert unverified.REMOVE.name == "kernel.remove_unverified"
    assert unverified.REMOVE.schedule is not None
    assert unverified.REMOVE.schedule.line == "17 * * * *"


async def test_an_account_unverified_for_7_days_is_removed_and_audited(database: Database) -> None:
    old = await _account(database, days_old=7, verified=False)
    clock.advance(60)  # 7 days and a minute
    await _sweep(database)
    assert not await _exists(database, old)
    async with database.sessions() as db:
        roles = await db.scalar(
            select(func.count()).select_from(UserRole).where(UserRole.user_id == old)
        )
        [row] = (await db.scalars(select(AuditEvent).where(AuditEvent.subject_id == old))).all()
    assert roles == 0
    assert (row.action, row.result, row.actor_id, row.ip) == (
        unverified.ACTION,
        "success",
        None,
        None,
    )


async def test_an_account_younger_than_7_days_stays(database: Database) -> None:
    young = await _account(database, days_old=6.9)
    await _sweep(database)
    assert await _exists(database, young)


@pytest.mark.parametrize(
    "kind",
    [
        {"verified": True},
        {"roles": ("member", "editor")},
        {"roles": ("owner",)},
        {"roles": ()},  # no role at all is still an unverified member's account
        {"status": "suspended"},
        {"status": "deleting"},
    ],
    ids=["verified", "editor", "owner", "no-role", "suspended", "deleting"],
)
async def test_which_old_accounts_stay(database: Database, kind: dict[str, object]) -> None:
    account = await _account(database, days_old=30, **kind)  # type: ignore[arg-type]
    await _sweep(database)
    stays = kind != {"roles": ()}
    assert await _exists(database, account) is stays


async def test_an_account_a_request_holds_is_left_for_the_next_run(database: Database) -> None:
    held = await _account(database, days_old=8)
    async with database.sessions() as holder:  # as a verification holds it (accounts.lock)
        await holder.execute(select(User.id).where(User.id == held).with_for_update())
        await asyncio.wait_for(_sweep(database), timeout=5)  # skipped, not waited on
        assert await _exists(database, held)
        await holder.rollback()
    await _sweep(database)
    assert not await _exists(database, held)


async def test_every_batch_is_swept(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(unverified, "BATCH", 2)
    accounts = [await _account(database, days_old=10) for _ in range(5)]
    await _sweep(database)
    for account in accounts:
        assert not await _exists(database, account)

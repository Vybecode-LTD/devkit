"""GET /api/kernel/admin/attention: the dashboard's "Needs you" list (K4
contract §2, addition 9; SPEC 8, the owner's lens).

Each item says what's wrong, why it matters and what fixes it, and reaches
only the people who can act on it: the site's description and card image
those who can change the site's settings, the failed jobs those who can also
retry them (`kernel.jobs.manage`). Written before the route, seen failing.

The run's database is shared, so a test that needs no failed jobs clears
them first, and each one that saves the site's identity puts it back.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, server_copy
from kernel.auth import sessions
from kernel.auth.models import Role, RolePermission, Totp, User, UserRole
from kernel.models import Job
from kernel.server_copy import SiteSettings
from kernel.settings import settings

from .conftest import AppFactory, Client

ROUTE = "/api/kernel/admin/attention"
SITE_FIXED = {"description": "A site for testing.", "card_image": "/card.png"}


async def _user(db: AsyncSession, *roles: str, second_factor: bool = True) -> User:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@site.test"
    user = User(id=user_id, email=email, email_normal=email, session_epoch=0, role_version=0)
    db.add(user)
    await db.flush()
    for role in roles or ("member",):
        db.add(UserRole(user_id=user_id, role_id=role))
    if second_factor:
        db.add(Totp(user_id=user_id, secret_sealed="sealed", confirmed_at=clock.now()))
    await db.commit()
    return user


async def _role(db: AsyncSession, *permissions: str) -> str:
    """A site's own role holding only `permissions`."""
    role_id = f"test-{uuid.uuid4().hex[:10]}"
    db.add(Role(id=role_id, name=role_id, builtin=False))
    await db.flush()
    for permission in permissions:
        db.add(RolePermission(role_id=role_id, permission=permission))
    await db.commit()
    return role_id


async def _as(db: AsyncSession, user: User) -> dict[str, str]:
    token, _ = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    return {"cookie": f"{sessions.SESSION_COOKIE}={token}"}


async def _save_site(db: AsyncSession, values: dict[str, Any]) -> None:
    form = await settings.form(db, server_copy.SECTION)
    await settings.save(db, server_copy.SECTION, values, version=form["version"])


@pytest_asyncio.fixture
async def site(db: AsyncSession, app_factory: AppFactory) -> AsyncIterator[None]:
    """The site's identity back to its defaults after the test."""
    app_factory([])  # registers the section
    yield
    await _save_site(db, SiteSettings().model_dump(mode="json"))


async def _no_failed_jobs(db: AsyncSession) -> None:
    await db.execute(delete(Job).where(Job.state == "dead"))
    await db.commit()


async def _failed_job(db: AsyncSession) -> None:
    now = clock.now()
    db.add(
        Job(
            name=f"test.failed_{uuid.uuid4().hex[:6]}",
            module="kernel",
            state="dead",
            run_at=now,
            tries=8,
            last_error="ValueError",
            finished_at=now,
        )
    )
    await db.commit()


async def _dead(db: AsyncSession) -> int:
    return int(
        await db.scalar(select(func.count()).select_from(Job).where(Job.state == "dead")) or 0
    )


def _code(response: httpx.Response) -> str:
    assert response.headers["content-type"].startswith("application/problem+json")
    code: str = response.json()["code"]
    return code


def _keys(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["key"] for item in response.json()["items"]]


async def test_the_list_is_for_staff_with_a_second_factor(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    member = await _user(db)
    bare_admin = await _user(db, "admin", second_factor=False)
    async with Client(app_factory()) as client:
        response = await client.get(ROUTE)
        assert (response.status_code, _code(response)) == (401, "kernel.not_signed_in")
        response = await client.get(ROUTE, headers=await _as(db, member))
        assert (response.status_code, _code(response)) == (403, "kernel.forbidden")
        response = await client.get(ROUTE, headers=await _as(db, bare_admin))
        assert (response.status_code, _code(response)) == (403, "auth.second_factor_required")


async def test_an_admin_is_told_what_the_site_lacks_and_how_to_fix_it(
    db: AsyncSession, app_factory: AppFactory, site: None
) -> None:
    await _no_failed_jobs(db)
    admin = await _user(db, "admin")
    async with Client(app_factory()) as client:
        response = await client.get(ROUTE, headers=await _as(db, admin))
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(item["key"], item["tone"], item["action"]["to"]) for item in items] == [
        ("kernel.site.description_missing", "warning", "/admin/settings"),
        ("kernel.site.card_missing", "info", "/admin/settings"),
    ]
    for item in items:
        assert set(item) == {"key", "tone", "what", "why", "action"}
        assert item["what"].strip()
        assert item["why"].strip()
        assert set(item["action"]) == {"label", "to"}
        assert item["action"]["label"].strip()


async def test_each_item_leaves_once_it_s_fixed(
    db: AsyncSession, app_factory: AppFactory, site: None
) -> None:
    await _no_failed_jobs(db)
    admin = await _user(db, "admin")
    async with Client(app_factory()) as client:
        headers = await _as(db, admin)
        await _save_site(db, {"description": SITE_FIXED["description"]})
        assert _keys(await client.get(ROUTE, headers=headers)) == ["kernel.site.card_missing"]
        await _save_site(db, SITE_FIXED)
        assert _keys(await client.get(ROUTE, headers=headers)) == []


async def test_failed_jobs_come_first_with_their_count(
    db: AsyncSession, app_factory: AppFactory, site: None
) -> None:
    await _save_site(db, SITE_FIXED)
    await _no_failed_jobs(db)
    admin = await _user(db, "admin")
    async with Client(app_factory()) as client:
        headers = await _as(db, admin)
        await _failed_job(db)
        one = (await client.get(ROUTE, headers=headers)).json()["items"]
        await _failed_job(db)
        await _save_site(db, {"card_image": ""})  # a save keeps what it doesn't name
        two = (await client.get(ROUTE, headers=headers)).json()["items"]
    assert [(item["key"], item["tone"]) for item in one] == [("kernel.jobs.dead", "danger")]
    assert one[0]["action"]["to"] == "/admin/settings/system"
    assert "1" in one[0]["what"]
    assert "jobs" not in one[0]["what"]
    assert [item["key"] for item in two] == ["kernel.jobs.dead", "kernel.site.card_missing"]
    assert str(await _dead(db)) in two[0]["what"]


async def test_each_item_reaches_only_those_who_can_act_on_it(
    db: AsyncSession, app_factory: AppFactory, site: None
) -> None:
    await _no_failed_jobs(db)
    await _failed_job(db)
    editor = await _user(db, "editor")  # moderation only
    settings_only = await _user(db, await _role(db, "kernel.settings.manage"))
    jobs_only = await _user(db, await _role(db, "kernel.jobs.manage"))
    both = await _user(db, await _role(db, "kernel.settings.manage", "kernel.jobs.manage"))
    owner = await _user(db, "owner")
    everything = ["kernel.jobs.dead", "kernel.site.description_missing", "kernel.site.card_missing"]
    async with Client(app_factory()) as client:
        assert _keys(await client.get(ROUTE, headers=await _as(db, editor))) == []
        # Who can't open System can't retry a job from it.
        assert _keys(await client.get(ROUTE, headers=await _as(db, jobs_only))) == []
        assert (
            _keys(await client.get(ROUTE, headers=await _as(db, settings_only))) == everything[1:]
        )
        assert _keys(await client.get(ROUTE, headers=await _as(db, both))) == everything
        assert _keys(await client.get(ROUTE, headers=await _as(db, owner))) == everything


def test_the_jobs_permission_is_the_kernel_s_and_the_admin_s_by_default() -> None:
    import json
    from pathlib import Path

    from kernel.auth.permissions import KERNEL_PERMISSIONS

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "kernel.json").read_text(encoding="utf-8")
    )
    declared = {each["key"]: each for each in manifest["permissions"]}
    assert "kernel.jobs.manage" in KERNEL_PERMISSIONS
    assert declared["kernel.jobs.manage"]["default_roles"] == ["admin"]
    assert declared["kernel.jobs.manage"]["description"] == (
        "Retry and discard failed background jobs"
    )

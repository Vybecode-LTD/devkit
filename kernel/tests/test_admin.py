"""The admin's System, below what the contract suite reaches over HTTP
(K4 contract §2, addition 8, change 19).

The contract suite (`contract/test_settings_system_contract.py`) covers the
routes. These cover what it can't make: a failed job whose name nothing
declares any more (its module was removed), and a queued job of such a name,
which the worker never takes and so never reads as a stuck worker.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import admin, clock
from kernel.auth import sessions
from kernel.auth.models import Totp, User, UserRole
from kernel.models import Job

from .conftest import AppFactory, Client, make_config


async def _owner(db: AsyncSession) -> dict[str, str]:
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@site.test"
    user = User(id=user_id, email=email, email_normal=email, session_epoch=0, role_version=0)
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user_id, role_id="owner"))
    db.add(Totp(user_id=user_id, secret_sealed="sealed", confirmed_at=clock.now()))
    await db.commit()
    token, _ = await sessions.start(db, user, user_agent="pytest")
    await db.commit()
    return {"cookie": f"{sessions.SESSION_COOKIE}={token}"}


def _job(name: str, state: str, **fields: object) -> Job:
    now = clock.now()
    values: dict[str, object] = {
        "name": name,
        "module": name.partition(".")[0],
        "state": state,
        "run_at": now,
        "payload": "{}",
    }
    if state == "dead":
        values |= {"tries": 8, "last_error": "ValueError", "finished_at": now}
    return Job(**(values | fields))


@pytest.mark.parametrize(
    ("name", "sealed", "payload", "expected"),
    [
        ("kernel.send_mail", False, "{}", True),
        ("kernel.send_mail", True, None, False),  # wiped when it failed (decision 0035)
        ("gone.thing", False, "{}", False),  # nothing declares it
    ],
)
def test_a_dead_job_runs_again_only_with_a_handler_and_its_contents(
    name: str, sealed: bool, payload: str | None, expected: bool
) -> None:
    job = _job(name, "dead", sealed=sealed, payload=payload)
    assert admin.retryable(job, frozenset({"kernel.send_mail"})) is expected


async def test_a_dead_job_nothing_declares_can_only_be_discarded(
    db: AsyncSession, app_factory: AppFactory
) -> None:
    app = app_factory([])
    ghost = _job(f"gone{uuid.uuid4().hex[:6]}.thing", "dead")
    db.add(ghost)
    await db.commit()
    cookie = await _owner(db)
    try:
        async with Client(app) as client:
            listed = await client.get("/api/kernel/admin/jobs/dead", headers=cookie)
            assert listed.status_code == 200, listed.text
            item = next(item for item in listed.json()["items"] if item["id"] == str(ghost.id))
            assert item["retryable"] is False
            refused = await client.post(f"/api/kernel/admin/jobs/{ghost.id}/retry", headers=cookie)
            assert refused.status_code == 409, refused.text
            assert refused.json()["code"] == "kernel.job_not_retryable"
            gone = await client.delete(f"/api/kernel/admin/jobs/{ghost.id}", headers=cookie)
            assert gone.status_code == 204, gone.text
    finally:
        await db.execute(delete(Job).where(Job.id == ghost.id))
        await db.commit()


async def test_only_an_overdue_job_the_worker_would_take_reads_as_behind(
    db: AsyncSession,
) -> None:
    declared = frozenset({"kernel.send_mail", "blog.digest"})
    late = clock.now() - timedelta(minutes=3)
    made = [
        _job(f"gone{uuid.uuid4().hex[:6]}.thing", "queued", run_at=late),  # nothing declares it
        _job("blog.digest", "queued", run_at=late),  # blog is off
        _job("kernel.send_mail", "queued", run_at=clock.now() - timedelta(seconds=90)),
    ]
    db.add_all(made)
    await db.commit()
    try:
        counts = await admin.job_counts(db, declared, frozenset())
        assert counts["worker"] == "ok"
        assert counts["queued"] >= 3
        assert (await admin.job_counts(db, declared, frozenset({"blog"})))["worker"] == "behind"
    finally:
        await db.execute(delete(Job).where(Job.id.in_([job.id for job in made])))
        await db.commit()


def test_system_names_the_adapter_and_buckets_the_host_set() -> None:
    assert admin._email(make_config()) == "log"
    smtp = make_config(mail_from="hello@vibe.test", smtp_host="smtp.vibe.test")
    assert admin._email(smtp) == "smtp"
    # Set in part, mail stops the start outside DEBUG; with it on, mail goes to the log.
    assert admin._email(make_config(debug=True, smtp_host="smtp.vibe.test")) == "log"
    assert admin._storage(make_config()) == {"configured": False, "public": False}

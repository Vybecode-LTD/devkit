"""The jobs worker and scheduler against the test Postgres (contract k3-jobs,
decision 0035).

Each test's jobs belong to a module id of its own, and a worker claims only
the names it has handlers for, so tests sharing the run's database never run
each other's jobs. Races are made real: a row held by another transaction, a
handler held mid-run, a second worker on the same table, and, for the K3
gate, a worker process killed mid-job (memory note race-tests-that-really-race).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update

from kernel import clock, jobs
from kernel.app import create_app
from kernel.db import Database
from kernel.email import LogMailer
from kernel.models import Job as JobRow
from kernel.models import JobSchedule, ModuleState
from kernel.modules import InstalledModule, ModuleRegistry
from kernel.tests.conftest import Client, make_config, manifest, unique_id
from kernel.worker import (
    SCHEDULER_LOCK,
    Watchdog,
    Worker,
    create_worker,
    serve,
    stop_on_signals,
)

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _real_time() -> Iterator[None]:
    clock.reset()
    yield
    clock.reset()


@pytest_asyncio.fixture(loop_scope="session")
async def database(migrated_url: str) -> AsyncIterator[Database]:
    """A pool big enough for two workers, their renewals and a test's own
    sessions holding rows."""
    made = Database(migrated_url, pool_size=5, max_overflow=10)
    yield made
    await made.dispose()


Handler = Callable[[jobs.Context, dict[str, Any]], Awaitable[None]]


def _worker(
    database: Database, owner: str, *declared: jobs.Job, ttl: float = 0, **options: Any
) -> Worker:
    registry = ModuleRegistry([InstalledModule(manifest(owner))], [owner], ttl=ttl)
    return Worker(declared, registry=registry, database=database, mailer=LogMailer(), **options)


async def _enqueue(
    database: Database, name: str, payload: dict[str, Any] | None = None, **options: Any
) -> uuid.UUID:
    async with database.sessions() as db:
        job_id = await jobs.enqueue(db, name, payload, **options)
        await db.commit()
    assert job_id is not None
    return job_id


async def _row(database: Database, job_id: uuid.UUID) -> JobRow:
    async with database.sessions() as db:
        row = await db.get(JobRow, job_id)
        assert row is not None
        return row


async def _until(check: Callable[[], Awaitable[bool]], seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while not await check():
        assert time.monotonic() < deadline, "timed out waiting"
        await asyncio.sleep(0.02)


def _seen() -> tuple[list[tuple[int, dict[str, Any]]], Handler]:
    calls: list[tuple[int, dict[str, Any]]] = []

    async def handler(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        calls.append((ctx.try_number, payload))

    return calls, handler


# --- one try ---------------------------------------------------------------------------


async def test_a_due_job_runs_once_and_is_done(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send", {"post_id": 7})

    assert await worker.run_due() == 1
    assert calls == [(1, {"post_id": 7})]
    row = await _row(database, job_id)
    assert (row.state, row.tries, row.locked_until, row.last_error) == ("done", 1, None, None)
    assert row.finished_at is not None
    assert await worker.run_due() == 0


async def test_the_context_names_the_job_and_opens_sessions(database: Database) -> None:
    owner = unique_id()
    seen: list[tuple[uuid.UUID, str, int]] = []

    async def handler(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        async with ctx.sessions() as db:
            assert await db.scalar(text("SELECT 1")) == 1
        seen.append((ctx.job_id, ctx.name, ctx.try_number))

    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send")
    await worker.run_due()
    assert seen == [(job_id, f"{owner}.send", 1)]


async def test_a_job_with_no_payload_gets_an_empty_one(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    await _enqueue(database, f"{owner}.send")
    await worker.run_due()
    assert calls == [(1, {})]


async def test_a_future_job_waits_for_its_time(database: Database) -> None:
    owner = unique_id()
    _, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    await _enqueue(database, f"{owner}.send", run_at=clock.now() + timedelta(hours=1))
    assert await worker.run_due() == 0
    clock.advance(3601)
    assert await worker.run_due() == 1


# --- failures ----------------------------------------------------------------------------


async def test_a_failure_is_retried_after_backoff_and_keeps_only_the_error_s_type(
    database: Database,
) -> None:
    owner = unique_id()
    secret = "do-not-keep-" + uuid.uuid4().hex

    async def flaky(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        if ctx.try_number == 1:
            raise RuntimeError(secret)

    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(flaky))
    job_id = await _enqueue(database, f"{owner}.send")
    before = clock.now()
    assert await worker.run_due() == 1
    row = await _row(database, job_id)
    assert (row.state, row.tries, row.last_error) == ("queued", 1, "RuntimeError")
    assert 27 <= (row.run_at - before).total_seconds() <= 34
    assert row.locked_until is None
    assert await worker.run_due() == 0
    clock.advance(34)
    assert await worker.run_due() == 1
    row = await _row(database, job_id)
    assert (row.state, row.tries) == ("done", 2)


async def test_retry_after_sets_the_wait(database: Database) -> None:
    owner = unique_id()

    async def later(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        raise jobs.Retry(after=600)

    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(later))
    job_id = await _enqueue(database, f"{owner}.send")
    before = clock.now()
    await worker.run_due()
    row = await _row(database, job_id)
    assert (row.state, row.last_error) == ("queued", "Retry")
    assert 599 <= (row.run_at - before).total_seconds() <= 605


async def test_abandon_is_dead_at_once(database: Database) -> None:
    owner = unique_id()

    async def refused(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        raise jobs.Abandon("the address was refused")

    worker = _worker(database, owner, jobs.handler(f"{owner}.send", tries=5)(refused))
    job_id = await _enqueue(database, f"{owner}.send")
    await worker.run_due()
    row = await _row(database, job_id)
    assert (row.state, row.tries, row.last_error) == ("dead", 1, "Abandon")
    assert row.finished_at is not None


async def test_a_job_is_dead_once_its_tries_are_used(database: Database) -> None:
    owner = unique_id()

    async def broken(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        raise ValueError("no")

    worker = _worker(database, owner, jobs.handler(f"{owner}.send", tries=2)(broken))
    job_id = await _enqueue(database, f"{owner}.send")
    await worker.run_due()
    assert (await _row(database, job_id)).state == "queued"
    clock.advance(40)
    await worker.run_due()
    row = await _row(database, job_id)
    assert (row.state, row.tries, row.last_error) == ("dead", 2, "ValueError")


async def test_the_timeout_cuts_a_try_short(database: Database) -> None:
    owner = unique_id()

    async def slow(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        await asyncio.sleep(30)

    worker = _worker(database, owner, jobs.handler(f"{owner}.send", timeout=0.2)(slow))
    job_id = await _enqueue(database, f"{owner}.send")
    started = time.monotonic()
    await worker.run_due()
    assert time.monotonic() - started < 5
    row = await _row(database, job_id)
    assert (row.state, row.last_error) == ("queued", "TimeoutError")


async def test_a_sealed_payload_reaches_its_handler_and_is_wiped_when_done(
    database: Database,
) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send", {"code": "481516"}, sealed=True)
    await worker.run_due()
    assert calls == [(1, {"code": "481516"})]
    assert (await _row(database, job_id)).payload is None


async def test_a_sealed_payload_is_wiped_when_dead(database: Database) -> None:
    owner = unique_id()

    async def refused(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        raise jobs.Abandon("no")

    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(refused))
    job_id = await _enqueue(database, f"{owner}.send", {"code": "481516"}, sealed=True)
    await worker.run_due()
    row = await _row(database, job_id)
    assert (row.state, row.payload) == ("dead", None)


async def test_a_plain_payload_stays_when_done(database: Database) -> None:
    owner = unique_id()
    _, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send", {"post_id": 7})
    await worker.run_due()
    assert (await _row(database, job_id)).payload == '{"post_id":7}'


# --- what a worker claims ----------------------------------------------------------------


async def test_a_job_with_no_handler_here_waits(database: Database) -> None:
    owner = unique_id()
    _, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.newer")
    assert await worker.run_due() == 0
    assert (await _row(database, job_id)).state == "queued"


async def test_a_switched_off_module_s_job_waits_until_it_s_back_on(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    async with database.sessions() as db:
        db.add(ModuleState(module_id=owner, enabled=False))
        await db.commit()
    await _enqueue(database, f"{owner}.send")
    assert await worker.run_due() == 0
    async with database.sessions() as db:
        await db.execute(
            update(ModuleState).where(ModuleState.module_id == owner).values(enabled=True)
        )
        await db.commit()
    assert await worker.run_due() == 1
    assert len(calls) == 1


async def test_a_row_another_claim_holds_is_skipped_not_waited_on(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send")
    async with database.sessions() as holder:
        await holder.execute(select(JobRow.id).where(JobRow.id == job_id).with_for_update())
        # Without SKIP LOCKED the claim would wait here for the holder.
        assert await asyncio.wait_for(worker.run_due(wait=0), timeout=5) == 0
        await holder.rollback()
    assert await worker.run_due() == 1
    assert len(calls) == 1


async def test_a_running_job_s_live_lease_keeps_another_worker_off_it(database: Database) -> None:
    owner = unique_id()
    started, release = asyncio.Event(), asyncio.Event()
    runs: list[int] = []

    async def held(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        runs.append(ctx.try_number)
        started.set()
        await release.wait()

    job = jobs.handler(f"{owner}.send")(held)
    first, second = _worker(database, owner, job), _worker(database, owner, job)
    job_id = await _enqueue(database, f"{owner}.send")
    running = asyncio.create_task(first.run_due())
    await asyncio.wait_for(started.wait(), timeout=10)
    assert await second.run_due(wait=0) == 0
    release.set()
    assert await running == 1
    assert runs == [1]
    assert (await _row(database, job_id)).state == "done"


async def test_the_lease_is_renewed_while_a_long_job_runs(database: Database) -> None:
    owner = unique_id()
    runs: list[int] = []

    async def long(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        runs.append(ctx.try_number)
        await asyncio.sleep(2.0)

    job = jobs.handler(f"{owner}.send")(long)
    options = {"lease": 1.0, "renew_every": 0.2}
    first, second = _worker(database, owner, job, **options), _worker(
        database, owner, job, **options
    )
    job_id = await _enqueue(database, f"{owner}.send")
    running = asyncio.create_task(first.run_due())
    await asyncio.sleep(1.5)  # past the first lease: only a renewal keeps it
    assert await second.run_due(wait=0) == 0
    assert await running == 1
    assert runs == [1]
    row = await _row(database, job_id)
    assert (row.state, row.tries) == ("done", 1)


async def test_a_lapsed_lease_is_claimed_again_as_the_next_try(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send")
    async with database.sessions() as db:  # a worker died holding it
        await db.execute(
            update(JobRow)
            .where(JobRow.id == job_id)
            .values(state="running", tries=1, locked_until=clock.now() - timedelta(seconds=1))
        )
        await db.commit()
    assert await worker.run_due() == 1
    assert calls == [(2, {})]


async def test_a_lapsed_job_out_of_tries_is_dead_without_running(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send", tries=1)(handler))
    job_id = await _enqueue(database, f"{owner}.send")
    async with database.sessions() as db:
        await db.execute(
            update(JobRow)
            .where(JobRow.id == job_id)
            .values(state="running", tries=1, locked_until=clock.now() - timedelta(seconds=1))
        )
        await db.commit()
    await worker.run_due()
    assert calls == []
    row = await _row(database, job_id)
    assert (row.state, row.last_error) == ("dead", "WorkerLost")


async def test_a_superseded_try_s_late_outcome_is_dropped(database: Database) -> None:
    owner = unique_id()
    reclaimed = asyncio.Event()

    async def stale(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        if ctx.try_number == 1:
            await reclaimed.wait()
            raise RuntimeError("too late")

    job = jobs.handler(f"{owner}.send")(stale)
    first = _worker(database, owner, job, lease=0.3, renew_every=60)
    second = _worker(database, owner, job)
    job_id = await _enqueue(database, f"{owner}.send")
    running = asyncio.create_task(first.run_due())
    await _until(lambda: _state_is(database, job_id, "running"))
    await asyncio.sleep(0.5)  # the first lease lapses, unrenewed
    assert await second.run_due(wait=0) == 1
    reclaimed.set()
    await running
    row = await _row(database, job_id)
    assert (row.state, row.tries, row.last_error) == ("done", 2, None)


async def _state_is(database: Database, job_id: uuid.UUID, state: str) -> bool:
    return (await _row(database, job_id)).state == state


async def test_run_due_waits_for_a_job_another_worker_holds(database: Database) -> None:
    owner = unique_id()
    release = asyncio.Event()

    async def held(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        await release.wait()

    job = jobs.handler(f"{owner}.send")(held)
    first, second = _worker(database, owner, job), _worker(database, owner, job)
    job_id = await _enqueue(database, f"{owner}.send")
    running = asyncio.create_task(first.run_due())
    await _until(lambda: _state_is(database, job_id, "running"))
    waiting = asyncio.create_task(second.run_due(wait=10))
    await asyncio.sleep(0.3)
    assert not waiting.done()
    release.set()
    assert await waiting == 0
    assert await _state_is(database, job_id, "done")
    await running


# --- the K3 gate: a worker killed mid-job --------------------------------------------------


async def test_a_killed_worker_s_job_is_finished_by_the_next(
    database: Database, migrated_url: str, tmp_path: Path
) -> None:
    owner = unique_id()
    job_id = await _enqueue(database, f"{owner}.slow")
    marker = tmp_path / "started"
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    child = (
        subprocess.Popen(  # noqa: S603, ASYNC220 - our own child script, polled without blocking
            [
                sys.executable,
                str(REPO / "kernel" / "tests" / "jobs_child.py"),
                migrated_url,
                owner,
                str(marker),
            ],
            cwd=REPO,
            env=env,
        )
    )
    try:
        deadline = time.monotonic() + 60
        while not marker.exists():
            assert child.poll() is None, "the child worker ended early"
            assert time.monotonic() < deadline, "the child worker never started the job"
            await asyncio.sleep(0.05)
        calls, handler = _seen()
        survivor = _worker(database, owner, jobs.handler(f"{owner}.slow", tries=3)(handler))
        # The child holds a live lease: nobody else may take the job yet.
        assert await survivor.run_due(wait=0) == 0
        child.kill()
        child.wait(timeout=30)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=30)
    assert (await _row(database, job_id)).state == "running"
    clock.advance(jobs.LEASE + 1)  # the dead worker's lease lapses
    assert await survivor.run_due() == 1
    assert calls == [(2, {})]
    row = await _row(database, job_id)
    assert (row.state, row.tries) == ("done", 2)


# --- the loop ------------------------------------------------------------------------------


async def test_the_loop_runs_jobs_as_they_arrive(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler), poll=0.05)
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    try:
        await _enqueue(database, f"{owner}.send", {"n": 1})
        await _until(lambda: _async(len(calls) == 1))
        await _enqueue(database, f"{owner}.send", {"n": 2})
        await _until(lambda: _async(len(calls) == 2))
    finally:
        stop.set()
        await asyncio.wait_for(loop, timeout=10)


async def _async(value: bool) -> bool:
    return value


async def test_a_failing_job_doesn_t_stop_the_loop(database: Database) -> None:
    owner = unique_id()
    calls, good = _seen()

    async def bad(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        raise RuntimeError("no")

    worker = _worker(
        database,
        owner,
        jobs.handler(f"{owner}.bad")(bad),
        jobs.handler(f"{owner}.good")(good),
        poll=0.05,
    )
    await _enqueue(database, f"{owner}.bad")
    await _enqueue(database, f"{owner}.good")
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    try:
        await _until(lambda: _async(len(calls) == 1))
    finally:
        stop.set()
        await asyncio.wait_for(loop, timeout=10)


async def test_the_loop_runs_at_most_its_concurrency(database: Database) -> None:
    owner = unique_id()
    running, most, release = 0, 0, asyncio.Event()

    async def counted(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await release.wait()
        running -= 1

    worker = _worker(
        database, owner, jobs.handler(f"{owner}.send")(counted), concurrency=2, poll=0.05
    )
    for _ in range(4):
        await _enqueue(database, f"{owner}.send")
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    try:
        await _until(lambda: _async(running == 2))
        await asyncio.sleep(0.3)
        assert most == 2
        release.set()
        await _until(lambda: _async(running == 0))
    finally:
        release.set()
        stop.set()
        await asyncio.wait_for(loop, timeout=10)
    assert most == 2


async def test_stopping_lets_the_running_job_finish_and_claims_nothing_new(
    database: Database,
) -> None:
    owner = unique_id()
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def held(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        calls.append(str(payload.get("n")))
        started.set()
        await release.wait()

    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(held), poll=0.05)
    first = await _enqueue(database, f"{owner}.send", {"n": 1})
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    await asyncio.wait_for(started.wait(), timeout=10)
    stop.set()
    second = await _enqueue(database, f"{owner}.send", {"n": 2})
    await asyncio.sleep(0.2)
    release.set()
    await asyncio.wait_for(loop, timeout=10)
    assert calls == ["1"]
    assert await _state_is(database, first, "done")
    assert await _state_is(database, second, "queued")


async def test_a_job_still_running_past_the_drain_is_left_to_its_lease(database: Database) -> None:
    owner = unique_id()
    started = asyncio.Event()

    async def endless(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        started.set()
        await asyncio.sleep(3600)

    worker = _worker(
        database, owner, jobs.handler(f"{owner}.send", timeout=3600)(endless), poll=0.05, drain=0.1
    )
    job_id = await _enqueue(database, f"{owner}.send")
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    await asyncio.wait_for(started.wait(), timeout=10)
    stop.set()
    await asyncio.wait_for(loop, timeout=10)
    row = await _row(database, job_id)
    assert (row.state, row.tries, row.last_error) == ("running", 1, None)


async def test_the_web_process_runs_a_worker_when_asked(migrated_url: str) -> None:
    owner = unique_id()
    calls, handler = _seen()
    module = InstalledModule(manifest(owner), jobs=(jobs.handler(f"{owner}.send")(handler),))
    app = create_app(
        modules=[module],
        config=make_config(database_url=migrated_url, jobs_in_web=True, jobs_poll_seconds=0.1),
    )
    async with Client(app):
        async with app.state.database.sessions() as db:
            await jobs.enqueue(db, f"{owner}.send", {"n": 1})
            await db.commit()
        await _until(lambda: _async(len(calls) == 1))
    assert calls == [(1, {"n": 1})]


async def test_the_web_process_runs_none_when_not_asked(migrated_url: str) -> None:
    owner = unique_id()
    calls, handler = _seen()
    module = InstalledModule(manifest(owner), jobs=(jobs.handler(f"{owner}.send")(handler),))
    app = create_app(
        modules=[module],
        config=make_config(database_url=migrated_url, jobs_in_web=False, jobs_poll_seconds=0.1),
    )
    async with Client(app):
        async with app.state.database.sessions() as db:
            await jobs.enqueue(db, f"{owner}.send", {"n": 1})
            await db.commit()
        await asyncio.sleep(0.5)
        assert calls == []
        assert await app.state.worker.run_due() == 1


# --- the scheduler ---------------------------------------------------------------------------


async def _slots(database: Database, name: str) -> list[str | None]:
    async with database.sessions() as db:
        return list(
            (
                await db.scalars(select(JobRow.key).where(JobRow.name == name).order_by(JobRow.key))
            ).all()
        )


async def test_a_new_scheduled_job_starts_from_now(database: Database) -> None:
    owner = unique_id()
    job = jobs.scheduled("* * * * *", f"{owner}.tick")(_tick)
    worker = _worker(database, owner, job)
    assert await worker.tick() == 0
    async with database.sessions() as db:
        schedule = await db.get(JobSchedule, f"{owner}.tick")
    assert schedule is not None
    assert await _slots(database, f"{owner}.tick") == []


async def _tick(ctx: jobs.Context) -> None:
    return None


async def test_each_slot_is_enqueued_once_across_schedulers(database: Database) -> None:
    owner = unique_id()
    job = jobs.scheduled("* * * * *", f"{owner}.tick")(_tick)
    first, second = _worker(database, owner, job), _worker(database, owner, job)
    await first.tick()
    clock.advance(60)
    assert await first.tick() == 1
    assert await second.tick() == 0
    assert await first.tick() == 0
    slots = await _slots(database, f"{owner}.tick")
    assert len(slots) == 1
    assert await first.run_due() == 1


async def test_missed_slots_collapse_into_one_run(database: Database) -> None:
    owner = unique_id()
    job = jobs.scheduled("* * * * *", f"{owner}.tick")(_tick)
    worker = _worker(database, owner, job)
    await worker.tick()
    clock.advance(600)
    assert await worker.tick() == 1
    newest = clock.now().replace(second=0, microsecond=0)
    assert await _slots(database, f"{owner}.tick") == [newest.isoformat()]


async def test_a_slot_older_than_7_days_isn_t_caught_up(database: Database) -> None:
    owner = unique_id()
    nine_days_ago = clock.now() - timedelta(days=9)
    line = (
        f"{nine_days_ago.minute} {nine_days_ago.hour} {nine_days_ago.day} {nine_days_ago.month} *"
    )
    job = jobs.scheduled(line, f"{owner}.yearly")(_tick)
    worker = _worker(database, owner, job)
    async with database.sessions() as db:
        db.add(JobSchedule(name=f"{owner}.yearly", last_slot=clock.now() - timedelta(days=30)))
        await db.commit()
    assert await worker.tick() == 0


async def test_a_switched_off_module_s_slots_wait_and_one_runs_when_it_s_back(
    database: Database,
) -> None:
    owner = unique_id()
    job = jobs.scheduled("* * * * *", f"{owner}.tick")(_tick)
    worker = _worker(database, owner, job)
    await worker.tick()
    async with database.sessions() as db:
        db.add(ModuleState(module_id=owner, enabled=False))
        await db.commit()
    clock.advance(180)
    assert await worker.tick() == 0
    async with database.sessions() as db:
        await db.execute(
            update(ModuleState).where(ModuleState.module_id == owner).values(enabled=True)
        )
        await db.commit()
    assert await worker.tick() == 1


async def test_a_scheduler_already_ticking_elsewhere_is_left_to_it(database: Database) -> None:
    owner = unique_id()
    job = jobs.scheduled("* * * * *", f"{owner}.tick")(_tick)
    worker = _worker(database, owner, job)
    await worker.tick()
    clock.advance(60)
    async with database.sessions() as holder:
        await holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCHEDULER_LOCK})
        assert await asyncio.wait_for(worker.tick(), timeout=5) == 0
        await holder.rollback()
    assert await worker.tick() == 1


async def test_the_loop_ticks_the_scheduler(database: Database) -> None:
    owner = unique_id()
    ran: list[int] = []

    async def counted(ctx: jobs.Context) -> None:
        ran.append(ctx.try_number)

    job = jobs.scheduled("* * * * *", f"{owner}.tick")(counted)
    worker = _worker(database, owner, job, poll=0.05)
    await worker.tick()
    clock.advance(60)
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    try:
        await _until(lambda: _async(ran == [1]))
    finally:
        stop.set()
        await asyncio.wait_for(loop, timeout=10)


# --- pruning ----------------------------------------------------------------------------------


async def test_pruning_keeps_done_jobs_7_days_and_dead_ones_30(database: Database) -> None:
    owner = unique_id()
    now = clock.now()
    ages = {
        "done-8": ("done", 8),
        "done-6": ("done", 6),
        "dead-31": ("dead", 31),
        "dead-29": ("dead", 29),
        "queued-90": ("queued", 90),
    }
    async with database.sessions() as db:
        for key, (state, days) in ages.items():
            db.add(
                JobRow(
                    name=f"{owner}.send",
                    module=owner,
                    key=key,
                    state=state,
                    run_at=now,
                    finished_at=None if state == "queued" else now - timedelta(days=days),
                    created_at=now - timedelta(days=days),
                )
            )
        await db.commit()
    worker = _worker(database, owner, jobs.PRUNE)
    await _enqueue(database, jobs.PRUNE.name)
    await worker.run_due()
    async with database.sessions() as db:
        left = set((await db.scalars(select(JobRow.key).where(JobRow.module == owner))).all())
    assert left == {"done-6", "dead-29", "queued-90"}


# --- the standalone process's guards ------------------------------------------------------------


def test_the_watchdog_ends_a_worker_whose_loop_stops_answering() -> None:
    ended: list[int] = []
    with Watchdog(0.2, end=ended.append):
        time.sleep(0.6)
    assert ended == [124]


def test_the_watchdog_leaves_a_worker_that_beats() -> None:
    ended: list[int] = []
    with Watchdog(0.3, end=ended.append) as dog:
        for _ in range(8):
            dog.beat()
            time.sleep(0.1)
    time.sleep(0.4)  # stopped with the block: no late end
    assert ended == []


async def test_a_stop_signal_sets_the_stop_request() -> None:
    stop = asyncio.Event()
    with stop_on_signals(stop):
        signal.raise_signal(signal.SIGINT)
        await asyncio.wait_for(stop.wait(), timeout=5)
    assert stop.is_set()


@pytest.mark.skipif(
    os.name == "nt", reason="Windows can't send a child SIGTERM; CI runs it on Linux"
)
async def test_sigterm_drains_and_exits_0(
    migrated_url: str, database: Database, tmp_path: Path
) -> None:
    owner = unique_id()
    await _enqueue(database, f"{owner}.slow")
    marker = tmp_path / "started"
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    child = (
        subprocess.Popen(  # noqa: S603, ASYNC220 - our own child script, polled without blocking
            [
                sys.executable,
                str(REPO / "kernel" / "tests" / "jobs_child.py"),
                migrated_url,
                owner,
                str(marker),
                "serve",
            ],
            cwd=REPO,
            env=env,
        )
    )
    try:
        deadline = time.monotonic() + 60
        while not marker.exists():
            assert child.poll() is None
            assert time.monotonic() < deadline
            await asyncio.sleep(0.05)
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=60) == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=30)


# --- what goes wrong around a job ----------------------------------------------------------


async def _raw_job(database: Database, owner: str, **values: Any) -> uuid.UUID:
    job_id = uuid.uuid4()
    async with database.sessions() as db:
        db.add(JobRow(id=job_id, name=f"{owner}.send", module=owner, run_at=clock.now(), **values))
        await db.commit()
    return job_id


async def test_a_job_with_no_payload_stored_gets_an_empty_one(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    await _raw_job(database, owner, payload=None)
    await worker.run_due()
    assert calls == [(1, {})]


async def test_a_payload_that_can_t_be_read_is_dead_without_running(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _raw_job(database, owner, payload="not sealed by this site", sealed=True)
    await worker.run_due()
    assert calls == []
    row = await _row(database, job_id)
    assert row.state == "dead"
    assert row.last_error
    assert "sealed" not in row.last_error


async def test_an_outcome_that_can_t_be_written_is_left_to_the_lease(
    database: Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    owner = unique_id()
    _, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    job_id = await _enqueue(database, f"{owner}.send")

    async def database_gone(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("the database went away")

    monkeypatch.setattr(worker, "_finish", database_gone)
    with caplog.at_level(logging.WARNING, logger="kernel.worker"):
        assert await worker.run_due(wait=0) == 1
    assert "outcome wasn't recorded (ConnectionError)" in caplog.text
    assert (await _row(database, job_id)).state == "running"


async def test_a_failed_renewal_is_logged_and_the_job_runs_on(
    database: Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    owner = unique_id()

    async def slow(ctx: jobs.Context, payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.3)

    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(slow), renew_every=0.05)
    job_id = await _enqueue(database, f"{owner}.send")

    async def refused() -> None:
        raise ConnectionError("no")

    monkeypatch.setattr(worker, "_renew", refused)
    with caplog.at_level(logging.WARNING, logger="kernel.worker"):
        await worker.run_due()
    assert "Couldn't renew the running jobs' leases (ConnectionError)" in caplog.text
    assert await _state_is(database, job_id, "done")


async def test_an_idle_worker_s_renewal_touches_nothing(database: Database) -> None:
    worker = _worker(database, unique_id(), renew_every=0.02)
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(loop, timeout=10)


async def test_run_due_stops_at_its_limit(database: Database) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler))
    await _enqueue(database, f"{owner}.send", {"n": 1})
    await _enqueue(database, f"{owner}.send", {"n": 2})
    assert await worker.run_due(limit=1) == 1
    assert await worker.run_due() == 1
    assert len(calls) == 2


async def test_a_worker_with_no_jobs_claims_nothing(database: Database) -> None:
    worker = _worker(database, unique_id())
    assert await worker.run_due(wait=0) == 0
    assert await worker.tick() == 0


async def test_a_failing_tick_or_claim_doesn_t_stop_the_loop(
    database: Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    owner = unique_id()
    calls, handler = _seen()
    worker = _worker(database, owner, jobs.handler(f"{owner}.send")(handler), poll=0.05)
    real_claim = worker._claim
    failures = {"tick": 1, "claim": 1}

    async def tick() -> int:
        if failures["tick"]:
            failures["tick"] -= 1
            raise ConnectionError("no")
        return 0

    async def claim(limit: int) -> Any:
        if failures["claim"]:
            failures["claim"] -= 1
            raise ConnectionError("no")
        return await real_claim(limit)

    monkeypatch.setattr(worker, "tick", tick)
    monkeypatch.setattr(worker, "_claim", claim)
    await _enqueue(database, f"{owner}.send")
    stop = asyncio.Event()
    with caplog.at_level(logging.WARNING, logger="kernel.worker"):
        loop = asyncio.create_task(worker.run(stop))
        try:
            await _until(lambda: _async(len(calls) == 1))
        finally:
            stop.set()
            await asyncio.wait_for(loop, timeout=10)
    assert "The scheduler's tick failed (ConnectionError)" in caplog.text
    assert "Couldn't claim jobs (ConnectionError)" in caplog.text


async def test_pruning_works_through_every_batch(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = unique_id()
    old = clock.now() - timedelta(days=8)
    async with database.sessions() as db:
        for _ in range(5):
            db.add(
                JobRow(
                    name=f"{owner}.send", module=owner, state="done", run_at=old, finished_at=old
                )
            )
        await db.commit()
    monkeypatch.setattr(jobs, "_PRUNE_BATCH", 2)
    worker = _worker(database, owner, jobs.PRUNE)
    await _enqueue(database, jobs.PRUNE.name)
    await worker.run_due()
    async with database.sessions() as db:
        left = (await db.scalars(select(JobRow.id).where(JobRow.module == owner))).all()
    assert left == []


# --- a worker process of its own --------------------------------------------------------------


def test_serve_runs_until_a_stop_signal_and_returns_0() -> None:
    """No jobs, so nothing reaches the database (there is none here)."""
    registry = ModuleRegistry([], [], ttl=0)
    nowhere = Database("postgresql://devkit:devkit@127.0.0.1:1/none")
    worker = Worker([], registry=registry, database=nowhere, mailer=LogMailer(), poll=0.05)
    timer = threading.Timer(0.5, signal.raise_signal, (signal.SIGINT,))
    timer.start()
    try:
        assert serve(worker, watchdog=60) == 0
    finally:
        timer.cancel()


def test_create_worker_builds_what_create_app_would() -> None:
    owner = unique_id()
    _, handler = _seen()
    module = InstalledModule(manifest(owner), jobs=(jobs.handler(f"{owner}.send")(handler),))
    config = make_config(jobs_concurrency=7, jobs_poll_seconds=0.5)  # connects to nothing
    worker = create_worker(modules=[module], config=config)
    assert {
        f"{owner}.send",
        "kernel.send_mail",
        "kernel.prune_jobs",
        "kernel.remove_unverified",
    } == (worker.names)
    assert (worker.concurrency, worker.poll, worker.drain) == (7, 0.5, 20.0)


def test_create_worker_refuses_what_create_app_refuses() -> None:
    module = InstalledModule(manifest(unique_id()), jobs=(jobs.handler("other.send")(_seen()[1]),))
    with pytest.raises(RuntimeError, match="Refusing to start"):
        create_worker(modules=[module], config=make_config())


async def test_stop_signals_use_the_loop_s_handlers_where_it_has_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    added: list[int] = []
    removed: list[int] = []
    monkeypatch.setattr(loop, "add_signal_handler", lambda sig, *args: added.append(sig))
    monkeypatch.setattr(loop, "remove_signal_handler", lambda sig: removed.append(sig) is None)
    with stop_on_signals(asyncio.Event()):
        assert added == [signal.SIGTERM, signal.SIGINT]
    assert removed == [signal.SIGTERM, signal.SIGINT]


async def test_stop_signals_fall_back_to_the_signal_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()

    def unsupported(*args: Any) -> None:
        raise NotImplementedError

    monkeypatch.setattr(loop, "add_signal_handler", unsupported)
    before = signal.getsignal(signal.SIGINT)
    stop = asyncio.Event()
    with stop_on_signals(stop):
        signal.raise_signal(signal.SIGINT)
        await asyncio.wait_for(stop.wait(), timeout=5)
        signal.raise_signal(signal.SIGINT)  # asked twice: still just stopping
        await asyncio.sleep(0.05)
    assert signal.getsignal(signal.SIGINT) == before

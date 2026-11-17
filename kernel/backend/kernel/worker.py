"""The jobs worker and scheduler (SPEC.md section 6, decision 0035; contract
dev plans/contracts/k3-jobs.md).

A site runs it one of two ways. By default (`JOBS_IN_WEB=true`) `create_app`'s
lifespan runs one in the web process: one service, nothing more to deploy. A
site with heavy jobs (Vibrant Mindz's ffmpeg) runs its own instead, with
JOBS_IN_WEB=false on the web service:

    # backend/app/worker.py
    from kernel.worker import create_worker, serve
    from app.modules import MODULES
    raise SystemExit(serve(create_worker(modules=MODULES)))

Any number of workers share one queue:

- **Claiming.** Every `JOBS_POLL_SECONDS`, up to `JOBS_CONCURRENCY` jobs at
  once: due jobs of handlers this worker has, for modules that are on, taken
  with `FOR UPDATE SKIP LOCKED` (Basefra.me's scheduler), each with a lease
  renewed while it runs. A worker that dies leaves its jobs to their lease:
  once it lapses, another worker claims them as their next try. Every outcome
  is written only while the claim is still this worker's (its try number), so
  a try that outlived its lease can't undo the one that replaced it.
- **The scheduler** ticks once a minute under a transaction advisory lock,
  so one scheduler across every worker enqueues each slot once
  (`kernel_job_schedule`).
- **Stopping** (VybeSite's worker): SIGTERM or SIGINT stops claiming; running
  jobs get `JOBS_DRAIN_SECONDS` to finish; what's still running is left to
  its lease, and the process exits 0. A watchdog thread ends the process with
  status 124 when the event loop stops answering (a handler that blocks it),
  so the host starts a fresh one.
"""

from __future__ import annotations

import asyncio
import faulthandler
import json
import logging
import os
import signal
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, exists, func, or_, select, update

from kernel import clock, crypto
from kernel.jobs import (
    LEASE,
    LONGEST_RETRY_AFTER,
    RENEW_EVERY,
    Abandon,
    Context,
    Job,
    Retry,
    backoff,
)
from kernel.jobs import enqueue as enqueue_job
from kernel.models import Job as JobRow
from kernel.models import JobSchedule

if TYPE_CHECKING:
    from kernel.config import KernelConfig
    from kernel.db import Database
    from kernel.email import Mailer, Template
    from kernel.modules import InstalledModule, ModuleRegistry

log = logging.getLogger(__name__)

#: Arbitrary but fixed: Postgres advisory locks are one namespace per database.
SCHEDULER_LOCK = 7_130_352_035
#: How far back a scheduler looks for a missed slot.
CATCH_UP = timedelta(days=7)
#: How long the event loop may go without a beat before the watchdog ends the
#: process.
WATCHDOG_SECONDS = 120.0


@dataclass(frozen=True)
class _Claimed:
    id: uuid.UUID
    name: str
    payload: str | None
    sealed: bool
    tries: int


class Worker:
    """Runs the jobs it has handlers for, and ticks the scheduler."""

    def __init__(
        self,
        declared: Iterable[Job],
        *,
        registry: ModuleRegistry,
        database: Database,
        mailer: Mailer,
        concurrency: int = 4,
        poll: float = 1.0,
        drain: float = 20.0,
        lease: float = LEASE,
        renew_every: float = RENEW_EVERY,
    ) -> None:
        self.jobs: dict[str, Job] = {job.name: job for job in declared}
        self.registry = registry
        self.database = database
        self.mailer = mailer
        self.concurrency = concurrency
        self.poll = poll
        self.drain = drain
        self.lease = lease
        self.renew_every = renew_every
        #: The jobs this worker is running: id to the try it claimed.
        self._running: dict[uuid.UUID, int] = {}
        #: Called on every turn of the loop; `serve` points it at the watchdog.
        self.beat: Callable[[], None] = lambda: None
        #: Jobs still cleaning up after `run` cancelled them; `serve` ends the
        #: process rather than wait for them.
        self.stragglers: set[asyncio.Task[None]] = set()

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self.jobs)

    async def _owners(self) -> list[str]:
        async with self.database.sessions() as db:
            on = await self.registry.on(db)
        return sorted(on | {"kernel"})

    def _claimable(self, owners: list[str], now: Any) -> Any:
        return and_(
            JobRow.name.in_(sorted(self.jobs)),
            JobRow.module.in_(owners),
            or_(
                and_(JobRow.state == "queued", JobRow.run_at <= now),
                and_(JobRow.state == "running", JobRow.locked_until < now),
            ),
        )

    async def _claim(self, limit: int) -> list[_Claimed]:
        if limit <= 0 or not self.jobs:
            return []
        owners = await self._owners()
        now = clock.now()
        due = (
            select(JobRow.id)
            .where(self._claimable(owners, now))
            .order_by(JobRow.run_at, JobRow.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        statement = (
            update(JobRow)
            .where(JobRow.id.in_(due))
            .values(
                state="running",
                locked_until=now + timedelta(seconds=self.lease),
                tries=JobRow.tries + 1,
            )
            .returning(JobRow.id, JobRow.name, JobRow.payload, JobRow.sealed, JobRow.tries)
        )
        async with self.database.sessions() as db:
            rows = (await db.execute(statement)).all()
            await db.commit()
        return [_Claimed(*row) for row in rows]

    async def _finish(self, claimed: _Claimed, state: str, **values: Any) -> None:
        """Writes the outcome, only while the claim is still this worker's."""
        values = {"state": state, "locked_until": None, **values}
        if state != "queued":
            values["finished_at"] = clock.now()
            if claimed.sealed:
                values["payload"] = None
        statement = (
            update(JobRow)
            .where(
                JobRow.id == claimed.id, JobRow.state == "running", JobRow.tries == claimed.tries
            )
            .values(**values)
        )
        async with self.database.sessions() as db:
            await db.execute(statement)
            await db.commit()

    def _payload(self, claimed: _Claimed) -> dict[str, Any]:
        if claimed.payload is None:
            return {}
        text = crypto.open(claimed.payload) if claimed.sealed else claimed.payload
        payload: dict[str, Any] = json.loads(text)
        return payload

    async def _run_one(self, claimed: _Claimed) -> None:
        try:
            await self._try(claimed)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # the outcome couldn't be written: the lease decides
            log.warning(
                "Job %s's outcome wasn't recorded (%s); its lease will lapse and it will run again.",
                claimed.name,
                type(error).__name__,
            )

    async def _try(self, claimed: _Claimed) -> None:
        job = self.jobs[claimed.name]
        if claimed.tries > job.tries:  # its last try's worker died
            await self._finish(claimed, "dead", last_error="WorkerLost", tries=claimed.tries - 1)
            return
        try:
            payload = self._payload(claimed)
        except Exception as error:
            await self._finish(claimed, "dead", last_error=type(error).__name__)
            return
        context = Context(claimed.id, claimed.name, claimed.tries, self.database, self.mailer)
        self._running[claimed.id] = claimed.tries
        try:
            await asyncio.wait_for(job.run(context, payload), timeout=job.timeout)
        except asyncio.CancelledError:
            raise  # stopped mid-job: left to its lease
        except Abandon:
            await self._finish(claimed, "dead", last_error="Abandon")
        except Exception as error:
            reason = type(error).__name__
            if claimed.tries >= job.tries:
                log.warning(
                    "Job %s is dead after %d tries (%s).", claimed.name, claimed.tries, reason
                )
                await self._finish(claimed, "dead", last_error=reason)
            else:
                wait = backoff(claimed.tries)
                if isinstance(error, Retry) and error.after is not None:
                    wait = min(error.after, LONGEST_RETRY_AFTER)
                log.warning(
                    "Job %s failed on try %d (%s); trying again in %.0f seconds.",
                    claimed.name,
                    claimed.tries,
                    reason,
                    wait,
                )
                await self._finish(
                    claimed,
                    "queued",
                    last_error=reason,
                    run_at=clock.now() + timedelta(seconds=wait),
                )
        else:
            await self._finish(claimed, "done", last_error=None)
        finally:
            # Only this try's: a newer try of the same job, claimed again here
            # once this one's lease lapsed, keeps its renewal (CodeRabbit on #63).
            if self._running.get(claimed.id) == claimed.tries:
                del self._running[claimed.id]

    async def _renew(self) -> None:
        if not self._running:
            return
        until = clock.now() + timedelta(seconds=self.lease)
        held = list(self._running.items())
        async with self.database.sessions() as db:
            for job_id, tries in held:
                await db.execute(
                    update(JobRow)
                    .where(JobRow.id == job_id, JobRow.state == "running", JobRow.tries == tries)
                    .values(locked_until=until)
                )
            await db.commit()

    @asynccontextmanager
    async def _renewals(self) -> AsyncIterator[None]:
        async def renew_forever() -> None:
            while True:
                await asyncio.sleep(self.renew_every)
                try:
                    await self._renew()
                except Exception as error:
                    log.warning(
                        "Couldn't renew the running jobs' leases (%s).", type(error).__name__
                    )

        task = asyncio.create_task(renew_forever())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _held_elsewhere(self) -> bool:
        owners = await self._owners()
        now = clock.now()
        held = exists().where(
            JobRow.name.in_(sorted(self.jobs)),
            JobRow.module.in_(owners),
            JobRow.state == "running",
            JobRow.locked_until >= now,
        )
        async with self.database.sessions() as db:
            return bool(await db.scalar(select(held)))

    async def run_due(self, *, wait: float = 10.0, limit: int = 1000) -> int:
        """Runs every job due now, oldest first and one at a time, then waits
        up to `wait` seconds for the ones other workers hold, so the caller
        reads a settled queue in the order it was filled: for tests and the
        harness, whose mail then arrives as each route queued it. Returns how
        many jobs this call ran."""
        ran = 0
        deadline: float | None = None
        async with self._renewals():
            while ran < limit:
                # One claim at a time: a job claimed but waiting its turn
                # would hold a lease nothing renews.
                claimed = await self._claim(1)
                if claimed:
                    await self._run_one(claimed[0])
                    ran += 1
                    continue
                if deadline is None:
                    deadline = time.monotonic() + wait
                if time.monotonic() >= deadline or not await self._held_elsewhere():
                    break
                await asyncio.sleep(0.05)
        return ran

    async def tick(self) -> int:
        """One turn of the scheduler: enqueues each scheduled job's newest slot
        not yet enqueued. Returns how many it enqueued; 0 when another
        scheduler holds the lock."""
        scheduled = [job for job in self.jobs.values() if job.schedule is not None]
        if not scheduled:
            return 0
        now = clock.now()
        enqueued = 0
        async with self.database.sessions() as db:
            if not await db.scalar(select(func.pg_try_advisory_xact_lock(SCHEDULER_LOCK))):
                await db.rollback()
                return 0
            on = await self.registry.on(db) | {"kernel"}
            for job in scheduled:
                if job.owner not in on or job.schedule is None:
                    continue
                row = await db.get(JobSchedule, job.name)
                if row is None:  # new: from now on, nothing back-filled
                    db.add(
                        JobSchedule(name=job.name, last_slot=now.replace(second=0, microsecond=0))
                    )
                    continue
                slot = job.schedule.latest(now, after=max(row.last_slot, now - CATCH_UP))
                if slot is None:
                    continue
                await enqueue_job(db, job.name, None, run_at=slot, key=slot.isoformat())
                row.last_slot = slot
                enqueued += 1
            await db.commit()
        return enqueued

    async def run(self, stop: asyncio.Event) -> None:
        """Claims and runs jobs, and ticks the scheduler each minute, until
        `stop` is set; then gives running jobs `drain` seconds and leaves the
        rest to their leases."""
        tasks: set[asyncio.Task[None]] = set()
        last_minute = None
        async with self._renewals():
            try:
                while not stop.is_set():
                    self.beat()
                    minute = clock.now().replace(second=0, microsecond=0)
                    if minute != last_minute:
                        last_minute = minute
                        try:
                            await self.tick()
                        except Exception as error:
                            log.warning("The scheduler's tick failed (%s).", type(error).__name__)
                    free = self.concurrency - len(tasks)
                    claimed: list[_Claimed] = []
                    if free > 0 and not stop.is_set():
                        try:
                            claimed = await self._claim(free)
                        except Exception as error:
                            log.warning("Couldn't claim jobs (%s).", type(error).__name__)
                    for job in claimed:
                        task = asyncio.create_task(self._run_one(job))
                        tasks.add(task)
                        task.add_done_callback(tasks.discard)
                    if claimed and len(claimed) == free:
                        await asyncio.sleep(0)  # more may be due: claim again
                        continue
                    await _nap(stop, tasks, self.poll)
            finally:
                pending = await self._wait_beating(set(tasks), self.drain)
                for task in pending:
                    task.cancel()
                # Bounded too: a handler still cleaning up after its cancel is
                # left to its lease rather than holding the stop up.
                self.stragglers = await self._wait_beating(pending, max(self.drain, 1.0))
                if self.stragglers:
                    log.warning(
                        "%d jobs are still finishing after the drain; their leases "
                        "will lapse and another worker will run them again.",
                        len(self.stragglers),
                    )

    async def _wait_beating(
        self, pending: set[asyncio.Task[None]], seconds: float
    ) -> set[asyncio.Task[None]]:
        """Waits up to `seconds` for `pending`, beating about once a second: a
        drain may outlast the watchdog's limit, and only a loop that stops
        answering should trip it. Returns the tasks still running."""
        deadline = time.monotonic() + seconds
        while pending and (left := deadline - time.monotonic()) > 0:
            self.beat()
            _, pending = await asyncio.wait(pending, timeout=min(left, 1.0))
        return pending


async def _nap(stop: asyncio.Event, tasks: set[asyncio.Task[None]], seconds: float) -> None:
    """Sleeps up to `seconds`, waking early on a stop request or a job ending."""
    waiter = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({waiter, *tasks}, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        waiter.cancel()
        with suppress(asyncio.CancelledError):
            await waiter


# --- a worker process of its own ----------------------------------------------------------


class Watchdog:
    """Ends the process with status 124 when `beat` isn't called for
    `seconds`: a handler that blocks the event loop holds everything up, and
    the host's restart starts a fresh worker (VybeSite's watchdog). A thread,
    not a task: a task needs the loop it's guarding."""

    def __init__(self, seconds: float, *, end: Callable[[int], object] = os._exit) -> None:
        self.seconds = seconds
        self._end = end
        self._last = time.monotonic()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="jobs-watchdog", daemon=True)

    def beat(self) -> None:
        self._last = time.monotonic()

    def _watch(self) -> None:
        while not self._stopped.wait(min(1.0, self.seconds / 4)):
            if time.monotonic() - self._last > self.seconds:
                log.critical(
                    "watchdog: the jobs worker's loop hasn't answered for %g seconds, so the "
                    "process ends with status 124 for a fresh worker.",
                    self.seconds,
                )
                with suppress(Exception):
                    faulthandler.dump_traceback(all_threads=True)  # code locations only
                self._end(124)
                return

    def __enter__(self) -> Watchdog:
        self.beat()
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stopped.set()
        self._thread.join(timeout=5)


def _asked_to_stop(stop: asyncio.Event, sig: int) -> None:
    if not stop.is_set():
        log.info("%s: the worker stops once its running jobs finish.", signal.Signals(sig).name)
    stop.set()


@contextmanager
def stop_on_signals(stop: asyncio.Event) -> Iterator[None]:
    """For the length of the block, SIGTERM and SIGINT set `stop`. SIGTERM is
    how Railway, Docker and systemd end a process; a handler is also what
    makes Python, as a container's PID 1, receive it at all. Windows' event
    loop takes no signal handlers, so `signal.signal` stands in there."""
    loop = asyncio.get_running_loop()
    signals = (signal.SIGTERM, signal.SIGINT)
    replaced: dict[int, Any] = {}
    for sig in signals:
        try:
            loop.add_signal_handler(sig, _asked_to_stop, stop, sig)
        except NotImplementedError:
            replaced[sig] = signal.signal(
                sig,
                lambda signum, _frame: loop.call_soon_threadsafe(_asked_to_stop, stop, signum),
            )
    try:
        yield
    finally:
        for sig in signals:
            if sig in replaced:
                signal.signal(sig, replaced[sig])
            else:
                loop.remove_signal_handler(sig)


def serve(
    worker: Worker,
    *,
    watchdog: float = WATCHDOG_SECONDS,
    end: Callable[[int], object] = os._exit,
) -> int:
    """Runs `worker` as a process of its own until SIGTERM or SIGINT. Returns
    the exit status: 0. A job still cleaning up after the drain ends the
    process at once instead (`end`), still with 0: `asyncio.run` would wait for
    it however long, and its lease lapses for another worker."""

    async def main() -> None:
        stop = asyncio.Event()
        try:
            with stop_on_signals(stop), Watchdog(watchdog) as dog:
                worker.beat = dog.beat
                log.info("The jobs worker is running %d kinds of job.", len(worker.jobs))
                await worker.run(stop)
        finally:
            await worker.database.dispose()
        if worker.stragglers:
            log.warning(
                "Ending the worker with %d jobs still cleaning up; their leases will lapse.",
                len(worker.stragglers),
            )
            end(0)

    asyncio.run(main())
    return 0


def create_worker(
    *,
    modules: Iterable[InstalledModule] = (),
    config: KernelConfig | None = None,
    database: Database | None = None,
    mailer: Mailer | None = None,
    emails: Mapping[str, Template] | None = None,
) -> Worker:
    """A worker for a process of its own, built as `create_app` builds the
    site: the same modules, config checks, mail and templates."""
    from kernel.app import assemble

    built = assemble(modules=modules, config=config, mailer=mailer, emails=emails, role="worker")
    return Worker(
        built.jobs,
        registry=built.registry,
        database=database or built.database(),
        mailer=built.mailer,
        concurrency=built.config.jobs_concurrency,
        poll=built.config.jobs_poll_seconds,
        drain=built.config.jobs_drain_seconds,
    )

"""Background and scheduled work (SPEC.md section 6, decision 0035; contract
dev plans/contracts/k3-jobs.md).

A module declares its jobs in `backend/<id_>/jobs.py` and queues them in the
same transaction as the change they follow:

    @jobs.handler("blog.send_digest", tries=5, timeout=300)
    async def send_digest(ctx: jobs.Context, payload: dict[str, Any]) -> None: ...

    @jobs.scheduled("*/5 * * * *", "blog.publish_scheduled")
    async def publish_scheduled(ctx: jobs.Context) -> None: ...

    await jobs.enqueue(db, "blog.send_digest", {"week": 47})
    await db.commit()   # the job exists exactly when the change does

- **Names** are `<owner>.<name>`: the module's id (or `kernel`), then
  `[a-z][a-z0-9_]*`. A module declares only its own, and each scheduled job is
  listed in its module.json's `jobs` with the same schedule; `create_app` and
  `create_worker` refuse to start otherwise (`build`).
- **At least once.** The worker (`kernel.worker`) runs each job until it
  returns, retrying a failure, so a handler MUST be safe to run twice.
- **Payloads** are JSON objects of at most 64 KiB, holding ids rather than
  rows. `sealed=True` keeps one `crypto.seal`ed and wipes it when the job ends:
  for anything a database dump shouldn't give away, such as a mail's link.
- **`key`** makes an enqueue a no-op while a job of that name and key is
  queued or running; once it has ended, the key is free again.
- **Outcomes.** A handler that returns is done. `Retry(after)` or any other
  exception queues it again after `backoff` (30 s, doubling to an hour, with
  jitter) or `after`, until its `tries` are used, then it is dead. `Abandon`
  is dead at once. The row keeps the exception's type name, never its message,
  which may hold a value.
- **Scheduled jobs** run once a slot (UTC, `kernel.cron`); missed slots
  collapse into one run, and a scheduled job tries once by default: its next
  slot is its retry.
"""

from __future__ import annotations

import inspect
import json
import re
import secrets
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, crypto
from kernel.cron import Cron, parse
from kernel.models import Job as JobRow

if TYPE_CHECKING:
    from kernel.db import Database
    from kernel.email import Mailer

#: `<owner>.<name>`: the owner as a module id (SPEC.md section 5) or `kernel`.
NAME = re.compile(r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.([a-z][a-z0-9_]*)")
MAX_NAME = 130
MAX_PAYLOAD = 64 * 1024
MAX_KEY = 200
DEFAULT_TRIES = 5
MAX_TRIES = 100
DEFAULT_TIMEOUT = 300.0
MAX_TIMEOUT = 6 * 3600.0
#: A claimed job is the worker's for this long, renewed every RENEW_EVERY while
#: it runs; a job whose lease lapsed (its worker died) is claimed again.
LEASE = 60.0
RENEW_EVERY = 20.0
FIRST_WAIT = 30.0
LONGEST_WAIT = 3600.0
#: The longest wait a handler's Retry(after) gets.
LONGEST_RETRY_AFTER = 24 * 3600.0

_random = secrets.SystemRandom()


class Retry(Exception):
    """Raised by a handler: try again later (after `after` seconds, or the
    backoff). It counts as a try."""

    def __init__(self, after: float | None = None) -> None:
        if after is not None and not after >= 0:
            raise ValueError("Retry's wait is a number of seconds, 0 or more.")
        super().__init__("try again later")
        self.after = after


class Abandon(Exception):
    """Raised by a handler: no more tries; the job is dead now (a refused
    address, a row that's gone)."""


@dataclass(frozen=True)
class Context:
    """What a handler gets besides its payload."""

    job_id: uuid.UUID
    name: str
    #: 1 on the first try; a try whose worker died counts.
    try_number: int
    _database: Database = field(repr=False)
    _mailer: Mailer = field(repr=False)

    def sessions(self) -> AsyncSession:
        """A new session, as `async with ctx.sessions() as db:`. Open one where
        it's needed and commit it: a session held through a long job holds a
        connection."""
        return self._database.sessions()


Handler = Callable[[Context, dict[str, Any]], Awaitable[None]]
ScheduledHandler = Callable[[Context], Awaitable[None]]


@dataclass(frozen=True)
class Job:
    """A declared job: what `@jobs.handler` and `@jobs.scheduled` make."""

    name: str
    run: Handler = field(repr=False, compare=False)
    tries: int
    timeout: float
    schedule: Cron | None = None

    @property
    def owner(self) -> str:
        return self.name.partition(".")[0]


def check_name(name: str) -> None:
    if len(name) > MAX_NAME or NAME.fullmatch(name) is None:
        raise ValueError(
            "A job's name is <module id>.<name>, the name in [a-z][a-z0-9_]* and "
            f"{MAX_NAME} characters at most, not {name!r}."
        )


def _checked(name: str, function: Callable[..., Any], tries: int, timeout: float) -> None:
    check_name(name)
    if not 1 <= tries <= MAX_TRIES:
        raise ValueError(f"{name}'s tries must be 1 to {MAX_TRIES}.")
    if not 0 < timeout <= MAX_TIMEOUT:
        raise ValueError(
            f"{name}'s timeout must be more than 0 and at most {MAX_TIMEOUT:g} seconds."
        )
    if not inspect.iscoroutinefunction(function):
        raise TypeError(f"{name}'s handler must be an async function.")


def handler(
    name: str, *, tries: int = DEFAULT_TRIES, timeout: float = DEFAULT_TIMEOUT
) -> Callable[[Handler], Job]:
    """Declares `name`'s handler: `async def f(ctx, payload)`."""

    def declare(function: Handler) -> Job:
        _checked(name, function, tries, timeout)
        return Job(name, function, tries, float(timeout))

    return declare


def scheduled(
    line: str, name: str, *, tries: int = 1, timeout: float = DEFAULT_TIMEOUT
) -> Callable[[ScheduledHandler], Job]:
    """Declares a job run on the cron line `line` (UTC): `async def f(ctx)`."""
    schedule = parse(line)

    def declare(function: ScheduledHandler) -> Job:
        _checked(name, function, tries, timeout)

        async def run(ctx: Context, payload: dict[str, Any]) -> None:
            await function(ctx)

        return Job(name, run, tries, float(timeout), schedule)

    return declare


def build(
    declared: Iterable[tuple[str, Iterable[Job], Sequence[Any] | None]],
) -> tuple[Job, ...]:
    """Every job, from (owner, its jobs, its module.json's `jobs` or None for
    the kernel) triples. ValueError, naming the job, on any the start can't take."""
    found: dict[str, Job] = {}
    for owner, owned, listed in declared:
        owned = tuple(owned)
        for job in owned:
            if job.owner != owner:
                raise ValueError(f"{owner} may only declare {owner}.* jobs, not {job.name}.")
            if job.name in found:
                raise ValueError(f"The job {job.name} is declared twice.")
            found[job.name] = job
        if listed is None:
            continue
        wanted: dict[str, str] = {}
        for entry in listed:
            if isinstance(entry, Mapping):
                wanted[f"{owner}.{entry.get('name')}"] = str(entry.get("schedule", ""))
        coded = {job.name: job.schedule.line for job in owned if job.schedule is not None}
        for name, line in wanted.items():
            if name not in coded:
                raise ValueError(
                    f"{owner}'s module.json lists the scheduled job {name}, which its jobs.py "
                    "doesn't declare with @jobs.scheduled."
                )
            if parse(line).line != coded[name]:
                raise ValueError(
                    f"{name} runs on {coded[name]!r} in jobs.py but {line!r} in module.json."
                )
        for name in sorted(coded.keys() - wanted.keys()):
            raise ValueError(
                f"{name} is scheduled in jobs.py but missing from {owner}'s module.json jobs."
            )
    return tuple(found.values())


def _encoded(payload: Mapping[str, Any] | None, limit: int) -> str:
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise ValueError("A job's payload is a JSON object (a dict), holding ids rather than rows.")
    plain = dict(payload)
    try:
        encoded = json.dumps(plain, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        same = json.loads(encoded) == plain
    except (TypeError, ValueError):
        same = False
    if not same:
        raise ValueError(
            "A job's payload must be plain JSON: string keys; strings, finite numbers, "
            "booleans, None, lists and objects."
        )
    if len(encoded.encode()) > limit:
        raise ValueError(
            f"A job's payload holds at most {limit // 1024} KiB of JSON; store more elsewhere."
        )
    return encoded


def _check_key(key: str | None) -> None:
    if key is None:
        return
    if not 1 <= len(key) <= MAX_KEY or any(
        unicodedata.category(character) in ("Cc", "Zl", "Zp") for character in key
    ):
        raise ValueError(f"A job's key is 1 to {MAX_KEY} characters on one line.")


async def enqueue(
    db: AsyncSession,
    name: str,
    payload: Mapping[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    key: str | None = None,
    sealed: bool = False,
) -> uuid.UUID | None:
    """Adds a job to the caller's transaction, which the caller commits: due
    at `run_at` (now if None). Returns its id, or None when a job of this
    name and `key` is already queued or running."""
    return await enqueue_up_to(
        db, name, payload, run_at=run_at, key=key, sealed=sealed, limit=MAX_PAYLOAD
    )


async def enqueue_up_to(
    db: AsyncSession,
    name: str,
    payload: Mapping[str, Any] | None,
    *,
    run_at: datetime | None,
    key: str | None,
    sealed: bool,
    limit: int,
) -> uuid.UUID | None:
    """`enqueue` with another payload limit: the kernel's mail job, whose
    bodies may be bigger than a module's ids (kernel.email.queue)."""
    check_name(name)
    encoded = _encoded(payload, limit)
    _check_key(key)
    if run_at is None:
        run_at = clock.now()
    elif run_at.tzinfo is None:
        raise ValueError("A job's run_at must say its zone: give a UTC datetime.")
    statement = (
        insert(JobRow)
        .values(
            id=uuid.uuid4(),
            name=name,
            module=name.partition(".")[0],
            payload=crypto.seal(encoded) if sealed else encoded,
            sealed=sealed,
            key=key,
            run_at=run_at,
        )
        .on_conflict_do_nothing(
            index_elements=[JobRow.name, JobRow.key],
            index_where=text("state IN ('queued', 'running')"),
        )
        .returning(JobRow.id)
    )
    added: uuid.UUID | None = (await db.execute(statement)).scalar_one_or_none()
    return added


def backoff(tries: int) -> float:
    """The wait before the next try, after `tries` tries: 30 s, doubling to an
    hour, give or take 10 % so failures that came together spread out."""
    base = min(FIRST_WAIT * float(2 ** min(tries - 1, 20)), LONGEST_WAIT)
    return base * _random.uniform(0.9, 1.1)


# --- the kernel's own job: pruning -------------------------------------------------------

KEEP_DONE = timedelta(days=7)
KEEP_DEAD = timedelta(days=30)
_PRUNE_BATCH = 1000


async def _prune(ctx: Context) -> None:
    """Deletes done jobs after 7 days and dead ones after 30; queued and
    running jobs are never pruned."""
    now = clock.now()
    ended = or_(
        and_(JobRow.state == "done", JobRow.finished_at < now - KEEP_DONE),
        and_(JobRow.state == "dead", JobRow.finished_at < now - KEEP_DEAD),
    )
    while True:
        async with ctx.sessions() as db:
            doomed = (
                select(JobRow.id).where(ended).limit(_PRUNE_BATCH).with_for_update(skip_locked=True)
            )
            result = await db.execute(delete(JobRow).where(JobRow.id.in_(doomed)))
            await db.commit()
        if getattr(result, "rowcount", 0) < _PRUNE_BATCH:
            return


PRUNE = scheduled("41 3 * * *", "kernel.prune_jobs", timeout=900)(_prune)

"""The admin's Settings pages at /api/kernel/admin (K4 contract §2, additions
6 to 8, change 19; decision 0046): each settings section's form, save and
history; the Features page's module switches; and System, with the failed
background jobs and their retry and discard.

**Who:** a section's form and System need `kernel.settings.manage`, the
switches `kernel.module.manage`, and acting on a failed job
`kernel.jobs.manage` (System is read with the settings permission, so a job
is retried only by someone who can also see why it failed).

**Failed jobs that can't run again.** A sealed job's contents are wiped when
it fails for good (decision 0035), and a job whose name nothing declares has
no handler: both read as `retryable: false` and can only be discarded (the
owner, 2026-11-19). A retry gives a job its tries again, due now.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import and_, delete, exists, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, clock
from kernel.answers import Answer, Id, When
from kernel.auth.dependencies import require_permission
from kernel.auth.models import User
from kernel.config import KernelConfig, mail_problems, storage_missing
from kernel.db import get_db
from kernel.errors import Problem
from kernel.models import Job
from kernel.modules import ModuleRegistry
from kernel.settings import settings
from kernel.version import __version__

router = APIRouter(tags=["kernel"])

SETTINGS = "kernel.settings.manage"
MODULES = "kernel.module.manage"
JOBS = "kernel.jobs.manage"

#: How late a job the worker would take may be before the worker reads as behind.
BEHIND = timedelta(minutes=2)


def _invalid_cursor(what: str) -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={"cursor": [f"Not a page of {what}."]},
    )


# --- what these routes answer (kernel.answers, decision 0042) ---------------------------


class SettingsForm(Answer):
    """A section as its form reads it: a secret as `{kept, changes}`."""

    version: int
    values: dict[str, Any]


class SettingsSaved(Answer):
    version: int
    changed: list[str]
    merged: list[str]


class SettingsVersion(Answer):
    number: int
    changed: list[str]
    via: str
    saved_at: When
    saved_by_id: Id | None


class Saver(Answer):
    name: str | None
    email: str


class SettingsHistory(Answer):
    items: list[SettingsVersion]
    next_cursor: str | None
    #: Each saver on the page who still has an account, by id.
    people: dict[str, Saver]


class ModuleItem(Answer):
    id: str
    name: str
    summary: str
    #: The manifest's: content, community, comms, commerce, admin, media, security or ai.
    category: str
    #: Allowed, switched on, and every module it requires on.
    on: bool
    #: The admin's own switch, kept while a module it requires is off.
    switched: bool
    requires: list[str]
    required_by: list[str]


class ModuleList(Answer):
    items: list[ModuleItem]


class JobCounts(Answer):
    queued: int
    running: int
    dead: int
    worker: Literal["ok", "behind"]


class Storage(Answer):
    configured: bool
    #: A public bucket for files anyone may fetch, beside the private one.
    public: bool


class Services(Answer):
    email: Literal["smtp", "resend", "log"]
    storage: Storage


class ModuleCounts(Answer):
    installed: int
    on: int


class System(Answer):
    jobs: JobCounts
    services: Services
    version: str
    modules: ModuleCounts


class DeadJob(Answer):
    id: Id
    name: str
    module: str
    tries: int
    #: The exception's type name, never its message.
    last_error: str | None
    failed_at: When
    retryable: bool


class DeadJobs(Answer):
    items: list[DeadJob]
    next_cursor: str | None


class Retried(Answer):
    state: Literal["queued"]
    #: The job as queued again: a new one, so no claim of the old can match it.
    id: Id


# --- settings: each section's form, save and history -------------------------------------


class SettingsSave(BaseModel):
    """`{version, changes}`: the form's values by field, read at `version`."""

    model_config = ConfigDict(strict=True, extra="forbid")

    version: int = Field(ge=0)
    changes: dict[str, Any]


#: A section's id in the path: a module's id, or the kernel's `kernel.<name>`.
Section = Annotated[str, Path(alias="id", max_length=130)]


@router.get(
    "/admin/settings/{id}",
    dependencies=[Depends(require_permission(SETTINGS))],
    response_model=SettingsForm,
)
async def settings_form(section: Section, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The section's values at its version; 404 for one no module registers."""
    return await settings.form(db, section)


@router.put("/admin/settings/{id}", response_model=SettingsSaved)
async def save_settings(
    body: SettingsSave,
    section: Section,
    user: User = Depends(require_permission(SETTINGS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Saves what the form changed, merged with any save since it was read
    (kernel.settings): 409 `kernel.settings_conflict` when both changed one
    field, saving nothing."""
    saved = await settings.save(db, section, body.changes, version=body.version, by=user.id)
    return {"version": saved.version, "changed": saved.changed, "merged": saved.merged}


_NUMBER = re.compile(r"[1-9][0-9]{0,9}")


@router.get(
    "/admin/settings/{id}/history",
    dependencies=[Depends(require_permission(SETTINGS))],
    response_model=SettingsHistory,
)
async def settings_history(
    section: Section,
    db: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The section's saves, newest first, in pages, with who made them."""
    before: int | None = None
    if cursor is not None:
        if not _NUMBER.fullmatch(cursor):
            raise _invalid_cursor("this history")
        before = int(cursor)
    found = await settings.history(db, section, before=before, limit=limit + 1)
    page = found[:limit]
    savers = {version["saved_by_id"] for version in page if version["saved_by_id"] is not None}
    people = {
        str(person.id): {"name": person.display_name, "email": person.email}
        for person in (await db.scalars(select(User).where(User.id.in_(savers))) if savers else ())
    }
    return {
        "items": [
            {
                "number": version["number"],
                "changed": version["changed"],
                "via": version["via"],
                "saved_at": version["saved_at"].isoformat(),
                "saved_by_id": (
                    str(version["saved_by_id"]) if version["saved_by_id"] is not None else None
                ),
            }
            for version in page
        ],
        "next_cursor": str(page[-1]["number"]) if len(found) > limit else None,
        "people": people,
    }


# --- features: the module switches ---------------------------------------------------------


class Switch(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    on: StrictBool


def _registry(request: Request) -> ModuleRegistry:
    registry: ModuleRegistry = request.app.state.modules
    return registry


@router.get(
    "/admin/modules",
    dependencies=[Depends(require_permission(MODULES))],
    response_model=ModuleList,
)
async def modules(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The modules MODULES allows, by name, each with its switch and needs."""
    return {"items": await _registry(request).listing(db)}


@router.put("/admin/modules/{id}", response_model=ModuleList)
async def switch_module(
    request: Request,
    body: Switch,
    module_id: Annotated[str, Path(alias="id", max_length=64)],
    user: User = Depends(require_permission(MODULES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Switches a module on or off (kernel.modules): off turns off every
    module requiring it too. Answers the whole list."""
    registry = _registry(request)
    await registry.set_enabled(db, module_id, body.on, by=user.id)
    return {"items": await registry.listing(db)}


# --- System --------------------------------------------------------------------------------


def _email(config: KernelConfig) -> Literal["smtp", "resend", "log"]:
    """The adapter that sends mail: none set, or set in part, is the log."""
    adapter = config.mail_adapter
    if not adapter or mail_problems(config):
        return "log"
    return adapter


def _storage(config: KernelConfig) -> dict[str, bool]:
    configured = not storage_missing(config)
    return {
        "configured": configured,
        "public": configured and bool(config.storage_public_bucket.strip()),
    }


def would_take(declared: frozenset[str], on: frozenset[str]) -> Any:
    """The queued jobs the worker takes: their names declared, their module
    on or the kernel's (kernel.worker's own rule)."""
    return and_(
        Job.state == "queued",
        Job.name.in_(sorted(declared)),
        Job.module.in_(sorted(on | {"kernel"})),
    )


async def job_counts(
    db: AsyncSession, declared: frozenset[str], on: frozenset[str]
) -> dict[str, Any]:
    """How many jobs are queued, running and dead, and whether a job the
    worker would take is more than BEHIND past due."""
    grouped = await db.execute(select(Job.state, func.count()).group_by(Job.state))
    counted = {state: int(count) for state, count in grouped.all()}
    late = await db.scalar(
        select(exists().where(would_take(declared, on), Job.run_at < clock.now() - BEHIND))
    )
    return {
        "queued": counted.get("queued", 0),
        "running": counted.get("running", 0),
        "dead": counted.get("dead", 0),
        "worker": "behind" if late else "ok",
    }


def _declared(request: Request) -> frozenset[str]:
    names: frozenset[str] = request.app.state.worker.names
    return names


@router.get(
    "/admin/system",
    dependencies=[Depends(require_permission(SETTINGS))],
    response_model=System,
)
async def system(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The queue, the services as the deploy set them, the build and its
    modules (no health check: K4 contract §6)."""
    config: KernelConfig = request.app.state.config
    registry = _registry(request)
    on = await registry.on(db, fresh=True)
    return {
        "jobs": await job_counts(db, _declared(request), on),
        "services": {"email": _email(config), "storage": _storage(config)},
        "version": __version__,
        "modules": {"installed": len(registry.installed), "on": len(on)},
    }


# --- the failed jobs: the list, retry and discard ------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_CURSOR = re.compile(r"([0-9]{1,19})\.([0-9a-f]{32})")


def _failed_at(job: Job) -> datetime:
    """When a dead job failed: the list reads only jobs that have a time."""
    return cast(datetime, job.finished_at)


def _cursor_of(job: Job) -> str:
    micros = (_failed_at(job) - _EPOCH) // timedelta(microseconds=1)
    return f"{micros}.{job.id.hex}"


def _after(cursor: str) -> tuple[datetime, uuid.UUID]:
    found = _CURSOR.fullmatch(cursor)
    try:
        if found is None:
            raise ValueError(cursor)
        return _EPOCH + timedelta(microseconds=int(found[1])), uuid.UUID(hex=found[2])
    except (ValueError, OverflowError):
        raise _invalid_cursor("the failed jobs") from None


def retryable(job: Job, declared: frozenset[str]) -> bool:
    """Whether a dead job can run again: it has a handler, and its payload
    wasn't wiped (a sealed one is, when it fails for good)."""
    return job.name in declared and not (job.sealed and job.payload is None)


def dead_item(job: Job, declared: frozenset[str]) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "name": job.name,
        "module": job.module,
        "tries": job.tries,
        "last_error": job.last_error,
        "failed_at": _failed_at(job).isoformat(),
        "retryable": retryable(job, declared),
    }


@router.get(
    "/admin/jobs/dead",
    dependencies=[Depends(require_permission(SETTINGS))],
    response_model=DeadJobs,
)
async def dead_jobs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The jobs that failed for good, the newest failure first, in pages;
    never a payload."""
    statement = select(Job).where(Job.state == "dead", Job.finished_at.is_not(None))
    if cursor is not None:
        at, ident = _after(cursor)
        statement = statement.where(
            or_(Job.finished_at < at, and_(Job.finished_at == at, Job.id < ident))
        )
    statement = statement.order_by(Job.finished_at.desc(), Job.id.desc()).limit(limit + 1)
    found = list(await db.scalars(statement))
    page = found[:limit]
    declared = _declared(request)
    return {
        "items": [dead_item(job, declared) for job in page],
        "next_cursor": _cursor_of(page[-1]) if len(found) > limit else None,
    }


JOB = "/admin/jobs/{id}"


async def _dead_held(db: AsyncSession, job_id: uuid.UUID) -> Job:
    """The job, locked for this transaction; 404 if there's none, 409 unless
    it failed for good."""
    job = await db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise Problem("kernel.job_not_found", 404, "There's no such job.")
    if job.state != "dead":
        raise Problem(
            "kernel.job_not_dead", 409, "This job hasn't failed for good: it's still to run."
        )
    return job


def _not_retryable(detail: str) -> Problem:
    return Problem("kernel.job_not_retryable", 409, detail)


@router.post(f"{JOB}/retry", response_model=Retried)
async def retry_job(
    request: Request,
    job_id: Annotated[uuid.UUID, Path(alias="id")],
    user: User = Depends(require_permission(JOBS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Queues a failed job again, due now, with all its tries: as a new job
    with the old one's name, module, payload and key, the old one removed.
    The worker knows a claim by its job's id and try, so a worker that lost
    the old job's lease and wakes late can never write over the new run, as
    resetting the old row's tries would let it (CodeRabbit on #87)."""
    job = await _dead_held(db, job_id)
    name = job.name
    if job.name not in _declared(request):
        raise _not_retryable("Nothing on this site runs this job any more, so discard it.")
    if job.sealed and job.payload is None:
        raise _not_retryable(
            "This job's contents were private, so they were wiped when it failed. It can't "
            "run again: discard it."
        )
    anew = uuid.uuid4()
    await db.execute(delete(Job).where(Job.id == job_id))
    try:
        # The live-key index refuses a second waiting run of one name and key.
        await db.execute(
            insert(Job).values(
                id=anew,
                name=job.name,
                module=job.module,
                payload=job.payload,
                sealed=job.sealed,
                key=job.key,
                run_at=clock.now(),
            )
        )
    except IntegrityError:
        await db.rollback()
        raise _not_retryable(
            "Another run of this job is already waiting: discard this one."
        ) from None
    audit.record(
        db,
        "kernel.job.retried",
        actor=user.id,
        target=("kernel.job", job_id),
        details={"name": name, "queued_as": str(anew)},
        request=request,
    )
    await db.commit()
    return {"state": "queued", "id": str(anew)}


@router.delete(JOB, status_code=204)
async def discard_job(
    request: Request,
    job_id: Annotated[uuid.UUID, Path(alias="id")],
    user: User = Depends(require_permission(JOBS)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Removes a failed job for good."""
    job = await _dead_held(db, job_id)
    name = job.name
    await db.execute(delete(Job).where(Job.id == job_id))
    audit.record(
        db,
        "kernel.job.discarded",
        actor=user.id,
        target=("kernel.job", job_id),
        details={"name": name},
        request=request,
    )
    await db.commit()
    return Response(status_code=204)

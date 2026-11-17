"""The kernel's own routes, at /api/kernel: the health check, the modules on,
the staff's audit log (decision 0037), each person's notices (decision 0038),
and moderation: reports, the queue, actions, time-outs and the moderators'
log (decision 0039)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    field_validator,
    model_validator,
)
from sqlalchemy import ColumnElement, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit, moderation, notifications
from kernel.access import public
from kernel.auth import sessions
from kernel.auth.dependencies import current_user, require_permission, signed_in
from kernel.auth.models import User
from kernel.db import get_db
from kernel.errors import Problem
from kernel.models import AuditEvent
from kernel.ratelimit import rate_limit
from kernel.version import __version__

log = logging.getLogger(__name__)

router = APIRouter(tags=["kernel"])


@router.get("/health", dependencies=[Depends(public)])
async def health(request: Request) -> JSONResponse:
    """For the host's health check: 200 while the database answers, else 503."""
    database = request.app.state.database
    try:
        async with database.sessions() as session:
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as error:
        log.error("health check: the database didn't answer (%s)", type(error).__name__)
        return JSONResponse(
            {"status": "unavailable", "version": __version__, "database": "unreachable"},
            status_code=503,
        )
    return JSONResponse({"status": "ok", "version": __version__, "database": "ok"})


@router.get("/modules", dependencies=[Depends(public)])
async def modules_on(request: Request) -> dict[str, Any]:
    """The modules on, for the web shell (`useModuleEnabled`). Modules that are
    off aren't named: a visitor learns nothing of what the site lacks."""
    registry = request.app.state.modules
    return {"on": sorted(await registry.current(request.app.state.database.sessions))}


# --- the staff's audit log (SPEC.md 14.10) ---------------------------------------------


def _invalid(name: str, message: str) -> Problem:
    return Problem(
        "kernel.invalid_request",
        422,
        "Some of what was sent isn't valid.",
        errors={name: [message]},
    )


def _utc(moment: datetime) -> datetime:
    """A time sent without a zone is UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _named(value: str) -> bool:
    return len(value) <= audit.MAX_NAME and audit.NAME.fullmatch(value) is not None


@router.get("/admin/audit", dependencies=[Depends(require_permission("auth.audit.read"))])
async def audit_log(
    db: AsyncSession = Depends(get_db),
    actor: uuid.UUID | None = None,
    subject: uuid.UUID | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """Every module's entries, newest first, in pages: by who did it
    (`actor`), whom it concerns (`subject`), the action (a name, or a prefix
    ending in a dot such as `blog.`), the target, and from `since` up to
    `until`."""
    where: list[ColumnElement[bool]] = []
    if actor is not None:
        where.append(AuditEvent.actor_id == actor)
    if subject is not None:
        where.append(AuditEvent.subject_id == subject)
    if action is not None:
        if len(action) <= audit.MAX_NAME and audit.PREFIX.fullmatch(action):
            where.append(AuditEvent.action.startswith(action, autoescape=True))
        elif _named(action):
            where.append(AuditEvent.action == action)
        else:
            raise _invalid("action", "An action's name, or a prefix ending in a dot.")
    if target_type is not None:
        if not _named(target_type):
            raise _invalid("target_type", "A target's kind: <owner>.<entity>, lowercase.")
        where.append(AuditEvent.target_type == target_type)
    if target_id is not None:
        if target_type is None:
            raise _invalid("target_id", "Only with target_type.")
        where.append(AuditEvent.target_id == target_id)
    if since is not None:
        where.append(AuditEvent.at >= _utc(since))
    if until is not None:
        where.append(AuditEvent.at < _utc(until))
    page = await audit.read(db, where=where, cursor=cursor, limit=limit)
    return {"items": [audit.item(entry) for entry in page.entries], "next_cursor": page.next}


# --- each person's notices (kernel.notifications, decision 0038) ------------------------


async def _modules_on(request: Request) -> frozenset[str]:
    on: frozenset[str] = await request.app.state.modules.current(
        request.app.state.database.sessions
    )
    return on


@router.get("/notifications")
async def notices(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The person's notices, newest first, in pages, and how many are unread."""
    return await notifications.listed(db, user.id, cursor=cursor, limit=limit)


class ReadNotices(BaseModel):
    """`{ids: [...]}` (1 to 100 of the person's notices) or `{all: true}`."""

    model_config = ConfigDict(strict=True, extra="forbid")

    ids: list[str] | None = None
    all: StrictBool | None = None

    @model_validator(mode="after")
    def _one(self) -> ReadNotices:
        if (self.ids is None) == (self.all is None) or self.all is False:
            raise ValueError("Send either ids or all: true.")
        if self.ids is not None and not 1 <= len(self.ids) <= 100:
            raise ValueError("Send 1 to 100 ids.")
        return self


@router.post("/notifications/read", status_code=204)
async def read_notices(
    body: ReadNotices, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Marks the person's own notices read; anyone else's id changes nothing."""
    ids = None
    if body.ids is not None:
        try:
            ids = [uuid.UUID(value) for value in body.ids]
        except ValueError:
            raise _invalid("ids", "Each id is a notice's id.") from None
    await notifications.mark_read(db, user.id, ids)
    return Response(status_code=204)


class Choice(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    in_site: StrictBool
    email: StrictBool


class Choices(RootModel[dict[str, Choice]]):
    """`{"<key>": {in_site, email}, ...}`, strict as every body (SPEC 7)."""

    model_config = ConfigDict(strict=True)


@router.get("/notifications/preferences")
async def notice_preferences(
    request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Every key of the modules on, with the person's choice for it."""
    on = await _modules_on(request)
    return {"items": await notifications.preferences(db, user.id, on)}


@router.put("/notifications/preferences")
async def choose_notices(
    request: Request,
    body: Choices,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Saves the person's choices for the keys sent; 422 for a key of no module on."""
    on = await _modules_on(request)
    changes = {key: (choice.in_site, choice.email) for key, choice in body.root.items()}
    await notifications.choose(db, user.id, changes, on)
    return {"items": await notifications.preferences(db, user.id, on)}


@router.get(
    notifications.UNSUBSCRIBE_API.removeprefix("/api/kernel"), dependencies=[Depends(public)]
)
async def unsubscribe_link(token: str = "", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """What the link would turn off, changing nothing: link scanners open links."""
    return await notifications.looked_up(db, token)


@router.post(
    notifications.UNSUBSCRIBE_API.removeprefix("/api/kernel"), dependencies=[Depends(public)]
)
async def unsubscribe(token: str = "", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """One click (RFC 8058): email off for the link's key. No session and no
    Origin needed (security.SameOriginWrites lets it through): the token is the proof."""
    await notifications.unsubscribe(db, token)
    return {"email": False}


# --- moderation (kernel.moderation, decision 0039) ----------------------------------------

Reason = Literal[
    "spam", "harassment", "hate", "sexual", "violence", "self_harm", "illegal", "other"
]
ACT = "kernel.moderation.act"
#: How recent a sign-in a ban needs: suspending's step-up (14.4, 14.7).
STEP_UP = timedelta(minutes=10)


def _no_nul(value: str | None) -> str | None:
    """Postgres can't hold a NUL; refused here, it's a 422 rather than the
    service's ValueError as a 500 (Codex on #71)."""
    if value is not None and chr(0) in value:
        raise ValueError("Text can't hold a NUL character.")
    return value


class Target(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    type: str = Field(min_length=1, max_length=moderation.MAX_ID)
    id: str = Field(min_length=1, max_length=moderation.MAX_ID)

    _plain = field_validator("type", "id")(_no_nul)


class Report(BaseModel):
    """`{target: {type, id}, reason, note?}`."""

    model_config = ConfigDict(strict=True, extra="forbid")

    target: Target
    reason: Reason
    note: str | None = Field(default=None, max_length=moderation.MAX_NOTE)

    _plain = field_validator("note")(_no_nul)


@router.post(
    "/moderation/reports",
    status_code=202,
    dependencies=[
        Depends(current_user),
        Depends(rate_limit(moderation.REPORTS_PER_HOUR, key="account")),
    ],
)
async def report(
    request: Request,
    body: Report,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reports a thing a module lets people report; the same answer for a
    first report and a repeat. 404 for no such thing, or one of a module off."""
    if user.email_verified_at is None:
        raise Problem("auth.email_unverified", 403, "Verify your email address first.")
    found = moderation.named(body.target.type)
    if found is None or found.owner not in await _modules_on(request):
        raise moderation.no_target()
    await moderation.report(
        db, (body.target.type, body.target.id), reporter=user.id, reason=body.reason, note=body.note
    )
    await db.commit()
    return {}


@router.get("/admin/moderation/cases", dependencies=[Depends(require_permission(ACT))])
async def cases(
    db: AsyncSession = Depends(get_db),
    status: str = "open",
    kind: str | None = None,
    source: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The queue, the latest report first, in pages: by status (`open` by
    default, `actioned`, `dismissed`), kind and source."""
    if status not in moderation.STATUSES:
        raise _invalid("status", f"One of {', '.join(moderation.STATUSES)}.")
    if source is not None and source not in moderation.SOURCES:
        raise _invalid("source", f"One of {', '.join(moderation.SOURCES)}.")
    if kind is not None and not moderation.KIND.fullmatch(kind):
        raise _invalid("kind", "A kind: <module id>.<entity>, lowercase.")
    return await moderation.listed(
        db, status=status, kind=kind, source=source, cursor=cursor, limit=limit
    )


@router.get("/admin/moderation/cases/{case_id}", dependencies=[Depends(require_permission(ACT))])
async def one_case(case_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """A case with every report on it."""
    return await moderation.case(db, case_id)


class Action(BaseModel):
    """`{action, reason?, note?, minutes?}`: a reason for all but dismiss,
    minutes for a time-out."""

    model_config = ConfigDict(strict=True, extra="forbid")

    action: str
    reason: str | None = None
    note: str | None = None
    minutes: int | None = None


@router.post("/admin/moderation/cases/{case_id}/actions")
async def act(
    request: Request,
    case_id: uuid.UUID,
    body: Action,
    user: User = Depends(require_permission(ACT)),
    resumed: sessions.Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Acts on an open case and closes it; answers the case. A ban suspends
    the account, so it needs a recent sign-in, as suspending does (14.7;
    CodeRabbit on #71)."""
    if body.action == "ban" and not sessions.recent(resumed.session, within=STEP_UP):
        raise Problem("auth.step_up_required", 403, "Confirm it's you to continue.")
    await moderation.act(
        db,
        case_id,
        body.action,
        actor=user,
        reason=body.reason,
        note=body.note,
        minutes=body.minutes,
        on=await _modules_on(request),
    )
    await db.commit()
    return await moderation.case(db, case_id)


class TimeOut(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    minutes: int
    reason: str


TIME_OUT = "/admin/moderation/people/{user_id}/time-out"


@router.put(TIME_OUT)
async def time_out(
    user_id: uuid.UUID,
    body: TimeOut,
    user: User = Depends(require_permission(ACT)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stops a member posting without a case (live chat); answers when it ends."""
    until = await moderation.time_out(
        db, user_id, actor=user, minutes=body.minutes, reason=body.reason
    )
    await db.commit()
    return {"until": until.isoformat()}


@router.delete(TIME_OUT, status_code=204)
async def lift_time_out(
    user_id: uuid.UUID,
    user: User = Depends(require_permission(ACT)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Lets the person post again."""
    await moderation.lift_time_out(db, user_id, actor=user)
    await db.commit()
    return Response(status_code=204)


@router.get("/admin/moderation/log", dependencies=[Depends(require_permission(ACT))])
async def moderation_log(
    db: AsyncSession = Depends(get_db),
    subject: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """The moderators' slice of the audit log: moderation and suspensions,
    newest first, with no address or browser (decision 0037's narrower view)."""
    where: list[ColumnElement[bool]] = [moderation.LOGGED]
    if subject is not None:
        where.append(AuditEvent.subject_id == subject)
    page = await audit.read(db, where=where, cursor=cursor, limit=limit)
    return {
        "items": [moderation.log_item(entry) for entry in page.entries],
        "next_cursor": page.next,
    }

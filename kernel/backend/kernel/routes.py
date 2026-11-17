"""The kernel's own routes, at /api/kernel: the health check, the modules on,
and the staff's audit log (decision 0037)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import ColumnElement, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import audit
from kernel.access import public
from kernel.auth.dependencies import require_permission
from kernel.db import get_db
from kernel.errors import Problem
from kernel.models import AuditEvent
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

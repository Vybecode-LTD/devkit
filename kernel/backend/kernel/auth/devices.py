"""The account's signed-in devices at /api/auth (SPEC.md 14.5;
docs/contracts/auth-api.md; K4.5). The account page lists them, with a
sign-out for each and "sign out everywhere else" (VybeSite `SignedInDevices`).

- **`GET /sessions?cursor=&limit=`:** the account's sessions that still
  count, the most recently seen first, this one marked `current`, in pages
  (SPEC 7: `limit` 1 to 100, 50 by default; `{items, next_cursor}`).
  `location` is null while the site has no way to place a browser.
- **`DELETE /sessions/{id}`:** that session ends at once. Ending this one is
  signing out: the cookie is cleared and the device cookie stays, as at
  `POST /sign-out`. An id that isn't one of the account's sessions still
  counting answers 404 `auth.session_not_found`, another account's included,
  so nobody learns whether an id exists.
- **`POST /sessions/sign-out-others`:** every other session ends; this one
  stays.

None asks for step-up: ending a session only ever takes access away, and the
owner of a stolen session needs these at once. Each write locks the account
row first (decision 0021) and looks at it again, so a reset or a password
change that ended this session meanwhile wins, and this answers 401.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from kernel.auth import accounts, audit, sessions
from kernel.auth.answers import Devices
from kernel.auth.dependencies import current_user, lifetimes_of, signed_in, supersede
from kernel.auth.models import Session
from kernel.auth.sessions import Resumed
from kernel.db import get_db
from kernel.errors import Problem

router = APIRouter()

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_CURSOR = re.compile(r"([0-9]{1,19})\.([0-9a-f]{32})")


def _cursor_of(row: Session) -> str:
    micros = (row.last_seen_at - _EPOCH) // timedelta(microseconds=1)
    return f"{micros}.{row.id.hex}"


def _after(cursor: str) -> tuple[datetime, uuid.UUID]:
    found = _CURSOR.fullmatch(cursor)
    try:
        if found is None:
            raise ValueError(cursor)
        return _EPOCH + timedelta(microseconds=int(found[1])), uuid.UUID(hex=found[2])
    except (ValueError, OverflowError):
        raise Problem(
            "kernel.invalid_request",
            422,
            "Some of what was sent isn't valid.",
            errors={"cursor": ["Not a page of your devices."]},
        ) from None


def view(row: Session, *, current: bool) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "device_label": row.device_label,
        "location": row.location or None,
        "started_at": row.started_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
        "current": current,
    }


@router.get("/sessions", dependencies=[Depends(current_user)], response_model=Devices)
async def list_sessions(
    request: Request,
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    found = await sessions.live_page(
        db,
        resumed.user,
        staff=resumed.staff,
        after=_after(cursor) if cursor is not None else None,
        limit=limit,
        lifetimes=lifetimes_of(request),
    )
    page = found[:limit]
    return {
        "items": [view(row, current=row.id == resumed.session.id) for row in page],
        "next_cursor": _cursor_of(page[-1]) if len(found) > limit else None,
    }


@router.delete("/sessions/{id}", dependencies=[Depends(current_user)], status_code=204)
async def end_session(
    session_id: Annotated[uuid.UUID, Path(alias="id")],
    request: Request,
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, resumed.user.id, resumed.session.id)
    row = await db.scalar(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    live = row is not None and sessions.is_live(
        row, user, staff=resumed.staff, lifetimes=lifetimes_of(request)
    )
    if not live:
        await db.rollback()
        raise Problem("auth.session_not_found", 404, "That device isn't signed in.")
    await sessions.end(db, user, session_id)
    response = Response(status_code=204)
    if session_id == resumed.session.id:
        audit.record(db, request, "auth.sign_out", "success", actor=user.id, subject=user.id)
        await db.commit()
        supersede(request)  # a token this request was given dies with the session
        sessions.clear_session_cookie(response)
        return response
    audit.record(
        db,
        request,
        "auth.session_ended",
        "success",
        actor=user.id,
        subject=user.id,
        details={"reason": "signed_out", "session": str(session_id)},
    )
    await db.commit()
    return response


@router.post("/sessions/sign-out-others", dependencies=[Depends(current_user)], status_code=204)
async def sign_out_others(
    request: Request,
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, resumed.user.id, resumed.session.id)
    ended = await sessions.end_others(db, user, resumed.session.id)
    audit.record(
        db,
        request,
        "auth.session_ended",
        "success",
        actor=user.id,
        subject=user.id,
        details={"reason": "signed_out_others", "ended": ended},
    )
    await db.commit()
    return Response(status_code=204)

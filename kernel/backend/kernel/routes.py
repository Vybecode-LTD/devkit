"""The kernel's own routes, at /api/kernel. Staff routes arrive with auth (K2)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from kernel.access import public
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

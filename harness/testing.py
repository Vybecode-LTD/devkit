"""The harness's test support: HTTP routes the contract suite drives.

Mounted only when HARNESS_TEST_SUPPORT=1, and only by the harness: a site
never has these routes (docs/contracts/auth-api.md, "The harness's test
support"). They let a suite written against HTTP alone reset counts, read
captured mail, move the clock and make accounts, so the same suite can test
a TypeScript port.

Built: reset, clock, routes and breached (the fake breach lookup's list,
which K2's password checks read from `app.state.breached`). Still to come
with K2 and K3: users, mail, oauth/grant, jobs/run, delete-hooks.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel, Field
from sqlalchemy import delete

from harness.registry import discover
from kernel import clock, create_app
from kernel.access import needs_step_up, public, undeclared
from kernel.auth.models import User
from kernel.config import KernelConfig
from kernel.ratelimit import RateLimiter

router = APIRouter(dependencies=[Depends(public)])


class Advance(BaseModel):
    advance: float = Field(gt=0)


class Breached(BaseModel):
    passwords: list[str]


class Reset(BaseModel):
    #: Also delete every account (and, by cascade, its sessions, factors and
    #: roles), for a test whose precondition is "no one else", such as the
    #: last owner. The suite's other tests keep theirs: they make their own.
    accounts: bool = False


@router.post("/reset", status_code=204)
async def reset(request: Request, body: Reset | None = None) -> Response:
    limiter: RateLimiter = request.app.state.limiter
    await limiter.reset()
    clock.reset()
    request.app.state.breached = set()
    if body is not None and body.accounts:
        async with request.app.state.database.sessions() as session:
            await session.execute(delete(User))
            await session.commit()
    return Response(status_code=204)


@router.post("/breached", status_code=204)
async def breached(body: Breached, request: Request) -> Response:
    """The fake breach lookup reports these passwords as breached until the
    next reset; it knows of no others, so the suite never goes online."""
    request.app.state.breached = set(request.app.state.breached) | set(body.passwords)
    return Response(status_code=204)


@router.post("/clock", status_code=204)
async def move_clock(body: Advance) -> Response:
    clock.advance(body.advance)
    return Response(status_code=204)


@router.get("/routes")
async def routes(request: Request) -> dict[str, Any]:
    """The route audit's list, then every admin route (a path segment `admin`)
    and every step-up route, each method as `METHOD /path/{template}`."""
    app: FastAPI = request.app
    admin: set[str] = set()
    step_up: set[str] = set()
    for context in iter_route_contexts(app.routes):
        path = context.path or ""
        if not isinstance(context.original_route, APIRoute) or not path.startswith("/api/"):
            continue
        entries = {f"{method} {path}" for method in context.methods or ()}
        if "admin" in path.split("/"):
            admin |= entries
        if needs_step_up(context.dependant):
            step_up |= entries
    return {"undeclared": undeclared(app), "admin": sorted(admin), "step_up": sorted(step_up)}


def enabled() -> bool:
    return os.environ.get("HARNESS_TEST_SUPPORT") == "1"


def build_test_app(database_url: str | None = None) -> FastAPI:
    """The harness's app with the test-support routes at /api/_test, on
    `database_url` when given (else DATABASE_URL)."""
    if not enabled():
        raise RuntimeError("HARNESS_TEST_SUPPORT=1 is needed to mount the test-support routes.")
    config = KernelConfig(database_url=database_url) if database_url else KernelConfig()
    app = create_app(modules=discover(), config=config)
    app.state.breached = set()
    app.include_router(router, prefix="/api/_test")
    return app

"""The harness's test support: HTTP routes the contract suite drives.

Mounted only when HARNESS_TEST_SUPPORT=1, and only by the harness: a site
never has these routes (docs/contracts/auth-api.md, "The harness's test
support"). They let a suite written against HTTP alone reset counts, read
captured mail, move the clock and make accounts, so the same suite can test
a TypeScript port.

Routes still to come with K2 and K3: users, mail, oauth/grant, jobs/run,
delete-hooks.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel, Field

from harness.registry import discover
from kernel import clock, create_app
from kernel.access import public, undeclared
from kernel.config import KernelConfig
from kernel.ratelimit import RateLimiter

router = APIRouter(dependencies=[Depends(public)])


class Advance(BaseModel):
    advance: float = Field(gt=0)


@router.post("/reset", status_code=204)
async def reset(request: Request) -> Response:
    limiter: RateLimiter = request.app.state.limiter
    await limiter.reset()
    clock.reset()
    return Response(status_code=204)


@router.post("/clock", status_code=204)
async def move_clock(body: Advance) -> Response:
    clock.advance(body.advance)
    return Response(status_code=204)


@router.get("/routes")
async def routes(request: Request) -> dict[str, Any]:
    app: FastAPI = request.app
    admin = sorted(
        {
            context.path or ""
            for context in iter_route_contexts(app.routes)
            if isinstance(context.original_route, APIRoute)
            and "/admin" in (context.path or "")
            and "GET" in (context.methods or ())
            and "{" not in (context.path or "")
        }
    )
    return {"undeclared": undeclared(app), "admin": admin}


def enabled() -> bool:
    return os.environ.get("HARNESS_TEST_SUPPORT") == "1"


def build_test_app(database_url: str | None = None) -> FastAPI:
    """The harness's app with the test-support routes at /api/_test, on
    `database_url` when given (else DATABASE_URL)."""
    if not enabled():
        raise RuntimeError("HARNESS_TEST_SUPPORT=1 is needed to mount the test-support routes.")
    config = KernelConfig(database_url=database_url) if database_url else KernelConfig()
    app = create_app(modules=discover(), config=config)
    app.include_router(router, prefix="/api/_test")
    return app

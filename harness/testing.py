"""The harness's test support: HTTP routes the contract suite drives.

Mounted only when HARNESS_TEST_SUPPORT=1, and only by the harness: a site
never has these routes (docs/contracts/auth-api.md, "The harness's test
support"). They let a suite written against HTTP alone reset counts, read
captured mail, move the clock and make accounts, so the same suite can test
a TypeScript port.

The harness's sign-up mode is open, and its breach lookup is a fake that
answers Have I Been Pwned's range API from `app.state.breached`, so the suite
never goes online and the real lookup's parsing still runs.

Built: reset, clock, routes, breached (the fake breach lookup's list), mail (what
the app's mailer was handed, kept by a `CapturingMailer` behind the same
checks a site's adapter gets) and users (accounts made without judging
their passwords). Still to come with K2 and K3: oauth/grant, jobs/run,
delete-hooks.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import pyotp
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from harness.registry import discover
from kernel import clock, create_app, crypto
from kernel.access import needs_step_up, public, undeclared
from kernel.auth.accounts import normal_email
from kernel.auth.models import Role, Totp, User, UserRole
from kernel.auth.passwords import normal
from kernel.config import KernelConfig
from kernel.email import CapturingMailer
from kernel.errors import Problem
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
    _captured(request).clear()
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


def _captured(request: Request) -> CapturingMailer:
    captured: CapturingMailer = request.app.state.captured_mail
    return captured


@router.get("/mail")
async def mail(to: str, request: Request) -> dict[str, list[dict[str, str]]]:
    """What the app's mailer was handed for `to`, oldest first."""
    return {
        "messages": [
            {"to": message.to, "subject": message.subject, "text": message.text}
            for message in _captured(request).to(to)
        ]
    }


class NewUser(BaseModel):
    email: str = Field(max_length=320)
    password: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["member"])
    verified: bool = False
    totp: bool = False


@router.post("/users", status_code=201)
async def users(body: NewUser, request: Request) -> dict[str, str]:
    """An account, made without judging its password (the suite needs ones a
    person couldn't choose): its roles (member by default), a verified
    address, and a confirmed TOTP whose secret comes back."""
    passwords = request.app.state.passwords
    async with request.app.state.database.sessions() as db:
        unknown = sorted(set(body.roles) - set(await db.scalars(select(Role.id))))
        if unknown:
            raise Problem("harness.unknown_role", 422, f"There's no role {', '.join(unknown)}.")
        user = User(
            email=body.email,
            email_normal=normal_email(body.email),
            password_hash=await passwords.hash(body.password) if body.password else None,
            email_verified_at=clock.now() if body.verified else None,
        )
        db.add(user)
        await db.flush()
        for role in body.roles:
            db.add(UserRole(user_id=user.id, role_id=role))
        made = {"id": str(user.id)}
        if body.totp:
            secret = pyotp.random_base32()
            db.add(
                Totp(user_id=user.id, secret_sealed=crypto.seal(secret), confirmed_at=clock.now())
            )
            made["totp_secret"] = secret
        await db.commit()
    return made


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
    config = (
        KernelConfig(database_url=database_url, sign_up_mode="open")
        if database_url
        else KernelConfig(sign_up_mode="open")
    )
    captured = CapturingMailer()

    async def fake_range(prefix: str) -> str:
        """The range API's answer, from the passwords given to /breached."""
        lines = []
        for password in app.state.breached:
            digest = hashlib.sha1(normal(password).encode(), usedforsecurity=False)
            hexed = digest.hexdigest().upper()
            if hexed.startswith(prefix):
                lines.append(f"{hexed[5:]}:1")
        return "\n".join(lines)

    app = create_app(modules=discover(), config=config, mailer=captured, breach_lookup=fake_range)
    app.state.captured_mail = captured
    app.state.breached = set()
    app.include_router(router, prefix="/api/_test")
    return app

"""Sign-up and email verification at /api/auth (SPEC.md 14.6, 14.7 and 14.10;
docs/contracts/auth-api.md; decision 0020).

**The site's mode** (`SIGN_UP_MODE`) comes first: closed answers 403
`auth.sign_up_closed`, invite-only 403 `auth.invite_required`. Until invites
arrive (K2's API keys and invites) no invite is valid, so an invite-only site
takes no sign-ups at all. Public sign-up makes only `member` accounts (14.1).

**Nothing says whether an account exists.** The password is judged before the
address is looked at, and either way one Argon2 hash is spent and one audit
row written. A new address gets an unverified account and a link to
`/auth/verify?token=…`. An address that has an account gets a notice instead,
at the address as the account keeps it, and its account is left exactly as
it was. Both answer 202
`{"status": "check_email"}`, and the mail goes out after the answer. Two
sign-ups for one new address at once make one account: the insert skips a
taken address, and the later one is sent the notice.

**Limits:** 5 sign-ups per IP an hour (14.6). Past 3 sign-up mails to one
address in 15 minutes, a sign-up is answered the same and sends no notice, so
the form can't be used to flood someone's inbox. An account's verification
link counts toward the 3 but always goes out: there is only one per account,
and notices from sign-ups racing it mustn't crowd it out.

**Verifying** takes the link's token once, within 24 hours, and only while
the account still has the address it was sent to. It signs nobody in.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import cast
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock
from kernel.access import public
from kernel.auth import accounts, audit, tokens
from kernel.auth.models import User, UserRole
from kernel.auth.passwords import Passwords, refusal
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import MAX_ADDRESS, Mailer, is_address
from kernel.errors import Problem
from kernel.ratelimit import RateLimiter, rate_limit

log = logging.getLogger(__name__)

router = APIRouter()

SIGN_UPS_PER_IP = "5/1h"
SIGN_UP_MAILS = "3/15m"
VERIFY_LIFETIME_HOURS = 24
_MAIL_SCOPE = "auth.sign_up.mail"
_VERIFY = "verify_email"
_MEMBER = "member"


class SignUp(BaseModel):
    email: str = Field(max_length=MAX_ADDRESS + 64)
    password: str = Field(max_length=1024)
    invite: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def _one_address(cls, value: str) -> str:
        value = value.strip()
        if not is_address(value):
            raise ValueError("Enter one email address, like name@example.com.")
        return value


class VerifyEmail(BaseModel):
    token: str = Field(max_length=128)


def _site(config: KernelConfig) -> str:
    return config.site_url.rstrip("/")


def _context(config: KernelConfig, email: str) -> tuple[str, ...]:
    """What a guesser starts from: the site's name and host, and the address."""
    host = urlsplit(config.site_url).hostname or ""
    return (config.site_name, host, host.split(".")[0], email, email.split("@")[0])


@router.post(
    "/sign-up",
    status_code=202,
    dependencies=[Depends(public), Depends(rate_limit(SIGN_UPS_PER_IP))],
)
async def sign_up(
    body: SignUp,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    config: KernelConfig = request.app.state.config
    if config.sign_up_mode == "closed":
        raise Problem("auth.sign_up_closed", 403, "This site isn't taking new accounts.")
    if config.sign_up_mode == "invite":
        raise Problem(
            "auth.invite_required", 403, "This site takes new accounts by invitation only."
        )
    email, normal = body.email, accounts.normal_email(body.email)
    reason = await refusal(
        body.password, _context(config, email), lookup=request.app.state.breach_lookup
    )
    if reason is not None:
        raise Problem("auth.password_rejected", 422, reason)
    passwords = cast(Passwords, request.app.state.passwords)
    # Spent for an address that has an account too, so the time says nothing.
    hashed = await passwords.hash(body.password)
    made: uuid.UUID | None = await db.scalar(
        insert(User)
        .values(email=email, email_normal=normal, password_hash=hashed)
        .on_conflict_do_nothing(index_elements=[User.email_normal])
        .returning(User.id)
    )
    to = email
    if made is None:
        existing = await accounts.by_email(db, normal)
        audit.record(
            db,
            request,
            "auth.sign_up",
            "existing",
            subject=existing.id if existing is not None else None,
        )
        subject, text = _notice(config)
        if existing is not None:
            to = existing.email  # the owner's own form of it
    else:
        db.add(UserRole(user_id=made, role_id=_MEMBER))
        token = await tokens.issue(
            db, _VERIFY, made, normal, lifetime=timedelta(hours=VERIFY_LIFETIME_HOURS)
        )
        audit.record(db, request, "auth.sign_up", "success", actor=made, subject=made)
        subject, text = _verify_mail(config, token)
    await db.commit()
    limiter = cast(RateLimiter, request.app.state.limiter)
    allowed = await limiter.hit(SIGN_UP_MAILS, _MAIL_SCOPE, normal)
    if allowed or made is not None:
        background.add_task(_send, request.app.state.mailer, to, subject, text)
    return {"status": "check_email"}


def _verify_mail(config: KernelConfig, token: str) -> tuple[str, str]:
    return (
        f"Confirm your email for {config.site_name}",
        f"Welcome to {config.site_name}. Confirm this is your address by opening this link "
        f"within {VERIFY_LIFETIME_HOURS} hours:\n\n"
        f"{_site(config)}/auth/verify?token={token}\n\n"
        "If you didn't make an account, ignore this message: nothing more will be sent.\n",
    )


def _notice(config: KernelConfig) -> tuple[str, str]:
    return (
        f"Sign-up attempt on {config.site_name}",
        f"Someone tried to make a {config.site_name} account with this address, which "
        "already has one, so no new account was made.\n\n"
        f"If it was you, sign in at {_site(config)}/sign-in instead, where you can also "
        "reset your password if you've forgotten it.\n\n"
        "If it wasn't you, there's nothing to do.\n",
    )


async def _send(mailer: Mailer, to: str, subject: str, text: str) -> None:
    try:
        await mailer.send(to, subject, text)
    except Exception as error:
        log.warning("A sign-up mail wasn't sent (%s).", type(error).__name__)


@router.post("/verify-email", dependencies=[Depends(public)])
async def verify_email(
    body: VerifyEmail, request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    redeemed = await tokens.redeem(db, _VERIFY, body.token)
    user = (
        await db.get(User, redeemed.user_id, populate_existing=True)
        if redeemed is not None
        else None
    )
    if (
        redeemed is None
        or user is None
        or user.status == "deleted"
        or user.email_normal != redeemed.email_normal
    ):
        await db.rollback()
        raise Problem(
            "auth.token_invalid",
            400,
            "This link has expired or has already been used.",
        )
    if user.email_verified_at is None:
        user.email_verified_at = clock.now()
    audit.record(db, request, "auth.email_verified", "success", actor=user.id, subject=user.id)
    await db.commit()
    return {"status": "verified"}

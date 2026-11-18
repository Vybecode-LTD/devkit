"""Changing an account's address at /api/auth (SPEC.md 14.6 and 14.7;
docs/contracts/auth-api.md; decision 0024).

**Asking** (`POST /email/change`, step-up) answers 202 `{"status":
"check_email"}` for any address but the account's own. A free address is
mailed a link to `/auth/email?token=…`, valid 24 hours; an address that has
an account is sent a notice instead, so the answer says nothing about it.
The account keeps its address until the link is used. 3 requests per
account in 15 minutes; a request within 60 seconds of the last link (by
`kernel.clock`) answers the same and sends nothing; past 3 mails to one
address in 15 minutes, nothing more goes to it. A new link voids the last.
Every request answers no sooner than the floor (`floor.py`).

**Confirming** (`POST /email/confirm`): the account takes the new address,
marked verified, since the link proved the inbox, and the old address is
mailed an undo link to `/auth/email/undo?token=…`, valid 7 days. The new
address must still be free, and the account still able to sign in. It
signs nobody in.

**Undoing** (`POST /email/undo`) puts the old address back, with its
verification as it was, ends every session, and voids every live way in sent
since: sign-in codes and links, reset links, second-factor challenges,
pending change links, and the undo links of later changes. Earlier undo
links always stay: each restores the address it was sent to, so whoever
changed the address can neither change it again nor undo their own change
to cut the owner off. The old address must still be free. A notice follows.

**A change link is bound to the session epoch** it was asked under: a
reset, a password change, a second-factor reset or a suspension in
between makes it refuse, so whoever asked with the old password can't
confirm it after the owner has taken the account back.

**One purpose, two kinds.** Both links are `email_change` tokens, told apart
by `data.kind` (`confirm` or `undo`); one used at the wrong route is refused
and left as it was. Every route locks the account before a link's row
(decision 0021).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import clock, events
from kernel.access import public
from kernel.auth import accounts, audit, floor, mails, sessions, tokens
from kernel.auth.answers import CheckEmail, EmailChanged, EmailRestored
from kernel.auth.dependencies import require_recent_auth
from kernel.auth.models import Token, User
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import MAX_ADDRESS, is_address, queue_message
from kernel.errors import Problem
from kernel.ratelimit import RateLimiter, too_many

log = logging.getLogger(__name__)

router = APIRouter()

CHANGES_PER_ACCOUNT = "3/15m"
MAILS_PER_ADDRESS = "3/15m"
CHANGE_LIFETIME = timedelta(hours=24)
UNDO_LIFETIME = timedelta(days=7)
RESEND_WAIT = timedelta(seconds=60)
_CHANGE = "email_change"
_ACCOUNT_SCOPE = "auth.email_change.account"
_MAIL_SCOPE = "auth.email_change.mail"
#: The kinds of a request still pending: a mailed change link, or the
#: unmailed trace a request for an address with an account leaves.
_PENDING = ("confirm", "notice")
#: Every way in an undo ends besides change links: what was sent or opened
#: since the change.
_ENDED = ("sign_in_code", "magic_link", "reset_password", "second_factor")


class EmailChange(BaseModel):
    model_config = ConfigDict(strict=True)

    email: str = Field(max_length=MAX_ADDRESS + 64)

    @field_validator("email")
    @classmethod
    def _one_address(cls, value: str) -> str:
        value = value.strip()
        if not is_address(value):
            raise ValueError("Enter one email address, like name@example.com.")
        return value


class EmailLink(BaseModel):
    model_config = ConfigDict(strict=True)

    token: str = Field(max_length=128)


def _token_invalid() -> Problem:
    return Problem("auth.token_invalid", 400, "This link has expired or has already been used.")


def _site(config: KernelConfig) -> str:
    return config.site_url.rstrip("/")


async def _taken(db: AsyncSession, normal: str, user_id: uuid.UUID) -> bool:
    """Whether another account has the address."""
    other = exists().where(User.email_normal == normal, User.id != user_id)
    return bool(await db.scalar(select(other)))


async def _write_address(db: AsyncSession) -> None:
    """Write the account's new address now, on its own. Another account can
    take the address between `_taken` and this write; the unique index then
    refuses it, and the route answers as for a taken address. Left to the next
    query's autoflush, the refusal would land outside any handler as a 500."""
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _token_invalid() from None


async def _void_after_undo(
    db: AsyncSession, user_id: uuid.UUID, undone_at: datetime | None
) -> None:
    """After an undo: use up the pending change links, and the undo links
    issued after this one, for changes this undo has rolled past. Earlier undo
    links stay: whoever made a later change can't cancel the owner's way back
    to the address before it by undoing their own (Codex on #45)."""
    later = Token.data["kind"].astext == "undo"
    if undone_at is not None:
        later = later & (Token.created_at > undone_at)
    await db.execute(
        update(Token)
        .where(
            Token.user_id == user_id,
            Token.purpose == _CHANGE,
            Token.used_at.is_(None),
            Token.data["kind"].astext.in_(_PENDING) | later,
        )
        .values(used_at=clock.now())
        .execution_options(synchronize_session=False)
    )


async def _void_confirms(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Use up the account's pending change links; its undo links stay."""
    await db.execute(
        update(Token)
        .where(
            Token.user_id == user_id,
            Token.purpose == _CHANGE,
            Token.used_at.is_(None),
            Token.data["kind"].astext.in_(_PENDING),
        )
        .values(used_at=clock.now())
        .execution_options(synchronize_session=False)
    )


# --- asking -------------------------------------------------------------------------


@router.post("/email/change", status_code=202, response_model=CheckEmail)
async def change_email(
    body: EmailChange,
    request: Request,
    user: User = Depends(require_recent_auth()),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    started = floor.start()
    new, normal = body.email, accounts.normal_email(body.email)
    if normal == user.email_normal:
        raise Problem("kernel.invalid_request", 422, "That is the account's address already.")
    limiter = cast(RateLimiter, request.app.state.limiter)
    key = str(user.id)
    if not await limiter.hit(CHANGES_PER_ACCOUNT, _ACCOUNT_SCOPE, key):
        raise too_many(await limiter.wait_seconds(CHANGES_PER_ACCOUNT, _ACCOUNT_SCOPE, key))
    await accounts.lock(db, user.id)  # before its token rows, as every route does
    config = cast(KernelConfig, request.app.state.config)
    action = "auth.email_change_requested"
    mail: tuple[str, str, str, str | None] | None = None  # to, subject, text, html
    if await _waiting(db, user.id):
        audit.record(db, request, action, "waiting", actor=user.id, subject=user.id)
    elif (existing := await accounts.by_email(db, normal)) is not None:
        # The same trace a free address leaves: the last link voided, and a
        # token the wait counts, never mailed and never confirmable (its kind
        # is `notice`). Otherwise the wait and the last link would tell an
        # address with an account from a free one (CodeRabbit on #45).
        await _void_confirms(db, user.id)
        await tokens.issue(
            db, _CHANGE, user.id, normal, lifetime=CHANGE_LIFETIME, data={"kind": "notice"}
        )
        audit.record(db, request, action, "taken", actor=user.id, subject=user.id)
        mail = (existing.email, *_taken_notice(config))
    else:
        await _void_confirms(db, user.id)
        token = await tokens.issue(
            db,
            _CHANGE,
            user.id,
            normal,
            lifetime=CHANGE_LIFETIME,
            data={"kind": "confirm", "email": new, "epoch": user.session_epoch},
        )
        audit.record(db, request, action, "success", actor=user.id, subject=user.id)
        mail = (new, *_confirm_mail(config, token))
    if mail is not None and await limiter.hit(
        MAILS_PER_ADDRESS, _MAIL_SCOPE, accounts.normal_email(mail[0])
    ):
        await queue_message(db, *mail)
    await db.commit()
    await floor.wait_out(started)
    return {"status": "check_email"}


async def _waiting(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether a change link went out for the account within the wait."""
    recent = exists().where(
        Token.purpose == _CHANGE,
        Token.user_id == user_id,
        Token.data["kind"].astext.in_(_PENDING),
        Token.created_at > clock.now() - RESEND_WAIT,
    )
    return bool(await db.scalar(select(recent)))


# --- confirming ---------------------------------------------------------------------


@router.post("/email/confirm", dependencies=[Depends(public)], response_model=EmailChanged)
async def confirm_email_change(
    body: EmailLink,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    owner = await tokens.owner_of(db, _CHANGE, body.token)
    if owner is None:
        await db.rollback()
        raise _token_invalid()
    await accounts.lock(db, owner)  # before the link's row, as every route does
    redeemed = await tokens.redeem(db, _CHANGE, body.token)
    user = await db.get(User, owner, populate_existing=True)
    if (
        redeemed is None
        or redeemed.data.get("kind") != "confirm"
        or redeemed.email_normal is None
        or user is None
        or user.status not in accounts.SIGNS_IN
        # Asked under another epoch: a reset, a password change, a
        # second-factor reset or a suspension has come between (Codex on #45).
        or redeemed.data.get("epoch") != user.session_epoch
        or await _taken(db, redeemed.email_normal, user.id)
    ):
        await db.rollback()
        raise _token_invalid()
    now = clock.now()
    old_email, old_normal, old_verified = user.email, user.email_normal, user.email_verified_at
    user.email = str(redeemed.data["email"])
    user.email_normal = redeemed.email_normal
    user.email_verified_at = now
    user.email_set_at = now
    await _write_address(db)
    await events.emit(db, "auth.user.verified", events.UserVerified(user_id=user.id))
    await _void_confirms(db, user.id)
    undo = await tokens.issue(
        db,
        _CHANGE,
        user.id,
        old_normal,
        lifetime=UNDO_LIFETIME,
        data={
            "kind": "undo",
            "email": old_email,
            "verified_at": old_verified.isoformat() if old_verified else None,
        },
    )
    audit.record(db, request, "auth.email_changed", "success", actor=user.id, subject=user.id)
    config = cast(KernelConfig, request.app.state.config)
    await queue_message(db, old_email, *_undo_mail(config, undo))
    await db.commit()
    return {"status": "email_changed"}


# --- undoing ------------------------------------------------------------------------


@router.post("/email/undo", dependencies=[Depends(public)], response_model=EmailRestored)
async def undo_email_change(
    body: EmailLink,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    owner = await tokens.owner_of(db, _CHANGE, body.token)
    if owner is None:
        await db.rollback()
        raise _token_invalid()
    await accounts.lock(db, owner)  # before the link's row, as every route does
    redeemed = await tokens.redeem(db, _CHANGE, body.token)
    user = await db.get(User, owner, populate_existing=True)
    if (
        redeemed is None
        or redeemed.data.get("kind") != "undo"
        or redeemed.email_normal is None
        or user is None
        or user.status not in accounts.SIGNS_IN
        or await _taken(db, redeemed.email_normal, user.id)
    ):
        await db.rollback()
        raise _token_invalid()
    verified = redeemed.data.get("verified_at")
    user.email = str(redeemed.data["email"])
    user.email_normal = redeemed.email_normal
    user.email_verified_at = datetime.fromisoformat(verified) if verified else None
    # A fresh 7 days for the address put back, if it isn't verified (decision 0035).
    user.email_set_at = clock.now()
    await _write_address(db)
    await sessions.end_all(db, user)
    await tokens.void(db, user.id, _ENDED)
    await _void_after_undo(db, user.id, redeemed.created_at)
    audit.record(db, request, "auth.email_restored", "success", actor=user.id, subject=user.id)
    restored = user.email
    config = cast(KernelConfig, request.app.state.config)
    await queue_message(db, restored, *_restored_notice(config))
    await db.commit()
    return {"status": "email_restored"}


# --- mail ---------------------------------------------------------------------------


def _confirm_mail(config: KernelConfig, token: str) -> mails.Mail:
    return mails.rendered(
        "kernel.email_change_confirm", link=f"{_site(config)}/auth/email?token={token}"
    )


def _taken_notice(config: KernelConfig) -> mails.Mail:
    return mails.rendered("kernel.email_change_taken")


def _undo_mail(config: KernelConfig, token: str) -> mails.Mail:
    return mails.rendered(
        "kernel.email_change_undo",
        link=f"{_site(config)}/auth/email/undo?token={token}",
        days=UNDO_LIFETIME.days,
    )


def _restored_notice(config: KernelConfig) -> mails.Mail:
    return mails.rendered("kernel.email_restored")

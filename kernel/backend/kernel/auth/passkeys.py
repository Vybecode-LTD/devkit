"""Passkeys at /api/auth (SPEC.md 14.2 to 14.6; docs/contracts/auth-api.md;
decision 0028): registering, listing, renaming and removing them, signing
in with one alone, and the options for one as a second factor or at
step-up. The challenges and the checks are in `ceremonies.py`; sign-in's
second-factor step and step-up take the passkey itself (`routes.py`).

**`POST /passkeys/register/start {name}`**, step-up and a verified address
(14.3): creation options asking for a discoverable credential with user
verification, excluding the account's passkeys, with the account's id as
the user handle (16 bytes, nothing personal) and its address as the name
the authenticator shows. The challenge is bound to this session. At most 20
passkeys (409 `auth.too_many_passkeys`). **`/register/finish`** takes the
credential and checks it all again with the account held: 201 with the
passkey, an audit row and a security mail; 400 `auth.invalid_passkey` for
anything that doesn't verify.

**`GET /passkeys`**, the account's, oldest first. **`PATCH /passkeys/{id}
{name}`**, step-up: renamed, audited, no mail (a name opens nothing).
**`DELETE /passkeys/{id}`**, step-up: every removal is a second-factor
reset (the owner's answer), as removing a TOTP is: the epoch goes up, every
other session ends, this one keeps a fresh device cookie, live codes,
links, reset links and second-factor challenges are voided, and a mail
follows. An id that isn't one of the account's is 404 `auth.passkey_not_found`.

**`POST /passkeys/sign-in/start` and `/finish`**, public, 10 per IP a
minute each: request options naming no passkey (the authenticator offers
its discoverable ones) with user verification required, then the
credential signs the account in, staff too, with no second-factor step: a
verified passkey is two factors. Everything wrong gets one answer, 401
`auth.invalid_passkey`.

**`POST /sign-in/second-factor/passkey {challenge}`** and **`POST
/step-up/passkey`**: request options for the account's passkeys, user
verification preferred as a second factor and required at step-up; 409
`auth.no_passkey` for an account with none.

Options are never cached. Every route that writes an account's passkey,
token or session rows locks the account first (decisions 0021 and 0027);
the signed-in ones then look at the account and the session again
(`accounts.held`), so a reset that ended this session wins.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Annotated, Any, NoReturn, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response
from webauthn import generate_authentication_options, generate_registration_options
from webauthn.helpers import options_to_json_dict
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from kernel import clock
from kernel.access import public
from kernel.auth import accounts, audit, ceremonies, second_factor, sessions, tokens
from kernel.auth.ceremonies import AssertionCredential, RegistrationCredential
from kernel.auth.dependencies import current_user, require_recent_auth, signed_in
from kernel.auth.models import Passkey, User
from kernel.auth.routes import finish_sign_in
from kernel.auth.sessions import Resumed
from kernel.config import KernelConfig
from kernel.db import get_db
from kernel.email import Mailer
from kernel.errors import Problem
from kernel.ratelimit import rate_limit

log = logging.getLogger(__name__)

router = APIRouter()

#: Passkeys one account may hold: a bound of ours, well past what a person keeps.
MAX_PASSKEYS = 20
_NO_STORE = {"Cache-Control": "no-store"}
#: Every way in a removal ends besides sessions, as removing a TOTP does.
_ENDED = ("sign_in_code", "magic_link", "reset_password", "second_factor")
#: Control characters and Unicode's line and paragraph separators.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


class PasskeyName(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(max_length=200)

    @field_validator("name")
    @classmethod
    def _trimmed(cls, name: str) -> str:
        name = name.strip()
        if not 1 <= len(name) <= 80 or _CONTROL.search(name):
            raise ValueError("A passkey's name is 1 to 80 characters, with no line breaks.")
        return name


class ChallengeOnly(BaseModel):
    model_config = ConfigDict(strict=True)

    challenge: str = Field(max_length=128)


def _config(request: Request) -> KernelConfig:
    return cast(KernelConfig, request.app.state.config)


def _party(request: Request) -> ceremonies.RelyingParty:
    return ceremonies.relying_party(_config(request))


def _options(options: Any) -> JSONResponse:
    return JSONResponse(options_to_json_dict(options), headers=_NO_STORE)


def _invalid() -> Problem:
    return Problem("auth.invalid_passkey", 400, "That passkey couldn't be added. Try again.")


def _refused() -> Problem:
    return Problem("auth.invalid_passkey", 401, "That passkey didn't work. Try again.")


def _not_found() -> Problem:
    return Problem("auth.passkey_not_found", 404, "There's no such passkey on this account.")


def _no_passkey() -> Problem:
    return Problem("auth.no_passkey", 409, "This account has no passkey.")


def _too_many() -> Problem:
    return Problem(
        "auth.too_many_passkeys", 409, f"An account holds at most {MAX_PASSKEYS} passkeys."
    )


def _unverified() -> Problem:
    return Problem("auth.email_unverified", 403, "Verify your email address first.")


def view(passkey: Passkey) -> dict[str, Any]:
    last = passkey.last_used_at
    return {
        "id": str(passkey.id),
        "name": passkey.name,
        "created_at": passkey.created_at.isoformat(),
        "last_used_at": last.isoformat() if last is not None else None,
    }


async def _passkeys_of(db: AsyncSession, user_id: uuid.UUID) -> list[Passkey]:
    found = await db.scalars(
        select(Passkey)
        .where(Passkey.user_id == user_id)
        .order_by(Passkey.created_at, Passkey.id)
        .execution_options(populate_existing=True)
    )
    return list(found)


async def _count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await db.scalar(select(func.count()).select_from(Passkey).where(Passkey.user_id == user_id))
        or 0
    )


async def _owned(db: AsyncSession, user_id: uuid.UUID, passkey_id: uuid.UUID) -> Passkey:
    passkey = await db.scalar(
        select(Passkey)
        .where(Passkey.id == passkey_id, Passkey.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if passkey is None:
        await db.rollback()
        raise _not_found()
    return passkey


# --- registering ----------------------------------------------------------------------


@router.post("/passkeys/register/start")
async def start_registration(
    body: PasskeyName,
    request: Request,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
    if user.email_verified_at is None:
        await db.rollback()
        raise _unverified()
    held = await _passkeys_of(db, user.id)
    if len(held) >= MAX_PASSKEYS:
        await db.rollback()
        raise _too_many()
    party, challenge = _party(request), ceremonies.new_challenge()
    options = generate_registration_options(
        rp_id=party.id,
        rp_name=party.name,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.email,
        challenge=challenge,
        timeout=ceremonies.TIMEOUT_MS,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=ceremonies.descriptors(held),
    )
    await ceremonies.keep(
        db,
        ceremonies.REGISTER,
        challenge,
        user_id=user.id,
        data={"name": body.name, "session": str(resumed.session.id)},
    )
    audit.record(
        db, request, "auth.passkey_registration_started", "success", actor=user.id, subject=user.id
    )
    await db.commit()
    return _options(options)


@router.post("/passkeys/register/finish", status_code=201)
async def finish_registration(
    body: RegistrationCredential,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
    if user.email_verified_at is None:
        await db.rollback()
        raise _unverified()
    if await _count(db, user.id) >= MAX_PASSKEYS:
        await db.rollback()
        raise _too_many()
    challenge = ceremonies.answered(body.response.client_data_json)
    kept = None
    if challenge is not None:
        kept = await ceremonies.use(
            db, ceremonies.REGISTER, challenge, user_id=user.id, session_id=resumed.session.id
        )
    if challenge is None or kept is None:
        await db.rollback()
        raise _invalid()
    verified = ceremonies.registered(body, challenge, _party(request))
    taken = verified is not None and await db.scalar(
        select(Passkey.id).where(Passkey.credential_id == verified.credential_id)
    )
    if verified is None or taken:
        audit.record(db, request, "auth.passkey_added", "failure", actor=user.id, subject=user.id)
        await db.commit()  # the challenge is used up either way
        raise _invalid()
    now = clock.now()
    passkey = Passkey(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=str(kept.get("name") or "Passkey"),
        transports=[t for t in body.response.transports if t in ceremonies.TRANSPORTS],
        created_at=now,
    )
    db.add(passkey)
    await db.flush()
    audit.record(
        db,
        request,
        "auth.passkey_added",
        "success",
        actor=user.id,
        subject=user.id,
        details={"passkey": str(passkey.id)},
    )
    shown, to = view(passkey), user.email
    await db.commit()
    background.add_task(_send, request.app.state.mailer, to, *_added(_config(request), now))
    return JSONResponse(shown, status_code=201)


# --- the list, renaming and removing --------------------------------------------------


@router.get("/passkeys")
async def list_passkeys(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, list[dict[str, Any]]]:
    return {"items": [view(passkey) for passkey in await _passkeys_of(db, user.id)]}


@router.patch("/passkeys/{id}")
async def rename_passkey(
    passkey_id: Annotated[uuid.UUID, Path(alias="id")],
    body: PasskeyName,
    request: Request,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await accounts.held(db, user.id, resumed.session.id)
    passkey = await _owned(db, user.id, passkey_id)
    passkey.name = body.name
    audit.record(
        db,
        request,
        "auth.passkey_renamed",
        "success",
        actor=user.id,
        subject=user.id,
        details={"passkey": str(passkey.id)},
    )
    shown = view(passkey)
    await db.commit()
    return shown


@router.delete("/passkeys/{id}", status_code=204)
async def remove_passkey(
    passkey_id: Annotated[uuid.UUID, Path(alias="id")],
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_recent_auth()),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
    passkey = await _owned(db, user.id, passkey_id)
    await db.delete(passkey)
    audit.record(
        db,
        request,
        "auth.passkey_removed",
        "success",
        actor=user.id,
        subject=user.id,
        details={"passkey": str(passkey_id)},
    )
    await sessions.end_all_but(db, user, resumed.session)  # the second-factor reset
    await tokens.void(db, user.id, _ENDED)
    to, now = user.email, clock.now()
    await db.commit()
    response = Response(status_code=204)
    sessions.set_device_cookie(response, user)  # signed over the new epoch
    background.add_task(_send, request.app.state.mailer, to, *_removed(_config(request), now))
    return response


# --- signing in with a passkey alone --------------------------------------------------


@router.post(
    "/passkeys/sign-in/start", dependencies=[Depends(public), Depends(rate_limit("10/1m"))]
)
async def start_passkey_sign_in(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    challenge = ceremonies.new_challenge()
    options = generate_authentication_options(
        rp_id=_party(request).id,
        challenge=challenge,
        timeout=ceremonies.TIMEOUT_MS,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    await ceremonies.keep(db, ceremonies.SIGN_IN, challenge)
    await db.commit()
    return _options(options)


@router.post(
    "/passkeys/sign-in/finish", dependencies=[Depends(public), Depends(rate_limit("10/1m"))]
)
async def finish_passkey_sign_in(
    body: AssertionCredential,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    challenge = ceremonies.answered(body.response.client_data_json)
    # Used up first, whatever follows: a challenge with no account yet is no
    # account's row, so it is taken before the account's lock.
    kept = None
    if challenge is not None:
        kept = await ceremonies.use(db, ceremonies.SIGN_IN, challenge, user_id=None)
    await db.commit()
    raw_id = body.credential_id()
    owner = None
    if kept is not None and raw_id is not None:
        owner = await db.scalar(select(Passkey.user_id).where(Passkey.credential_id == raw_id))
    if challenge is None or raw_id is None or owner is None:
        await _failed_sign_in(request, db, None)
    await accounts.lock(db, owner)
    user = await db.get(User, owner, populate_existing=True)
    passkey = await db.scalar(
        select(Passkey)
        .where(Passkey.credential_id == raw_id, Passkey.user_id == owner)
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or user.status not in accounts.SIGNS_IN
        or passkey is None
        or not ceremonies.used(
            passkey,
            body,
            challenge,
            _party(request),
            require_user_verification=True,
            need_user_handle=True,
        )
    ):
        await db.rollback()
        await _failed_sign_in(request, db, owner)
    return await finish_sign_in(request, db, background, user, second_factor=True, method="passkey")


async def _failed_sign_in(
    request: Request, db: AsyncSession, subject: uuid.UUID | None
) -> NoReturn:
    audit.record(
        db, request, "auth.sign_in", "failure", subject=subject, details={"method": "passkey"}
    )
    await db.commit()
    raise _refused()


# --- options for a second factor and for step-up --------------------------------------


@router.post("/sign-in/second-factor/passkey", dependencies=[Depends(public)])
async def passkey_for_second_factor(
    body: ChallengeOnly, request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    owner = await second_factor.owner_of_challenge(db, body.challenge)
    if owner is None:
        raise Problem("auth.challenge_ended", 401, "This sign-in has ended. Start again.")
    await accounts.lock(db, owner)  # before the challenge's row
    held = await _passkeys_of(db, owner)
    if not held:
        await db.rollback()
        raise _no_passkey()
    challenge = ceremonies.new_challenge()
    if not await second_factor.expect_passkey(db, body.challenge, ceremonies.encoded(challenge)):
        await db.rollback()
        raise Problem("auth.challenge_ended", 401, "This sign-in has ended. Start again.")
    await db.commit()
    return _options(
        generate_authentication_options(
            rp_id=_party(request).id,
            challenge=challenge,
            timeout=ceremonies.TIMEOUT_MS,
            allow_credentials=ceremonies.descriptors(held),
            user_verification=UserVerificationRequirement.PREFERRED,
        )
    )


@router.post("/step-up/passkey")
async def passkey_for_step_up(
    request: Request,
    user: User = Depends(current_user),
    resumed: Resumed = Depends(signed_in),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await accounts.held(db, user.id, resumed.session.id)
    held = await _passkeys_of(db, user.id)
    if not held:
        await db.rollback()
        raise _no_passkey()
    challenge = ceremonies.new_challenge()
    await ceremonies.keep(
        db,
        ceremonies.STEP_UP,
        challenge,
        user_id=user.id,
        data={"session": str(resumed.session.id)},
    )
    await db.commit()
    return _options(
        generate_authentication_options(
            rp_id=_party(request).id,
            challenge=challenge,
            timeout=ceremonies.TIMEOUT_MS,
            allow_credentials=ceremonies.descriptors(held),
            user_verification=UserVerificationRequirement.REQUIRED,
        )
    )


# --- security mail --------------------------------------------------------------------


def _when(at: datetime) -> str:
    return f"{at.day} {at:%B %Y} at {at:%H:%M} UTC"


def _added(config: KernelConfig, at: datetime) -> tuple[str, str]:
    site = config.site_url.rstrip("/")
    return (
        f"A passkey was added to your {config.site_name} account",
        f"A passkey was added to your {config.site_name} account on {_when(at)}. It can sign "
        "in on its own.\n\n"
        "If that was you, there's nothing to do.\n\n"
        f"If it wasn't, someone is signed in to your account: reset your password now at "
        f"{site}/sign-in, which signs every device out, then remove the passkey from your "
        "account's settings.\n",
    )


def _removed(config: KernelConfig, at: datetime) -> tuple[str, str]:
    """No name in it: whoever names a passkey chooses its words."""
    site = config.site_url.rstrip("/")
    return (
        f"A passkey was removed from your {config.site_name} account",
        f"A passkey was removed from your {config.site_name} account on {_when(at)}, and "
        "every other device was signed out.\n\n"
        "If that was you, there's nothing to do.\n\n"
        f"If it wasn't, reset your password now at {site}/sign-in: that signs every device "
        "out, this one too.\n",
    )


async def _send(mailer: Mailer, to: str, subject: str, text: str) -> None:
    try:
        await mailer.send(to, subject, text)
    except Exception as error:
        log.warning("A passkey mail wasn't sent (%s).", type(error).__name__)

"""Passkey ceremonies (SPEC.md 14.2 and 14.4; decision 0028): the relying
party, the challenges, the credentials a browser sends and the checks on
them, for the routes in `passkeys.py` and for sign-in's second factor and
step-up in `routes.py`. Every check on a credential is the `webauthn`
library's; nothing here is crypto of its own.

**Challenges** are 32 random bytes, kept only as a keyed hash over their
purpose and base64url (decision 0012), valid 5 minutes and used once:

- `passkey_register`, bound to the account and the session that asked;
- `passkey_step_up`, the same;
- `passkey_sign_in`, bound to nothing, since nobody is known yet.

A passkey as a second factor keeps its challenge on the sign-in's own
(`second_factor.py`). The challenge a credential answers is read from its
client data, so a client sends no other handle.

**The relying party** is `SITE_URL`'s host and the origin its origin. With
DEBUG on, `CORS_ORIGINS` count too, as for the same-origin check: a dev
server on another port is the site's own.
"""

from __future__ import annotations

import binascii
import re
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, parse_client_data_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import AuthenticatorTransport, PublicKeyCredentialDescriptor
from webauthn.registration.verify_registration_response import VerifiedRegistration

from kernel import clock
from kernel.auth import tokens
from kernel.auth.models import Passkey, Token
from kernel.config import KernelConfig

LIFETIME = timedelta(minutes=5)
#: What the options ask a browser to wait, in milliseconds: the challenge's life.
TIMEOUT_MS = int(LIFETIME.total_seconds() * 1000)
REGISTER = "passkey_register"
SIGN_IN = "passkey_sign_in"
STEP_UP = "passkey_step_up"
#: A 32-byte challenge in base64url, unpadded: anything else was never issued.
_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")
TRANSPORTS = frozenset(transport.value for transport in AuthenticatorTransport)
#: What decoding a credential's parts can raise besides the library's own.
_MALFORMED = (WebAuthnException, ValueError, TypeError, KeyError, binascii.Error)


# --- what a browser sends -------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True)


class AttestationResponse(_Strict):
    client_data_json: str = Field(alias="clientDataJSON", max_length=4096)
    attestation_object: str = Field(alias="attestationObject", max_length=32768)
    transports: list[Annotated[str, Field(max_length=32)]] = Field(
        default_factory=list, max_length=8
    )


class RegistrationCredential(_Strict):
    """A new passkey, as `PublicKeyCredential.toJSON()` gives it."""

    id: str = Field(max_length=1400)
    raw_id: str = Field(alias="rawId", max_length=1400)
    type: Literal["public-key"]
    response: AttestationResponse

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rawId": self.raw_id,
            "type": self.type,
            "response": {
                "clientDataJSON": self.response.client_data_json,
                "attestationObject": self.response.attestation_object,
                "transports": self.response.transports,
            },
            "clientExtensionResults": {},
        }


class AssertionResponse(_Strict):
    client_data_json: str = Field(alias="clientDataJSON", max_length=4096)
    authenticator_data: str = Field(alias="authenticatorData", max_length=4096)
    signature: str = Field(max_length=2048)
    user_handle: str | None = Field(default=None, alias="userHandle", max_length=128)


class AssertionCredential(_Strict):
    """A passkey's answer to request options, as `toJSON()` gives it."""

    id: str = Field(max_length=1400)
    raw_id: str = Field(alias="rawId", max_length=1400)
    type: Literal["public-key"]
    response: AssertionResponse

    def as_json(self) -> dict[str, Any]:
        response: dict[str, Any] = {
            "clientDataJSON": self.response.client_data_json,
            "authenticatorData": self.response.authenticator_data,
            "signature": self.response.signature,
        }
        if self.response.user_handle is not None:
            response["userHandle"] = self.response.user_handle
        return {
            "id": self.id,
            "rawId": self.raw_id,
            "type": self.type,
            "response": response,
            "clientExtensionResults": {},
        }

    def credential_id(self) -> bytes | None:
        """The raw credential id, or None when it isn't base64url."""
        try:
            return base64url_to_bytes(self.raw_id)
        except _MALFORMED:
            return None


# --- the relying party ----------------------------------------------------------------


@dataclass(frozen=True)
class RelyingParty:
    id: str
    name: str
    origins: tuple[str, ...]


def relying_party(config: KernelConfig) -> RelyingParty:
    parts = urlsplit(config.site_url.strip())
    origins = [f"{parts.scheme}://{parts.netloc}".lower()]
    if config.debug:
        origins += [origin.rstrip("/").lower() for origin in config.cors_origins_list]
    return RelyingParty(parts.hostname or "", config.site_name, tuple(dict.fromkeys(origins)))


def descriptors(passkeys: Iterable[Passkey]) -> list[PublicKeyCredentialDescriptor]:
    """The passkeys as options name them, with the transports they reported."""
    return [
        PublicKeyCredentialDescriptor(
            id=passkey.credential_id,
            transports=[AuthenticatorTransport(t) for t in passkey.transports if t in TRANSPORTS],
        )
        for passkey in passkeys
    ]


# --- challenges -----------------------------------------------------------------------


def new_challenge() -> bytes:
    return secrets.token_bytes(32)


def encoded(challenge: bytes) -> str:
    return bytes_to_base64url(challenge)


def answered(client_data_json: str) -> str | None:
    """The challenge (base64url) a credential's client data answers, or None
    when the client data can't be read or holds nothing we could have issued."""
    try:
        challenge = encoded(parse_client_data_json(base64url_to_bytes(client_data_json)).challenge)
    except _MALFORMED:
        return None
    return challenge if _CHALLENGE.fullmatch(challenge) else None


async def keep(
    db: AsyncSession,
    purpose: str,
    challenge: bytes,
    *,
    user_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Keep a new challenge's keyed hash for 5 minutes; the caller commits."""
    now = clock.now()
    db.add(
        Token(
            purpose=purpose,
            token_hash=tokens.token_hash(purpose, encoded(challenge)),
            user_id=user_id,
            data=data or {},
            created_at=now,
            expires_at=now + LIFETIME,
        )
    )
    await db.flush()


async def use(
    db: AsyncSession,
    purpose: str,
    challenge: str,
    *,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Use up a live challenge of `purpose`: what was kept beside it, or None
    when it was never issued, is used or expired, or isn't `user_id`'s (no
    one's, for None) or `session_id`'s. One UPDATE, so two requests holding
    it can't both have it. The caller commits."""
    now = clock.now()
    where = [
        Token.purpose == purpose,
        Token.token_hash == tokens.token_hash(purpose, challenge),
        Token.used_at.is_(None),
        Token.expires_at > now,
        Token.user_id.is_(None) if user_id is None else Token.user_id == user_id,
    ]
    if session_id is not None:
        where.append(Token.data["session"].astext == str(session_id))
    row = (
        await db.execute(
            update(Token)
            .where(*where)
            .values(used_at=now)
            .returning(Token.data)
            .execution_options(synchronize_session=False)
        )
    ).first()
    return None if row is None else dict(row.data or {})


# --- the checks -----------------------------------------------------------------------


def registered(
    credential: RegistrationCredential, challenge: str, party: RelyingParty
) -> VerifiedRegistration | None:
    """The new passkey, verified with user verification required, or None."""
    try:
        return verify_registration_response(
            credential=credential.as_json(),
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=party.id,
            expected_origin=list(party.origins),
            require_user_verification=True,
        )
    except _MALFORMED:
        return None


def used(
    passkey: Passkey,
    credential: AssertionCredential,
    challenge: str,
    party: RelyingParty,
    *,
    require_user_verification: bool,
    need_user_handle: bool = False,
) -> bool:
    """Whether `credential` is `passkey`'s answer to `challenge`. The user
    handle, when sent (and it must be with `need_user_handle`, as for a
    discoverable sign-in), must be the passkey's account. A sign count that
    doesn't rise, when either count isn't zero, is a clone, and refused. On
    success the passkey's count and last use are written; the caller holds
    the account's lock and commits."""
    handle = credential.response.user_handle
    if handle is None and need_user_handle:
        return False
    if handle is not None and handle != encoded(passkey.user_id.bytes):
        return False
    try:
        verified = verify_authentication_response(
            credential=credential.as_json(),
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=party.id,
            expected_origin=list(party.origins),
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=require_user_verification,
        )
    except _MALFORMED:
        return False
    passkey.sign_count, passkey.last_used_at = verified.new_sign_count, clock.now()
    return True

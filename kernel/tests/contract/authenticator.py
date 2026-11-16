"""A software authenticator for the tests (decision 0028): it answers a
server's WebAuthn options with the JSON a browser's `PublicKeyCredential.toJSON()`
gives, ES256 keys and `none` attestation, and nothing of the kernel's, so a
port of the kernel passes the same suite.

Its knobs make the answers a test needs to be refused: no user verification,
another origin or relying party, someone else's user handle, a sign count
that goes back, a signature that doesn't match.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from dataclasses import dataclass
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

_UP, _UV, _BE, _BS, _AT = 0x01, 0x04, 0x08, 0x10, 0x40


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class Credential:
    id: bytes
    rp_id: str
    user_handle: bytes
    key: ec.EllipticCurvePrivateKey
    count: int = 0


class Authenticator:
    """One authenticator holding discoverable credentials. `counter=False` is
    a synced passkey (its count is always 0, and it says it's backed up);
    `counter=True` a hardware key whose count rises with each use."""

    def __init__(self, origin: str, *, counter: bool = False) -> None:
        self.origin = origin.rstrip("/")
        self.counter = counter
        self.credentials: list[Credential] = []

    # --- registration -------------------------------------------------------------

    def create(
        self,
        options: dict[str, Any],
        *,
        uv: bool = True,
        origin: str | None = None,
        rp_id: str | None = None,
        credential: Credential | None = None,
    ) -> dict[str, Any]:
        """The credential for these creation options; it is kept for `get`.
        With `credential`, that one is offered again instead of a new one."""
        if credential is None:
            credential = self.make(rp_id or options["rp"]["id"], unb64url(options["user"]["id"]))
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        public = credential.key.public_key().public_numbers()
        cose_key = cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32, "big"), -3: public.y.to_bytes(32, "big")}
        )
        attested = bytes(16) + struct.pack(">H", len(credential.id)) + credential.id + cose_key
        auth_data = self._auth_data(credential, uv=uv, extra_flags=_AT) + attested
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(credential.id),
            "rawId": b64url(credential.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def make(self, rp_id: str, user_handle: bytes) -> Credential:
        """A credential the authenticator holds, registered anywhere or nowhere."""
        credential = Credential(
            os.urandom(16), rp_id, user_handle, ec.generate_private_key(ec.SECP256R1())
        )
        self.credentials.append(credential)
        return credential

    # --- assertion ----------------------------------------------------------------

    def get(
        self,
        options: dict[str, Any],
        *,
        credential: Credential | None = None,
        uv: bool = True,
        origin: str | None = None,
        rp_id: str | None = None,
        user_handle: bytes | None = None,
        sign_count: int | None = None,
        tamper: bool = False,
    ) -> dict[str, Any]:
        """The assertion for these request options, by `credential`, else the
        newest one they allow (any of this relying party's when they name none,
        as a discoverable credential is chosen)."""
        chosen = credential or self._choose(options)
        if sign_count is not None:
            chosen.count = sign_count
        elif self.counter:
            chosen.count += 1
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        auth_data = self._auth_data(chosen, uv=uv, rp_id=rp_id)
        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = chosen.key.sign(signed, ec.ECDSA(hashes.SHA256()))
        if tamper:
            signature = signature[:-1] + bytes([signature[-1] ^ 0x01])
        return {
            "id": b64url(chosen.id),
            "rawId": b64url(chosen.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(chosen.user_handle if user_handle is None else user_handle),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def _choose(self, options: dict[str, Any]) -> Credential:
        allowed = {unb64url(item["id"]) for item in options.get("allowCredentials") or []}
        rp_id = options.get("rpId")
        for credential in reversed(self.credentials):
            if allowed and credential.id in allowed:
                return credential
            if not allowed and credential.rp_id == rp_id:
                return credential
        raise LookupError("this authenticator holds no credential these options allow")

    # --- the parts ----------------------------------------------------------------

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        data = {
            "type": kind,
            "challenge": challenge,
            "origin": (origin or self.origin).rstrip("/"),
            "crossOrigin": False,
        }
        return json.dumps(data, separators=(",", ":")).encode()

    def _auth_data(
        self, credential: Credential, *, uv: bool, rp_id: str | None = None, extra_flags: int = 0
    ) -> bytes:
        flags = _UP | extra_flags | (_UV if uv else 0)
        if not self.counter:
            flags |= _BE | _BS  # a synced passkey: backed up, so its count stays 0
        rp_hash = hashlib.sha256((rp_id or credential.rp_id).encode()).digest()
        return rp_hash + bytes([flags]) + struct.pack(">I", credential.count)

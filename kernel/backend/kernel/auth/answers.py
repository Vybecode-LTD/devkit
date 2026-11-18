"""What the auth routes answer, typed (kernel.answers, decision 0042).

The shapes are the ones `docs/contracts/auth-api.md` gives; these models only
name them, so the committed `openapi.json` and the web kernel's client know
them. WebAuthn's options keep the browser's camelCase names (W3C's
`PublicKeyCredentialCreationOptionsJSON` and `...RequestOptionsJSON`), with
an optional key absent rather than null.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from kernel.answers import Answer, Id, OwnActivityEntry, When

#: The second steps an account offers after its password, code or link.
Method = Literal["totp", "recovery_code", "passkey"]


class UserView(Answer):
    """The signed-in person, as `kernel.auth.accounts.view` makes it."""

    id: Id
    email: str
    roles: list[str]
    permissions: list[str]
    verified: bool
    second_factor: bool


class SignedIn(Answer):
    status: Literal["signed_in"]
    user: UserView


class SecondFactorNeeded(Answer):
    """The first step passed; the account has a second factor to ask for."""

    status: Literal["second_factor"]
    challenge: str
    methods: list[Method]


#: A sign-in by password, code or link: done, or a second step to take.
SignInAnswer = Annotated[SignedIn | SecondFactorNeeded, Field(discriminator="status")]


class SessionAnswer(Answer):
    user: UserView


class OwnActivity(Answer):
    items: list[OwnActivityEntry]
    next_cursor: str | None


class CheckEmail(Answer):
    """A mail is on its way, or would be: the same answer either way."""

    status: Literal["check_email"]


class Verified(Answer):
    status: Literal["verified"]


class PasswordReset(Answer):
    status: Literal["password_reset"]


class PasswordChanged(Answer):
    status: Literal["password_changed"]


class EmailChanged(Answer):
    status: Literal["email_changed"]


class EmailRestored(Answer):
    status: Literal["email_restored"]


class SecondFactorUndone(Answer):
    status: Literal["second_factor_undone"]


class SteppedUp(Answer):
    status: Literal["recent"]


class AccountStatus(Answer):
    status: Literal["suspended", "active"]


class TotpSetup(Answer):
    secret: str
    otpauth_uri: str


class RecoveryCodes(Answer):
    recovery_codes: list[str]


class PasskeyView(Answer):
    id: Id
    name: str
    created_at: When
    last_used_at: When | None


class Passkeys(Answer):
    items: list[PasskeyView]


# --- WebAuthn's options, as py_webauthn's options_to_json_dict writes them ---------------


class RelyingParty(Answer):
    name: str
    id: str | None = None


class WebAuthnUser(Answer):
    id: str
    name: str
    displayName: str


class CredentialParameter(Answer):
    type: Literal["public-key"]
    alg: int


class CredentialDescriptor(Answer):
    id: str
    type: Literal["public-key"]
    transports: list[str] | None = None


class AuthenticatorSelection(Answer):
    authenticatorAttachment: str | None = None
    residentKey: str | None = None
    requireResidentKey: bool | None = None
    userVerification: str | None = None


class CreationOptions(Answer):
    """For `navigator.credentials.create`: adding a passkey."""

    rp: RelyingParty
    user: WebAuthnUser
    challenge: str
    pubKeyCredParams: list[CredentialParameter]
    timeout: int | None = None
    excludeCredentials: list[CredentialDescriptor] | None = None
    authenticatorSelection: AuthenticatorSelection | None = None
    hints: list[str] | None = None
    attestation: str | None = None
    attestationFormats: list[str] | None = None
    extensions: dict[str, Any] | None = None


class RequestOptions(Answer):
    """For `navigator.credentials.get`: signing in, a second step or a step-up."""

    challenge: str
    timeout: int | None = None
    rpId: str | None = None
    allowCredentials: list[CredentialDescriptor] | None = None
    userVerification: str | None = None
    hints: list[str] | None = None
    extensions: dict[str, Any] | None = None

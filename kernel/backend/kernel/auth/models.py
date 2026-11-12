"""Auth's tables (SPEC.md 14.11). One `auth_user` for everyone; roles decide
what an account is (14.1).

Secrets are never kept as given: passwords as Argon2id hashes, session
tokens, one-time tokens, recovery codes and API-key secrets as SHA-256
hashes, TOTP secrets sealed (`kernel.crypto`). Emails are kept as typed and,
for lookups, lowercased in `email_normal`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import Base

USER_STATUSES = ("active", "suspended", "deleting", "deleted")
TOKEN_PURPOSES = (
    "verify_email",
    "reset_password",
    "sign_in_code",
    "magic_link",
    "email_change",
    "invite",
    "second_factor",
)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _user_fk(*, nullable: bool = False, on_delete: str = "CASCADE") -> Mapped[Any]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_user.id", ondelete=on_delete), nullable=nullable
    )


class User(Base):
    __tablename__ = "auth_user"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleting', 'deleted')", name="status_known"
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(320))
    email_normal: Mapped[str] = mapped_column(String(320), unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'active'"))
    #: Up on a password change, a reset, a second-factor reset or a suspension:
    #: every session started before then ends (14.5).
    session_epoch: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    #: Up on any role change: each session gets a new token on its next request.
    role_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    deletion_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(Base):
    """A role: the built-in owner, admin, editor and member, or a site's own."""

    __tablename__ = "auth_role"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    builtin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _created()


class RolePermission(Base):
    __tablename__ = "auth_role_permission"

    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_role.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(128), primary_key=True)


class UserRole(Base):
    __tablename__ = "auth_user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_user.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auth_role.id", ondelete="CASCADE"), primary_key=True
    )
    granted_at: Mapped[datetime] = _created()
    granted_by_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, on_delete="SET NULL")


class PermissionOverride(Base):
    """A grant or denial of one permission on one thing, for one person or
    one role (VybeMindz per-resource overrides; 14.8)."""

    __tablename__ = "auth_permission_override"
    __table_args__ = (
        CheckConstraint("effect IN ('grant', 'deny')", name="effect_known"),
        CheckConstraint("(user_id IS NULL) <> (role_id IS NULL)", name="one_subject"),
        Index("ix_auth_permission_override_resource", "resource_type", "resource_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    role_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("auth_role.id", ondelete="CASCADE"), nullable=True
    )
    permission: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(128))
    effect: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = _created()


class Identity(Base):
    """An outside sign-in, keyed by provider and subject, never by email (14.3)."""

    __tablename__ = "auth_identity"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    #: Sealed, and only when a module needs the provider's API.
    access_token_sealed: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Passkey(Base):
    __tablename__ = "auth_passkey"

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    name: Mapped[str] = mapped_column(String(80))
    transports: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = _created()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Totp(Base):
    __tablename__ = "auth_totp"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_user.id", ondelete="CASCADE"), primary_key=True
    )
    secret_sealed: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The last 30-second step a code was accepted for: a code of that step or
    #: an earlier one is refused, so none can be replayed (14.4).
    last_step: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    created_at: Mapped[datetime] = _created()


class RecoveryCode(Base):
    __tablename__ = "auth_recovery_code"

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Session(Base):
    """A signed-in browser. Only the token's SHA-256 is kept (14.5)."""

    __tablename__ = "auth_session"

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = _user_fk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    epoch: Mapped[int] = mapped_column(Integer)
    role_version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: The absolute limit: the session ends then, however busy.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: The last sign-in or step-up: `require_recent_auth` reads it.
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    second_factor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_label: Mapped[str] = mapped_column(String(80), server_default=text("''"))
    location: Mapped[str] = mapped_column(String(80), server_default=text("''"))


class Token(Base):
    """A one-time token, kept hashed: a verification, a reset, a sign-in code
    or link, an email change, an invite, or a sign-in waiting on its second
    factor."""

    __tablename__ = "auth_token"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password', 'sign_in_code', 'magic_link', "
            "'email_change', 'invite', 'second_factor')",
            name="purpose_known",
        ),
        Index("ix_auth_token_lookup", "purpose", "email_normal"),
    )

    id: Mapped[uuid.UUID] = _id()
    purpose: Mapped[str] = mapped_column(String(24))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    email_normal: Mapped[str | None] = mapped_column(String(320))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(Base):
    """`dk_<live|test>_<key_id>_<secret>`; only the secret's SHA-256 is kept (14.9)."""

    __tablename__ = "auth_api_key"

    id: Mapped[uuid.UUID] = _id()
    key_id: Mapped[str] = mapped_column(String(8), unique=True)
    mode: Mapped[str] = mapped_column(String(4))
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    secret_hash: Mapped[str] = mapped_column(String(64))
    scopes: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """The append-only audit log (14.10). The actor and subject are kept as
    plain ids, so a deleted account's history stays, pseudonymous."""

    __tablename__ = "auth_audit_event"
    __table_args__ = (
        Index("ix_auth_audit_event_subject", "subject_id", "at"),
        Index("ix_auth_audit_event_at", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str] = mapped_column(String(300), server_default=text("''"))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

"""The kernel's own tables (K1). Auth's are in `kernel.auth.models`; the outbox and jobs come in K3.

`updated_by_id` and `saved_by_id` hold an `auth_user` id, set to NULL when
that account is deleted (migration kernel_0002 adds the foreign keys).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import Base


class ModuleState(Base):
    """A module the admin switched on or off (the Features page). A module
    with no row is on, as far as MODULES allows it."""

    __tablename__ = "kernel_module_state"

    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class Setting(Base):
    """A module's settings as they stand: one row per module, made on its
    first save. Secret fields are sealed (`kernel.crypto`)."""

    __tablename__ = "kernel_setting"

    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class SettingVersion(Base):
    """One saved version of a module's settings, kept for good: what the
    admin's form showed after the save, a secret only as whether one is kept
    and how many times it has changed. Number 0 is the defaults, never stored."""

    __tablename__ = "kernel_setting_version"
    __table_args__ = (UniqueConstraint("module_id", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id: Mapped[str] = mapped_column(String(64))
    number: Mapped[int] = mapped_column(Integer)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    changed: Mapped[list[str]] = mapped_column(JSONB)
    #: How it was saved: "form", "assistant", "setup", "cli".
    via: Mapped[str] = mapped_column(String(20))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    saved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


# Auth's tables live in kernel.auth.models; importing them here puts every
# kernel table in Base.metadata for Alembic and the model checks.
from kernel.auth import models as _auth_models  # noqa: E402, F401

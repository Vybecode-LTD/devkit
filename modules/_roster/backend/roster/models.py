"""SQLAlchemy models for roster (SPEC.md section 10). Generated scaffold: check types and indexes before the first migration.

Tables are roster_<name>, UUID keys, timestamptz in UTC; foreign keys only to this module's tables and auth_user.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kernel import Base


class RosterProfile(Base):
    __tablename__ = "roster_profile"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_user.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    bio: Mapped[str] = mapped_column(Text, default="")
    photo_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    disciplines: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    on_home_ring: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class RosterLink(Base):
    __tablename__ = "roster_link"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roster_profile.id", ondelete="CASCADE")
    )
    service: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(Text)

"""SQLAlchemy models for licensing (SPEC.md section 10). Generated scaffold: check types and indexes before the first migration.

Tables are licensing_<name>, UUID keys, timestamptz in UTC; foreign keys only to this module's tables and auth_user.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kernel import Base


class LicensingWork(Base):
    __tablename__ = "licensing_work"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_user.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key: Mapped[str | None] = mapped_column(String(12), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(60), nullable=True)
    mood: Mapped[str | None] = mapped_column(String(60), nullable=True)
    mode: Mapped[str] = mapped_column(String(12), default="tiers", doc="tiers or request")
    status: Mapped[str] = mapped_column(String(12), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)


class LicensingFile(Base):
    __tablename__ = "licensing_file"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("licensing_work.id", ondelete="CASCADE")
    )
    format: Mapped[str] = mapped_column(String(12), doc="preview, mp3, wav or stems")
    key: Mapped[str] = mapped_column(Text)


class LicensingTier(Base):
    __tablename__ = "licensing_tier"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60))
    formats: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    price_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    exclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    template_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class LicensingLicense(Base):
    __tablename__ = "licensing_license"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("licensing_work.id", ondelete="RESTRICT")
    )
    tier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("licensing_tier.id", ondelete="RESTRICT")
    )
    buyer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_user.id", ondelete="SET NULL"), nullable=True
    )
    buyer_name: Mapped[str] = mapped_column(String(120))
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, doc="shop order, by id")
    pdf_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LicensingSplit(Base):
    __tablename__ = "licensing_split"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("licensing_work.id", ondelete="CASCADE")
    )
    roster_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    share_bp: Mapped[int] = mapped_column(Integer, doc="Basis points, 10000 = 100%")

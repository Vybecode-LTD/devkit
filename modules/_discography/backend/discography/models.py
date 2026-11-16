"""SQLAlchemy models for discography (SPEC.md section 10). Generated scaffold: check types and indexes before the first migration.

Tables are discography_<name>, UUID keys, timestamptz in UTC; foreign keys only to this module's tables and auth_user.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kernel import Base


class DiscographyAlbum(Base):
    __tablename__ = "discography_album"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artist_line: Mapped[str] = mapped_column(String(200))
    credit: Mapped[str] = mapped_column(Text, default="")
    cover_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    screen_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    screen_focus: Mapped[str] = mapped_column(String(20), default="center")
    status: Mapped[str] = mapped_column(String(12), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscographyTrack(Base):
    __tablename__ = "discography_track"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("discography_album.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(12), default="upload")
    file_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Private master in object storage"
    )
    stream_key: Mapped[str | None] = mapped_column(Text, nullable=True, doc="Public stream file")
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peaks: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    explicit: Mapped[bool] = mapped_column(Boolean, default=False)
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="draft")


class DiscographyCredit(Base):
    __tablename__ = "discography_credit"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("discography_track.id", ondelete="CASCADE"), nullable=True
    )
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("discography_album.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    roster_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, doc="Links to roster by id, no foreign key"
    )


class DiscographyLink(Base):
    __tablename__ = "discography_link"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    album_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("discography_album.id", ondelete="CASCADE")
    )
    service: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(Text)

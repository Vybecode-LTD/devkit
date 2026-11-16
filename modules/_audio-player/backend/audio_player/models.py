"""SQLAlchemy models for audio-player (SPEC.md section 10). Generated scaffold: check types and indexes before the first migration.

Tables are audio_player_<name>, UUID keys, timestamptz in UTC; foreign keys only to this module's tables and auth_user.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kernel import Base


class AudioPlayerPlay(Base):
    __tablename__ = "audio_player_play"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ref_module: Mapped[str] = mapped_column(String(40))
    ref_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    listener_hash: Mapped[str] = mapped_column(
        String(64), doc="Daily-rotating hash, no personal data"
    )


class AudioPlayerPlayDaily(Base):
    __tablename__ = "audio_player_play_daily"

    ref_module: Mapped[str] = mapped_column(String(40), primary_key=True)
    ref_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    plays: Mapped[int] = mapped_column(Integer, default=0)

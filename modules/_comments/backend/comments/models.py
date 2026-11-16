"""SQLAlchemy models for comments (SPEC.md section 10). Generated scaffold: check types and indexes before the first migration.

Tables are comments_<name>, UUID keys, timestamptz in UTC; foreign keys only to this module's tables and auth_user.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kernel import Base


class CommentsThread(Base):
    __tablename__ = "comments_thread"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    target_module: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class CommentsComment(Base):
    __tablename__ = "comments_comment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("comments_thread.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("comments_comment.id", ondelete="CASCADE"), nullable=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_user.id", ondelete="SET NULL"), nullable=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommentsSubscription(Base):
    __tablename__ = "comments_subscription"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("comments_thread.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("auth_user.id", ondelete="CASCADE"))

"""The kernel's own tables: module switches and settings (K1), the jobs
queue and its schedule (K3, decision 0035), and the audit log every module
writes to (K3, decision 0037). Auth's are in `kernel.auth.models`. Events have
no table: their deliveries are jobs (decision 0036).

`updated_by_id` and `saved_by_id` hold an `auth_user` id, set to NULL when
that account is deleted (migration kernel_0002 adds the foreign keys).
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
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
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


#: A job is queued until a worker claims it, running while that worker's lease
#: lasts, then done or dead (kernel.jobs).
JOB_STATES = ("queued", "running", "done", "dead")


class Job(Base):
    """One job: a handler's name, its payload and where it stands. A sealed
    payload is `crypto.seal`ed JSON, wiped when the job ends. `key` makes an
    enqueue a no-op while a job of that name and key is queued or running.
    `last_error` holds an exception's type name, never a value."""

    __tablename__ = "kernel_job"
    __table_args__ = (
        CheckConstraint("state IN ('queued', 'running', 'done', 'dead')", name="state_known"),
        Index(
            "uq_kernel_job_live_key",
            "name",
            "key",
            unique=True,
            postgresql_where=text("state IN ('queued', 'running')"),
        ),
        Index("ix_kernel_job_due", "run_at", postgresql_where=text("state = 'queued'")),
        Index("ix_kernel_job_lease", "locked_until", postgresql_where=text("state = 'running'")),
        Index(
            "ix_kernel_job_finished",
            "finished_at",
            postgresql_where=text("finished_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(130))
    #: `kernel` or the module's id: a switched-off module's jobs wait.
    module: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str | None] = mapped_column(Text)
    sealed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    key: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(8), server_default=text("'queued'"))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tries: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobSchedule(Base):
    """Each scheduled job's newest slot enqueued, so every scheduler, in any
    worker, enqueues a slot once (kernel.worker's scheduler)."""

    __tablename__ = "kernel_job_schedule"

    name: Mapped[str] = mapped_column(String(130), primary_key=True)
    last_slot: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """The append-only audit log (14.10; `kernel.audit`): auth's rows and
    every module's. The actor and subject are kept as plain ids, so a deleted
    account's history stays, pseudonymous. Postgres refuses an UPDATE, and a
    DELETE but the pruning's (migration kernel_0008)."""

    __tablename__ = "kernel_audit_event"
    __table_args__ = (
        Index("ix_kernel_audit_event_subject", "subject_id", "at"),
        Index("ix_kernel_audit_event_at", "at"),
        Index("ix_kernel_audit_event_actor", "actor_id", "at"),
        Index("ix_kernel_audit_event_target", "target_type", "target_id", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    #: `<owner>.<entity>` and the thing's id as text, such as `blog.post`, `42`.
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str] = mapped_column(String(300), server_default=text("''"))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


# Auth's tables live in kernel.auth.models; importing them here puts every
# kernel table in Base.metadata for Alembic and the model checks. Last, since
# auth's models import the audit log's from here.
from kernel.auth import models as _auth_models  # noqa: E402, F401

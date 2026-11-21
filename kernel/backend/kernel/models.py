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


class Notification(Base):
    """A notice in the site's list for one person (kernel.notifications,
    decision 0038): its title is its email template's subject, rendered.
    Kept 90 days after it's read and a year at most (`kernel.prune_notifications`)."""

    __tablename__ = "kernel_notification"
    __table_args__ = (
        Index("ix_kernel_notification_user", "user_id", "created_at"),
        Index(
            "ix_kernel_notification_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_user.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255))
    link: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(Base):
    """A person's choice for one key, once it differs from the module's
    default (kernel.notifications)."""

    __tablename__ = "kernel_notification_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_user.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    in_site: Mapped[bool] = mapped_column(Boolean)
    email: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModerationCase(Base):
    """One reported thing (kernel.moderation, decision 0039): open until staff
    act on it, with the excerpt as it was when first reported. At most one
    case per thing is open. People's ids stay plain, as in the audit log.
    Closed cases go after AUDIT_KEEP_DAYS (`kernel.prune_moderation`)."""

    __tablename__ = "kernel_moderation_case"
    __table_args__ = (
        Index(
            "ux_kernel_moderation_case_open",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_kernel_moderation_case_queue", "status", "last_report_at"),
        Index("ix_kernel_moderation_case_author", "author_id"),
        Index("ix_kernel_moderation_case_closed", "closed_at"),
        CheckConstraint("source IN ('report', 'filter')", name="source_known"),
        CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="status_known"),
        CheckConstraint(
            "outcome IN ('dismiss', 'hide', 'delete', 'time_out', 'ban')", name="outcome_known"
        ),
        CheckConstraint(
            "(status = 'open') = (closed_at IS NULL AND outcome IS NULL)",
            name="closed_when_decided",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: `<owner>.<entity>` and the thing's id as text: a kind a module declares.
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    #: `report` (a person reported it) or `filter` (the filters held it).
    source: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'open'"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    excerpt: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(500))
    report_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_report_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: The action taken: dismiss, hide, delete, time_out or ban.
    outcome: Mapped[str | None] = mapped_column(String(16))


class ModerationReport(Base):
    """One person's report on a case, or the filters' (no reporter). A person
    reports a case once."""

    __tablename__ = "kernel_moderation_report"
    __table_args__ = (
        UniqueConstraint("case_id", "reporter_id"),
        CheckConstraint(
            "reason IN ('spam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm', "
            "'illegal', 'other', 'filter')",
            name="reason_known",
        ),
        CheckConstraint(
            "(reason = 'filter') = (reporter_id IS NULL)", name="filter_has_no_reporter"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kernel_moderation_case.id", ondelete="CASCADE")
    )
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(1000))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaxonomyVocabulary(Base):
    """A list of terms that modules declare in their manifests (kernel.taxonomy,
    decision 0052, hook 2). Its row is made the first time it's used, and its
    label and `hierarchical` are kept in step with the manifests."""

    __tablename__ = "kernel_vocabulary"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(60))
    hierarchical: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class TaxonomyTerm(Base):
    """One term of a vocabulary, its slug unique in it. A term with children
    isn't deleted: they're moved or deleted first."""

    __tablename__ = "kernel_term"
    __table_args__ = (
        UniqueConstraint("vocabulary_id", "slug"),
        Index("ix_kernel_term_parent_id", "parent_id"),
        CheckConstraint("parent_id IS DISTINCT FROM id", name="not_its_own_parent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kernel_vocabulary.id", ondelete="CASCADE")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kernel_term.id")
    )
    slug: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class TaxonomyTermLink(Base):
    """A term on one thing of a module's. No foreign key to the module's row:
    the module calls `taxonomy.untag_all` when it deletes one."""

    __tablename__ = "kernel_term_link"
    __table_args__ = (Index("ix_kernel_term_link_content", "content_type", "content_id"),)

    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kernel_term.id", ondelete="CASCADE"), primary_key=True
    )
    #: `<id>.<entity>`, a content type the module's manifest lists.
    content_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


# Auth's tables live in kernel.auth.models; importing them here puts every
# kernel table in Base.metadata for Alembic and the model checks. Last, since
# auth's models import the audit log's from here.
from kernel.auth import models as _auth_models  # noqa: E402, F401

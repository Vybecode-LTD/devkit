"""The audit log becomes the kernel's (decision 0037, the owner's choice: one
table): auth's `auth_audit_event` is renamed `kernel_audit_event`, keeping its
rows, and gains a target (`target_type`, `target_id`) so any module can
record what it acted on. Two indexes serve the staff's log by person and by
target. Two triggers make it append-only: an UPDATE is refused, and a
DELETE but in a transaction that set `kernel.audit_prune`
(`kernel.prune_audit`); a TRUNCATE, which runs no row trigger, is refused
outright (CodeRabbit on #67).

Revision ID: kernel_0008
Revises: kernel_0007
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0008"
down_revision: str | Sequence[str] | None = "kernel_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading renames the table and adds empty columns;
# downgrading drops the targets modules recorded (each row stays).
destructive = False

_APPEND_ONLY = """
CREATE FUNCTION kernel_audit_event_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('kernel.audit_prune', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'kernel_audit_event is append-only: % refused', TG_OP;
END
$$
"""


def upgrade() -> None:
    op.rename_table("auth_audit_event", "kernel_audit_event")
    op.execute("ALTER SEQUENCE auth_audit_event_id_seq RENAME TO kernel_audit_event_id_seq")
    op.execute(
        "ALTER TABLE kernel_audit_event RENAME CONSTRAINT pk_auth_audit_event "
        "TO pk_kernel_audit_event"
    )
    op.execute("ALTER INDEX ix_auth_audit_event_at RENAME TO ix_kernel_audit_event_at")
    op.execute("ALTER INDEX ix_auth_audit_event_subject RENAME TO ix_kernel_audit_event_subject")
    op.add_column("kernel_audit_event", sa.Column("target_type", sa.String(64), nullable=True))
    op.add_column("kernel_audit_event", sa.Column("target_id", sa.String(64), nullable=True))
    op.create_index(
        "ix_kernel_audit_event_actor", "kernel_audit_event", ["actor_id", "at"], unique=False
    )
    op.create_index(
        "ix_kernel_audit_event_target",
        "kernel_audit_event",
        ["target_type", "target_id", "at"],
        unique=False,
    )
    op.execute(_APPEND_ONLY)
    op.execute(
        "CREATE TRIGGER kernel_audit_event_append_only BEFORE UPDATE OR DELETE "
        "ON kernel_audit_event FOR EACH ROW EXECUTE FUNCTION kernel_audit_event_append_only()"
    )
    op.execute(
        "CREATE TRIGGER kernel_audit_event_no_truncate BEFORE TRUNCATE ON kernel_audit_event "
        "FOR EACH STATEMENT EXECUTE FUNCTION kernel_audit_event_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER kernel_audit_event_no_truncate ON kernel_audit_event")
    op.execute("DROP TRIGGER kernel_audit_event_append_only ON kernel_audit_event")
    op.execute("DROP FUNCTION kernel_audit_event_append_only()")
    op.drop_index("ix_kernel_audit_event_target", table_name="kernel_audit_event")
    op.drop_index("ix_kernel_audit_event_actor", table_name="kernel_audit_event")
    op.drop_column("kernel_audit_event", "target_id")
    op.drop_column("kernel_audit_event", "target_type")
    op.execute("ALTER INDEX ix_kernel_audit_event_subject RENAME TO ix_auth_audit_event_subject")
    op.execute("ALTER INDEX ix_kernel_audit_event_at RENAME TO ix_auth_audit_event_at")
    op.execute(
        "ALTER TABLE kernel_audit_event RENAME CONSTRAINT pk_kernel_audit_event "
        "TO pk_auth_audit_event"
    )
    op.execute("ALTER SEQUENCE kernel_audit_event_id_seq RENAME TO auth_audit_event_id_seq")
    op.rename_table("kernel_audit_event", "auth_audit_event")

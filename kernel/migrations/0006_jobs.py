"""The jobs queue and its schedule (K3, decision 0035; contract k3-jobs):
`kernel_job`, one row per job, and `kernel_job_schedule`, each scheduled
job's newest slot enqueued.

Revision ID: kernel_0006
Revises: kernel_0005
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "kernel_0006"
down_revision: str | Sequence[str] | None = "kernel_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds two empty tables.
destructive = False


def upgrade() -> None:
    op.create_table(
        "kernel_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=130), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("sealed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=True),
        sa.Column("state", sa.String(length=8), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'done', 'dead')", name=op.f("ck_kernel_job_state_known")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_job")),
    )
    op.create_index(
        "uq_kernel_job_live_key",
        "kernel_job",
        ["name", "key"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_kernel_job_due", "kernel_job", ["run_at"], postgresql_where=sa.text("state = 'queued'")
    )
    op.create_index(
        "ix_kernel_job_lease",
        "kernel_job",
        ["locked_until"],
        postgresql_where=sa.text("state = 'running'"),
    )
    op.create_index(
        "ix_kernel_job_finished",
        "kernel_job",
        ["finished_at"],
        postgresql_where=sa.text("finished_at IS NOT NULL"),
    )
    op.create_table(
        "kernel_job_schedule",
        sa.Column("name", sa.String(length=130), nullable=False),
        sa.Column("last_slot", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_kernel_job_schedule")),
    )


def downgrade() -> None:
    # Going down drops every queued job, mail included: run the worker until
    # the queue is empty first.
    op.drop_table("kernel_job_schedule")
    op.drop_index("ix_kernel_job_finished", table_name="kernel_job")
    op.drop_index("ix_kernel_job_lease", table_name="kernel_job")
    op.drop_index("ix_kernel_job_due", table_name="kernel_job")
    op.drop_index("uq_kernel_job_live_key", table_name="kernel_job")
    op.drop_table("kernel_job")

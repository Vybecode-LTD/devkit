"""Moderation (decision 0039): one case per reported thing, the reports on
it, and the time a person is timed out of posting until. Ids of people stay
plain, with no foreign key, as in the audit log, so a case outlives the
accounts it names; a case's reports go with it (ON DELETE CASCADE).

Revision ID: kernel_0010
Revises: kernel_0009
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0010"
down_revision: str | Sequence[str] | None = "kernel_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds two empty tables and an empty column.
destructive = False


def upgrade() -> None:
    op.create_table(
        "kernel_moderation_case",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'open'"), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("excerpt", sa.String(length=1000), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("report_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_report_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.UUID(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "source IN ('report', 'filter')", name=op.f("ck_kernel_moderation_case_source_known")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'actioned', 'dismissed')",
            name=op.f("ck_kernel_moderation_case_status_known"),
        ),
        sa.CheckConstraint(
            "outcome IN ('dismiss', 'hide', 'delete', 'time_out', 'ban')",
            name=op.f("ck_kernel_moderation_case_outcome_known"),
        ),
        sa.CheckConstraint(
            "(status = 'open') = (closed_at IS NULL AND outcome IS NULL)",
            name=op.f("ck_kernel_moderation_case_closed_when_decided"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_moderation_case")),
    )
    op.create_index(
        "ux_kernel_moderation_case_open",
        "kernel_moderation_case",
        ["target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_kernel_moderation_case_queue",
        "kernel_moderation_case",
        ["status", "last_report_at"],
    )
    op.create_index("ix_kernel_moderation_case_author", "kernel_moderation_case", ["author_id"])
    op.create_index("ix_kernel_moderation_case_closed", "kernel_moderation_case", ["closed_at"])
    op.create_table(
        "kernel_moderation_report",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('spam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm', "
            "'illegal', 'other', 'filter')",
            name=op.f("ck_kernel_moderation_report_reason_known"),
        ),
        sa.CheckConstraint(
            "(reason = 'filter') = (reporter_id IS NULL)",
            name=op.f("ck_kernel_moderation_report_filter_has_no_reporter"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["kernel_moderation_case.id"],
            name=op.f("fk_kernel_moderation_report_case_id_kernel_moderation_case"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_moderation_report")),
        sa.UniqueConstraint(
            "case_id", "reporter_id", name=op.f("uq_kernel_moderation_report_case_id")
        ),
    )
    op.add_column(
        "auth_user", sa.Column("timed_out_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("auth_user", "timed_out_until")
    op.drop_table("kernel_moderation_report")
    op.drop_index("ix_kernel_moderation_case_closed", table_name="kernel_moderation_case")
    op.drop_index("ix_kernel_moderation_case_author", table_name="kernel_moderation_case")
    op.drop_index("ix_kernel_moderation_case_queue", table_name="kernel_moderation_case")
    op.drop_index("ux_kernel_moderation_case_open", table_name="kernel_moderation_case")
    op.drop_table("kernel_moderation_case")

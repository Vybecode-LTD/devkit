"""The kernel's core tables: module switches and versioned settings (K1).

Revision ID: kernel_0001
Revises:
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "kernel_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("kernel",)
depends_on: str | Sequence[str] | None = None

destructive = False


def upgrade() -> None:
    op.create_table(
        "kernel_module_state",
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("module_id", name=op.f("pk_kernel_module_state")),
    )
    op.create_table(
        "kernel_setting",
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column(
            "values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("module_id", name=op.f("pk_kernel_setting")),
    )
    op.create_table(
        "kernel_setting_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("via", sa.String(length=20), nullable=False),
        sa.Column(
            "saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("saved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_setting_version")),
        sa.UniqueConstraint(
            "module_id", "number", name=op.f("uq_kernel_setting_version_module_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("kernel_setting_version")
    op.drop_table("kernel_setting")
    op.drop_table("kernel_module_state")

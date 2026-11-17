"""Notifications (decision 0038): each person's notices in the site, and their
choices per key where they differ from the module's default. Both go with the
account (ON DELETE CASCADE).

Revision ID: kernel_0009
Revises: kernel_0008
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0009"
down_revision: str | Sequence[str] | None = "kernel_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds two empty tables.
destructive = False


def upgrade() -> None:
    op.create_table(
        "kernel_notification",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_kernel_notification_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_notification")),
    )
    op.create_index("ix_kernel_notification_user", "kernel_notification", ["user_id", "created_at"])
    op.create_index(
        "ix_kernel_notification_unread",
        "kernel_notification",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "kernel_notification_preference",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("in_site", sa.Boolean(), nullable=False),
        sa.Column("email", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_kernel_notification_preference_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name=op.f("pk_kernel_notification_preference")),
    )


def downgrade() -> None:
    op.drop_table("kernel_notification_preference")
    op.drop_index("ix_kernel_notification_unread", table_name="kernel_notification")
    op.drop_index("ix_kernel_notification_user", table_name="kernel_notification")
    op.drop_table("kernel_notification")

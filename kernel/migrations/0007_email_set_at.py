"""When each account's address was set (decision 0035, the owner's choice):
an unverified account is removed 7 days after its address was set, by
sign-up, an email change or an email change's undo, so an undo that puts back
an unverified address gives it a full week however old the account is.

Revision ID: kernel_0007
Revises: kernel_0006
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0007"
down_revision: str | Sequence[str] | None = "kernel_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds a column: every account there already
# counts as having set its address now, so none is removed sooner than before.
destructive = False


def upgrade() -> None:
    op.add_column(
        "auth_user",
        sa.Column(
            "email_set_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("auth_user", "email_set_at")

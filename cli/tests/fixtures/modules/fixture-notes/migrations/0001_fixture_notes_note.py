"""fixture-notes' one table, for the CLI's tests.

Revision ID: fixture_notes_0001
"""

import sqlalchemy as sa
from alembic import op

revision = "fixture_notes_0001"
down_revision = None
branch_labels = ("fixture-notes",)
depends_on = "kernel_0001"

destructive = False


def upgrade() -> None:
    op.create_table(
        "fixture_notes_note",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("body", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fixture_notes_note")

"""Search index (decision 0052, hook 3; `dev plans/contracts/hooks.md` §3): one
row for each public thing of a module's that site search finds, its words
(`tsv`: the title weighted A, the body B) kept by Postgres from its title,
body and language, and found through a GIN index. A row has no foreign key
to the module's: the kernel fills the table from each module's `search.py`.

Revision ID: kernel_0014
Revises: kernel_0013
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "kernel_0014"
down_revision: str | Sequence[str] | None = "kernel_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds an empty table; downgrading drops only
# what a reindex makes again.
destructive = False

WORDS = (
    "setweight(to_tsvector(language, title), 'A') || setweight(to_tsvector(language, body), 'B')"
)


def upgrade() -> None:
    op.create_table(
        "kernel_search_document",
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("content_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("language", postgresql.REGCONFIG(), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(WORDS, persisted=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "content_type", "content_id", name=op.f("pk_kernel_search_document")
        ),
    )
    op.create_index(
        "ix_kernel_search_document_tsv",
        "kernel_search_document",
        ["tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_kernel_search_document_tsv", table_name="kernel_search_document")
    op.drop_table("kernel_search_document")

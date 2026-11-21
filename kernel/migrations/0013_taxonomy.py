"""Taxonomy (decision 0052, hook 2; `dev plans/contracts/hooks.md` §3): the
vocabularies modules declare, their terms, and the links from a term to a
module's content, with `kernel.taxonomy.manage` granted to the built-in admin
and editor roles, as `kernel/kernel.json` declares it. A link has no foreign
key to the module's row: the module calls `taxonomy.untag_all` when it
deletes one.

Revision ID: kernel_0013
Revises: kernel_0012
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0013"
down_revision: str | Sequence[str] | None = "kernel_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds three empty tables and a grant.
destructive = False

PERMISSION = "kernel.taxonomy.manage"
ROLES = ("admin", "editor")

_grants = sa.table(
    "auth_role_permission", sa.column("role_id", sa.String), sa.column("permission", sa.String)
)


def upgrade() -> None:
    op.create_table(
        "kernel_vocabulary",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("hierarchical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_vocabulary")),
        sa.UniqueConstraint("key", name=op.f("uq_kernel_vocabulary_key")),
    )
    op.create_table(
        "kernel_term",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vocabulary_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "parent_id IS DISTINCT FROM id", name=op.f("ck_kernel_term_not_its_own_parent")
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_id"],
            ["kernel_vocabulary.id"],
            name=op.f("fk_kernel_term_vocabulary_id_kernel_vocabulary"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["kernel_term.id"], name=op.f("fk_kernel_term_parent_id_kernel_term")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kernel_term")),
        sa.UniqueConstraint("vocabulary_id", "slug", name=op.f("uq_kernel_term_vocabulary_id")),
    )
    op.create_index("ix_kernel_term_parent_id", "kernel_term", ["parent_id"])
    op.create_table(
        "kernel_term_link",
        sa.Column("term_id", sa.UUID(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("content_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["kernel_term.id"],
            name=op.f("fk_kernel_term_link_term_id_kernel_term"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "term_id", "content_type", "content_id", name=op.f("pk_kernel_term_link")
        ),
    )
    op.create_index(
        "ix_kernel_term_link_content", "kernel_term_link", ["content_type", "content_id"]
    )
    op.bulk_insert(_grants, [{"role_id": role, "permission": PERMISSION} for role in ROLES])


def downgrade() -> None:
    # Every grant of it goes, a custom role's too: the older kernel doesn't
    # declare the permission, so no role may hold it.
    op.execute(sa.delete(_grants).where(_grants.c.permission == PERMISSION))
    op.drop_index("ix_kernel_term_link_content", table_name="kernel_term_link")
    op.drop_table("kernel_term_link")
    op.drop_index("ix_kernel_term_parent_id", table_name="kernel_term")
    op.drop_table("kernel_term")
    op.drop_table("kernel_vocabulary")

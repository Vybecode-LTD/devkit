"""The kernel's jobs permission (K4 contract §2, addition 8; change 17):
`kernel.jobs.manage`, "Retry and discard failed background jobs", granted to
the built-in admin role, as `kernel/kernel.json` declares it. The dashboard's
failed-jobs item is for those who hold it (K4.6); System's retry and discard
use it (K4.8).

Revision ID: kernel_0011
Revises: kernel_0010
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0011"
down_revision: str | Sequence[str] | None = "kernel_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading only adds a grant.
destructive = False

PERMISSION = "kernel.jobs.manage"
ROLES = ("admin",)

_grants = sa.table(
    "auth_role_permission", sa.column("role_id", sa.String), sa.column("permission", sa.String)
)


def upgrade() -> None:
    op.bulk_insert(_grants, [{"role_id": role, "permission": PERMISSION} for role in ROLES])


def downgrade() -> None:
    # Every grant of it goes, a custom role's too: the older kernel doesn't
    # declare the permission, so no role may hold it.
    op.execute(sa.delete(_grants).where(_grants.c.permission == PERMISSION))

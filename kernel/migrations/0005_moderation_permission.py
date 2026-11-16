"""The kernel's moderation permission (decision 0031): `kernel.moderation.act`,
granted to the built-in admin and editor roles, as `kernel/kernel.json`
declares it.

Revision ID: kernel_0005
Revises: kernel_0004
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0005"
down_revision: str | Sequence[str] | None = "kernel_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading only adds two grants.
destructive = False

PERMISSION = "kernel.moderation.act"
ROLES = ("admin", "editor")

_grants = sa.table(
    "auth_role_permission", sa.column("role_id", sa.String), sa.column("permission", sa.String)
)


def upgrade() -> None:
    op.bulk_insert(_grants, [{"role_id": role, "permission": PERMISSION} for role in ROLES])


def downgrade() -> None:
    # Every grant of it goes, a custom role's too: the older kernel doesn't
    # declare the permission, so no role may hold it.
    op.execute(sa.delete(_grants).where(_grants.c.permission == PERMISSION))

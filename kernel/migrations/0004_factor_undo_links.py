"""Second-factor undo links (decision 0030): one more purpose for `auth_token`,
the 7-day link the mail for an added passkey or TOTP carries.

Revision ID: kernel_0004
Revises: kernel_0003
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0004"
down_revision: str | Sequence[str] | None = "kernel_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10). Upgrading adds a purpose and touches no row.
destructive = False

_BEFORE = (
    "verify_email",
    "reset_password",
    "sign_in_code",
    "magic_link",
    "email_change",
    "invite",
    "second_factor",
    "passkey_register",
    "passkey_sign_in",
    "passkey_step_up",
)
_NEW = ("factor_undo",)
_NAME = "ck_auth_token_purpose_known"


def _known(purposes: Sequence[str]) -> str:
    return "purpose IN (" + ", ".join(f"'{purpose}'" for purpose in purposes) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "auth_token", type_="check")
    op.create_check_constraint(op.f(_NAME), "auth_token", _known(_BEFORE + _NEW))


def downgrade() -> None:
    # The older schema can't hold undo links: going down drops the live ones,
    # and their owners lose that way back until a factor is added again.
    token = sa.table("auth_token", sa.column("purpose", sa.String))
    op.execute(sa.delete(token).where(token.c.purpose.in_(_NEW)))
    op.drop_constraint(op.f(_NAME), "auth_token", type_="check")
    op.create_check_constraint(op.f(_NAME), "auth_token", _known(_BEFORE))

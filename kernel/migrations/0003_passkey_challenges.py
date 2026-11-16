"""Passkey ceremonies' challenges (decision 0028): three more purposes for
`auth_token`, each a 32-byte WebAuthn challenge kept as a keyed hash for 5
minutes. A passkey as a second factor keeps its challenge on the sign-in's.

Revision ID: kernel_0003
Revises: kernel_0002
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "kernel_0003"
down_revision: str | Sequence[str] | None = "kernel_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10).
destructive = False

_BEFORE = (
    "verify_email",
    "reset_password",
    "sign_in_code",
    "magic_link",
    "email_change",
    "invite",
    "second_factor",
)
_NEW = ("passkey_register", "passkey_sign_in", "passkey_step_up")
_NAME = "ck_auth_token_purpose_known"


def _known(purposes: Sequence[str]) -> str:
    return "purpose IN (" + ", ".join(f"'{purpose}'" for purpose in purposes) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "auth_token", type_="check")
    op.create_check_constraint(op.f(_NAME), "auth_token", _known(_BEFORE + _NEW))


def downgrade() -> None:
    # Challenges live 5 minutes: dropping the live ones only ends ceremonies
    # under way, which the older schema can't hold.
    token = sa.table("auth_token", sa.column("purpose", sa.String))
    op.execute(sa.delete(token).where(token.c.purpose.in_(_NEW)))
    op.drop_constraint(op.f(_NAME), "auth_token", type_="check")
    op.create_check_constraint(op.f(_NAME), "auth_token", _known(_BEFORE))

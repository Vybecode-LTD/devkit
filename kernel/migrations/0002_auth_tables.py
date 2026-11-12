"""Auth's tables (SPEC.md 14.11), the built-in roles, and the foreign keys
K1's tables were waiting on.

Revision ID: kernel_0002
Revises: kernel_0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "kernel_0002"
down_revision: str | Sequence[str] | None = "kernel_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# True when this migration drops or rewrites data: the CLI asks before running it
# (SPEC.md section 10).
destructive = False


def upgrade() -> None:
    op.create_table(
        "auth_audit_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "user_agent", sa.String(length=300), server_default=sa.text("''"), nullable=False
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_audit_event")),
    )
    op.create_index("ix_auth_audit_event_at", "auth_audit_event", ["at"], unique=False)
    op.create_index(
        "ix_auth_audit_event_subject", "auth_audit_event", ["subject_id", "at"], unique=False
    )
    op.create_table(
        "auth_role",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("builtin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_role")),
    )
    op.create_table(
        "auth_user",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_normal", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("session_epoch", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("role_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deletion_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleting', 'deleted')",
            name=op.f("ck_auth_user_status_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_user")),
        sa.UniqueConstraint("email_normal", name=op.f("uq_auth_user_email_normal")),
    )
    op.create_table(
        "auth_api_key",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key_id", sa.String(length=8), nullable=False),
        sa.Column("mode", sa.String(length=4), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_api_key_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_api_key")),
        sa.UniqueConstraint("key_id", name=op.f("uq_auth_api_key_key_id")),
    )
    op.create_table(
        "auth_identity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("access_token_sealed", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_identity_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identity")),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_auth_identity_provider")),
    )
    op.create_table(
        "auth_passkey",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "transports",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_passkey_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_passkey")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_auth_passkey_credential_id")),
    )
    op.create_table(
        "auth_permission_override",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("role_id", sa.String(length=64), nullable=True),
        sa.Column("permission", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effect IN ('grant', 'deny')", name=op.f("ck_auth_permission_override_effect_known")
        ),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (role_id IS NULL)",
            name=op.f("ck_auth_permission_override_one_subject"),
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["auth_role.id"],
            name=op.f("fk_auth_permission_override_role_id_auth_role"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_permission_override_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_permission_override")),
    )
    op.create_index(
        "ix_auth_permission_override_resource",
        "auth_permission_override",
        ["resource_type", "resource_id"],
        unique=False,
    )
    op.create_table(
        "auth_recovery_code",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_recovery_code_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_recovery_code")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_auth_recovery_code_code_hash")),
    )
    op.create_table(
        "auth_role_permission",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("permission", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["auth_role.id"],
            name=op.f("fk_auth_role_permission_role_id_auth_role"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission", name=op.f("pk_auth_role_permission")),
    )
    op.create_table(
        "auth_session",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("role_version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("second_factor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "device_label", sa.String(length=80), server_default=sa.text("''"), nullable=False
        ),
        sa.Column("location", sa.String(length=80), server_default=sa.text("''"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_session_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_session_token_hash")),
    )
    op.create_table(
        "auth_token",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("email_normal", sa.String(length=320), nullable=True),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password', 'sign_in_code', 'magic_link', 'email_change', 'invite', 'second_factor')",
            name=op.f("ck_auth_token_purpose_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_token_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_token_token_hash")),
    )
    op.create_index("ix_auth_token_lookup", "auth_token", ["purpose", "email_normal"], unique=False)
    op.create_table(
        "auth_totp",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("secret_sealed", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_totp_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_auth_totp")),
    )
    op.create_table(
        "auth_user_role",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("granted_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_user_role_granted_by_id_auth_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["auth_role.id"],
            name=op.f("fk_auth_user_role_role_id_auth_role"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_user.id"],
            name=op.f("fk_auth_user_role_user_id_auth_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_auth_user_role")),
    )
    op.create_foreign_key(
        op.f("fk_kernel_module_state_updated_by_id_auth_user"),
        "kernel_module_state",
        "auth_user",
        ["updated_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_kernel_setting_updated_by_id_auth_user"),
        "kernel_setting",
        "auth_user",
        ["updated_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_kernel_setting_version_saved_by_id_auth_user"),
        "kernel_setting_version",
        "auth_user",
        ["saved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    roles = sa.table(
        "auth_role",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("builtin", sa.Boolean),
    )
    op.bulk_insert(
        roles,
        [
            {
                "id": "owner",
                "name": "Owner",
                "description": "Every permission. A site always has one.",
                "builtin": True,
            },
            {
                "id": "admin",
                "name": "Admin",
                "description": "Runs the site: people, roles, modules and settings.",
                "builtin": True,
            },
            {
                "id": "editor",
                "name": "Editor",
                "description": "Writes and publishes content.",
                "builtin": True,
            },
            {
                "id": "member",
                "name": "Member",
                "description": "A signed-up visitor.",
                "builtin": True,
            },
        ],
    )
    grants = sa.table(
        "auth_role_permission", sa.column("role_id", sa.String), sa.column("permission", sa.String)
    )
    op.bulk_insert(
        grants,
        [
            {"role_id": "admin", "permission": permission}
            for permission in (
                "auth.user.manage",
                "auth.user.suspend",
                "auth.role.assign",
                "auth.audit.read",
                "kernel.module.manage",
                "kernel.settings.manage",
            )
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_kernel_setting_version_saved_by_id_auth_user"),
        "kernel_setting_version",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_kernel_setting_updated_by_id_auth_user"), "kernel_setting", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_kernel_module_state_updated_by_id_auth_user"),
        "kernel_module_state",
        type_="foreignkey",
    )
    op.drop_table("auth_user_role")
    op.drop_table("auth_totp")
    op.drop_index("ix_auth_token_lookup", table_name="auth_token")
    op.drop_table("auth_token")
    op.drop_table("auth_session")
    op.drop_table("auth_role_permission")
    op.drop_table("auth_recovery_code")
    op.drop_index("ix_auth_permission_override_resource", table_name="auth_permission_override")
    op.drop_table("auth_permission_override")
    op.drop_table("auth_passkey")
    op.drop_table("auth_identity")
    op.drop_table("auth_api_key")
    op.drop_table("auth_user")
    op.drop_table("auth_role")
    op.drop_index("ix_auth_audit_event_subject", table_name="auth_audit_event")
    op.drop_index("ix_auth_audit_event_at", table_name="auth_audit_event")
    op.drop_table("auth_audit_event")

"""PR 26: Security tables — admin_audit_log + revoked_tokens + password_reset_tokens

Revision ID: 0012_security_tables
Revises: 0011_account_portfolio_snapshot
Create Date: 2026-05-14 12:00:00.000000

Pre-launch security hardening:

1. **admin_audit_log** — каждое admin-действие (toggle, impersonate, view-sync-health)
   записывается. Нужно для 152-ФЗ compliance и расследования инцидентов.

2. **revoked_tokens** — JWT jti, признанные невалидными (logout, incident).
   Auth dependency проверяет jti на каждом request. Исправляет P0 баг: украденный
   токен оставался валидным после logout до естественного expiry.

3. **password_reset_tokens** — one-time URL-safe токены для password reset flow
   (POST /auth/password-reset/request → email с link → confirm).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012_security_tables"
down_revision: Union[str, Sequence[str], None] = "0011_account_portfolio_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_account_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"]
    )
    op.create_index(
        "ix_admin_audit_actor_time",
        "admin_audit_log",
        ["actor_user_id", "created_at"],
    )
    op.create_index("ix_admin_audit_action", "admin_audit_log", ["action"])
    op.create_index(
        "ix_admin_audit_target", "admin_audit_log", ["target_user_id"]
    )

    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_revoked_tokens_user_id", "revoked_tokens", ["user_id"]
    )
    op.create_index(
        "ix_revoked_tokens_expires", "revoked_tokens", ["expires_at"]
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("token", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("requester_ip", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_pwd_reset_user", "password_reset_tokens", ["user_id"])
    op.create_index(
        "ix_pwd_reset_expires", "password_reset_tokens", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_pwd_reset_expires", table_name="password_reset_tokens")
    op.drop_index("ix_pwd_reset_user", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("ix_revoked_tokens_expires", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_user_id", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")

    op.drop_index("ix_admin_audit_target", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_action", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_actor_time", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

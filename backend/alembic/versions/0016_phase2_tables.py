"""PR 26 (Phase 2): FeatureFlagORM + AccessLogORM + User.totp_*

Revision ID: 0016_phase2_tables
Revises: 0015_broker_conn_unique
Create Date: 2026-05-14 16:00:00.000000

Финальная порция таблиц для launch:

1. **feature_flags** — per-user beta access (MAE/MFE, Trade Replay, AI)
2. **access_log** — sampled HTTP requests (10%) для admin debugging
3. **users.totp_secret + totp_enabled** — TOTP 2FA для admin аккаунтов
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016_phase2_tables"
down_revision: Union[str, Sequence[str], None] = "0015_broker_conn_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column, has_table

    bind = op.get_bind()

    # DATA-01: на чистой БД объекты уже создал 0001 (create_all из models).
    if not has_table(bind, "feature_flags"):
        op.create_table(
            "feature_flags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("flag_name", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "flag_name", name="uq_feature_flag_user_name"),
        )
        op.create_index("ix_feature_flags_user", "feature_flags", ["user_id"])

    if not has_table(bind, "access_log"):
        op.create_table(
            "access_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("method", sa.String(length=8), nullable=False),
            sa.Column("path", sa.String(length=256), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=256), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_access_log_user_id", "access_log", ["user_id"])
        op.create_index("ix_access_log_created_at", "access_log", ["created_at"])
        op.create_index("ix_access_log_user_time", "access_log", ["user_id", "created_at"])
        op.create_index("ix_access_log_status", "access_log", ["status_code"])

    if not has_column(bind, "users", "totp_secret"):
        with op.batch_alter_table("users", schema=None) as batch:
            batch.add_column(sa.Column("totp_secret", sa.String(length=64), nullable=True))
            batch.add_column(sa.Column("totp_enabled", sa.Boolean(), nullable=True, server_default="0"))


def downgrade() -> None:
    from _guards import has_column, has_table

    bind = op.get_bind()

    if has_column(bind, "users", "totp_secret"):
        with op.batch_alter_table("users", schema=None) as batch:
            batch.drop_column("totp_enabled")
            batch.drop_column("totp_secret")

    if has_table(bind, "access_log"):
        op.drop_index("ix_access_log_status", table_name="access_log")
        op.drop_index("ix_access_log_user_time", table_name="access_log")
        op.drop_index("ix_access_log_created_at", table_name="access_log")
        op.drop_index("ix_access_log_user_id", table_name="access_log")
        op.drop_table("access_log")

    if has_table(bind, "feature_flags"):
        op.drop_index("ix_feature_flags_user", table_name="feature_flags")
        op.drop_table("feature_flags")

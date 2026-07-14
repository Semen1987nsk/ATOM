"""add pd_consents table and User.deletion_requested_at (152-ФЗ compliance)

Revision ID: 0002_add_pd_consents
Revises: 0001_initial_baseline
Create Date: 2026-05-07 00:00:00.000000

Цель: реализовать соответствие ст. 9 ч. 4 и ст. 21 ч. 5 152-ФЗ.

Добавляет:
1. Таблицу pd_consents — журнал согласий пользователей на ОПД с IP/User-Agent
   (доказательная база при проверке РКН).
2. Колонку users.deletion_requested_at — soft-delete с 30-дневным grace period
   для запросов на удаление аккаунта.

SQLite-совместимость: используем batch_alter_table для ALTER COLUMN.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_add_pd_consents"
down_revision: Union[str, Sequence[str], None] = "0001_initial_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ----- 1. users.deletion_requested_at -----
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "deletion_requested_at" not in user_columns:
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("deletion_requested_at", sa.DateTime(), nullable=True)
            )
            batch_op.create_index(
                "ix_users_deletion_requested_at",
                ["deletion_requested_at"],
                unique=False,
            )

    # ----- 2. pd_consents -----
    if not inspector.has_table("pd_consents"):
        op.create_table(
            "pd_consents",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("consent_text_version", sa.String(), nullable=False),
            sa.Column("accepted_at", sa.DateTime(), nullable=False),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_pd_consents_id", "pd_consents", ["id"], unique=False)
        op.create_index("ix_pd_consents_user_id", "pd_consents", ["user_id"], unique=False)
        op.create_index(
            "ix_pd_consents_user_active",
            "pd_consents",
            ["user_id", "revoked_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("pd_consents"):
        op.drop_index("ix_pd_consents_user_active", table_name="pd_consents")
        op.drop_index("ix_pd_consents_user_id", table_name="pd_consents")
        op.drop_index("ix_pd_consents_id", table_name="pd_consents")
        op.drop_table("pd_consents")

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "deletion_requested_at" in user_columns:
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.drop_index("ix_users_deletion_requested_at")
            batch_op.drop_column("deletion_requested_at")

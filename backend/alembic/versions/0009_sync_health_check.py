"""PR 20: таблица sync_health_checks — история health-audit'ов

Revision ID: 0009_sync_health_check
Revises: 0008_trade_entry_value
Create Date: 2026-05-13 22:00:00.000000

Создаётся для отслеживания корректности импорта Tinkoff для каждого
пользователя. После каждого pipeline.run SyncHealthAuditor проверяет
данные аккаунта и пишет результат. UI/admin читают последнюю запись.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009_sync_health_check"
down_revision: Union[str, Sequence[str], None] = "0008_trade_entry_value"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_table

    if has_table(op.get_bind(), "sync_health_checks"):
        return

    op.create_table(
        "sync_health_checks",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker_account_id", sa.String(64), nullable=False),
        sa.Column("sync_id", sa.String(64), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "total_trades_checked",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "trades_with_issues",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("issues_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_health_account_time",
        "sync_health_checks",
        ["account_id", "checked_at"],
    )
    op.create_index("ix_health_status", "sync_health_checks", ["status"])


def downgrade() -> None:
    from _guards import has_table

    if not has_table(op.get_bind(), "sync_health_checks"):
        return

    op.drop_index("ix_health_status", table_name="sync_health_checks")
    op.drop_index("ix_health_account_time", table_name="sync_health_checks")
    op.drop_table("sync_health_checks")

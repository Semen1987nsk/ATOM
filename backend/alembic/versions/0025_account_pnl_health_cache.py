"""Phase 10: Account.last_pnl_health_* cache columns

Revision ID: 0025_account_pnl_health_cache
Revises: 0024_trade_point_value_snapshot
Create Date: 2026-05-17 21:00:00.000000

Phase 10 (2026-05-17): кешируем результат P&L Health Check на Account.
Запускается nightly cron'ом + post-sync hook. UI читает cached fields
напрямую без recalc — O(1) latency для dashboard badge.

Сравнение двух методологий:
  Method A (Journal):  closed Trade.net_pnl + open unrealized + adjustments
  Method B (Cash):     last_portfolio_value - net_deposits

|A − B| / |B| × 100 = diff_pct → status:
  < 0.5%  → ok
  < 2%    → warning
  >= 2%   → mismatch

Если |cash_pnl| < 1 ₽ (нет операций) → status='na'.
Если last_pnl_health_at старше 7 дней → UI показывает 'stale' (computed in router).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0025_account_pnl_health_cache"
down_revision: Union[str, Sequence[str], None] = "0024_trade_point_value_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("accounts", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "last_pnl_health_at",
                sa.DateTime,
                nullable=True,
                comment="Timestamp of last P&L health check",
            )
        )
        batch.add_column(
            sa.Column(
                "last_pnl_health_status",
                sa.String(16),
                nullable=True,
                comment="ok|warning|mismatch|stale|na",
            )
        )
        batch.add_column(
            sa.Column(
                "last_pnl_health_diff_pct",
                sa.Numeric(precision=10, scale=4),
                nullable=True,
                comment="|journal − cash| / |cash| × 100",
            )
        )
        batch.add_column(
            sa.Column(
                "last_pnl_health_diff_rub",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
                comment="journal_pnl − cash_pnl (signed, RUB)",
            )
        )
        batch.add_column(
            sa.Column(
                "last_pnl_health_breakdown",
                sa.JSON,
                nullable=True,
                comment="{journal_pnl, cash_pnl, closed, unrealized, adjustments, portfolio, deposits, ...}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("accounts", schema=None) as batch:
        batch.drop_column("last_pnl_health_breakdown")
        batch.drop_column("last_pnl_health_diff_rub")
        batch.drop_column("last_pnl_health_diff_pct")
        batch.drop_column("last_pnl_health_status")
        batch.drop_column("last_pnl_health_at")

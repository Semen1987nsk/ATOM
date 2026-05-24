"""PR 26 (Phase 3): broker_reports + reconciliation_runs + reconciliation_breaks

Revision ID: 0018_broker_reports
Revises: 0017_email_verify
Create Date: 2026-05-14 18:00:00.000000

Three-way triangulation для verification correctness:
- broker_reports — кэш официальных Tinkoff broker report'ов
  (источник B в 3-way reconciliation: independent ground truth от того же
  брокера, не зависит от потоковых GetOperationsByCursor)
- reconciliation_runs — история запусков сверки
- reconciliation_breaks — конкретные расхождения для drill-down
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018_broker_reports"
down_revision: Union[str, Sequence[str], None] = "0017_email_verify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("broker_commission_total", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("exchange_commission_total", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("clearing_commission_total", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("dividends_gross", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("ndfl_withheld", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("net_cash_flow", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("end_cash_balance", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("raw_trades", sa.JSON(), nullable=True),
        sa.UniqueConstraint("account_id", "period_start", "period_end", name="uq_broker_report_period"),
    )
    op.create_index("ix_broker_reports_account_fetched", "broker_reports", ["account_id", "fetched_at"])
    op.create_index("ix_broker_reports_account_id", "broker_reports", ["account_id"])

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),  # ok|warning|break|error
        sa.Column("breaks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="admin_manual"),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
    )
    op.create_index("ix_reconciliation_runs_account_started", "reconciliation_runs", ["account_id", "started_at"])
    op.create_index("ix_reconciliation_runs_status", "reconciliation_runs", ["status"])
    op.create_index("ix_reconciliation_runs_account_id", "reconciliation_runs", ["account_id"])
    op.create_index("ix_reconciliation_runs_user_id", "reconciliation_runs", ["user_id"])

    op.create_table(
        "reconciliation_breaks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("our_value", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("broker_value", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("diff_abs", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("diff_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),  # hard|soft
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolution_note", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_reconciliation_breaks_run", "reconciliation_breaks", ["run_id"])
    op.create_index("ix_reconciliation_breaks_unresolved", "reconciliation_breaks", ["resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_reconciliation_breaks_unresolved", table_name="reconciliation_breaks")
    op.drop_index("ix_reconciliation_breaks_run", table_name="reconciliation_breaks")
    op.drop_table("reconciliation_breaks")

    op.drop_index("ix_reconciliation_runs_user_id", table_name="reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_account_id", table_name="reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_status", table_name="reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_account_started", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")

    op.drop_index("ix_broker_reports_account_id", table_name="broker_reports")
    op.drop_index("ix_broker_reports_account_fetched", table_name="broker_reports")
    op.drop_table("broker_reports")

"""Reverse-Trial model: 21d trial + Free+ + Pro

Revision ID: 0019_reverse_trial
Revises: 0018_broker_reports
Create Date: 2026-05-15 00:00:00.000000

См. ADR-0005 (.business/tech/decisions/0005-reverse-trial-model.md).

Изменения (все additive, не ломают существующие записи):

1. subscriptions:
   - status: TEXT (trial_active | trial_expired | free_plus | pro_active | corporate_active | none)
     Заполняется default'ом 'none' для существующих записей. SubscriptionPlan-enum
     (FREE/PRO/CORPORATE) остаётся как источник истины для plan; status — отдельная
     ортогональная ось (для downgrade-job).
   - trial_started_at: DATETIME, nullable
   - trial_ended_at: DATETIME, nullable
   - trial_summary_shown: BOOLEAN, default 0 (показывали ли D+21 dialog)
   - frozen_at: DATETIME, nullable (момент downgrade; для метки "Расчёт остановлен ...")

2. trades:
   - created_during_trial: BOOLEAN, default 0
     (для read-only Trade Replay и архивных MAE/MFE на Free+)

3. ai_request_log:
   - новая таблица для cap'а 30 AI-запросов за trial-период
   - (user_id, requested_at, kind, tokens_in, tokens_out, cost_rub)

Down-миграция полностью обратная.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0019_reverse_trial"
down_revision: Union[str, Sequence[str], None] = "0018_broker_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column, has_index, has_table

    bind = op.get_bind()

    # DATA-01: на чистой БД объекты уже создал 0001 (create_all из models).
    # --- subscriptions ---
    if not has_column(bind, "subscriptions", "status"):
        with op.batch_alter_table("subscriptions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="none",
                )
            )
            batch_op.add_column(sa.Column("trial_started_at", sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column("trial_ended_at", sa.DateTime(), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "trial_summary_shown",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )
            batch_op.add_column(sa.Column("frozen_at", sa.DateTime(), nullable=True))

    if not has_index(bind, "subscriptions", "ix_subscriptions_status_trial_ended"):
        op.create_index(
            "ix_subscriptions_status_trial_ended",
            "subscriptions",
            ["status", "trial_ended_at"],
        )

    # --- trades ---
    if not has_column(bind, "trades", "created_during_trial"):
        with op.batch_alter_table("trades") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "created_during_trial",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )

    # --- ai_request_log ---
    if not has_table(bind, "ai_request_log"):
        op.create_table(
            "ai_request_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("plan_at_request", sa.String(length=32), nullable=False),
            sa.Column("tokens_in", sa.Integer(), nullable=True),
            sa.Column("tokens_out", sa.Integer(), nullable=True),
            sa.Column("cost_rub", sa.Numeric(precision=10, scale=4), nullable=True),
        )
        op.create_index("ix_ai_request_log_user_requested", "ai_request_log", ["user_id", "requested_at"])


def downgrade() -> None:
    from _guards import has_column, has_index, has_table

    bind = op.get_bind()

    if has_table(bind, "ai_request_log"):
        op.drop_index("ix_ai_request_log_user_requested", table_name="ai_request_log")
        op.drop_table("ai_request_log")

    if has_column(bind, "trades", "created_during_trial"):
        with op.batch_alter_table("trades") as batch_op:
            batch_op.drop_column("created_during_trial")

    if has_index(bind, "subscriptions", "ix_subscriptions_status_trial_ended"):
        op.drop_index("ix_subscriptions_status_trial_ended", table_name="subscriptions")

    if has_column(bind, "subscriptions", "status"):
        with op.batch_alter_table("subscriptions") as batch_op:
            batch_op.drop_column("frozen_at")
            batch_op.drop_column("trial_summary_shown")
            batch_op.drop_column("trial_ended_at")
            batch_op.drop_column("trial_started_at")
            batch_op.drop_column("status")

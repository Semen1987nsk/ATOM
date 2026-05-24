"""PR 26 (Phase 1): SyncEventORM — история всех sync attempts

Revision ID: 0014_sync_events
Revises: 0013_payment_attempts
Create Date: 2026-05-14 14:00:00.000000

SyncHealthCheckORM пишется только при успехе. Нужна вторая таблица
с записью каждой попытки sync (success/failed/interrupted/timeout) для:
- /admin/users/{id}/sync-timeline endpoint
- verify_user check #7 (cursor monotonicity)
- Поддержка debug юзера "у меня sync завис"
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0014_sync_events"
down_revision: Union[str, Sequence[str], None] = "0013_payment_attempts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("broker_account_id", sa.String(length=64), nullable=True),
        sa.Column("sync_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cursor_before", sa.String(length=256), nullable=True),
        sa.Column("cursor_after", sa.String(length=256), nullable=True),
        sa.Column("pages_fetched", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("operations_total", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("operations_new_or_updated", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("trades_built", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("positions_open", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_sync_events_account_id", "sync_events", ["account_id"])
    op.create_index("ix_sync_events_account_started", "sync_events", ["account_id", "started_at"])
    op.create_index("ix_sync_events_status", "sync_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sync_events_status", table_name="sync_events")
    op.drop_index("ix_sync_events_account_started", table_name="sync_events")
    op.drop_index("ix_sync_events_account_id", table_name="sync_events")
    op.drop_table("sync_events")

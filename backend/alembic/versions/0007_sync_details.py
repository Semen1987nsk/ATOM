"""PR 17: детализация последней синхронизации в BrokerConnection

Revision ID: 0007_sync_details
Revises: 0006_pr7_trade_unique_with_exit
Create Date: 2026-05-13 21:00:00.000000

После каждого sync хочется видеть в UI:
* сколько операций обработано,
* сколько FIFO-сделок построено,
* сколько открытых позиций,
* длительность.

Сейчас в BrokerConnection есть только last_sync_at/last_sync_status — это
не информативно. Добавляем 4 поля, заполняемых из SyncReport в pipeline.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007_sync_details"
down_revision: Union[str, Sequence[str], None] = "0006_pr7_trade_unique_with_exit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("broker_connections", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("last_sync_operations_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_sync_trades_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_sync_positions_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_sync_duration_ms", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("broker_connections", schema=None) as batch_op:
        batch_op.drop_column("last_sync_duration_ms")
        batch_op.drop_column("last_sync_positions_count")
        batch_op.drop_column("last_sync_trades_count")
        batch_op.drop_column("last_sync_operations_count")

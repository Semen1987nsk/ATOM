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


_COLUMNS = (
    "last_sync_operations_count",
    "last_sync_trades_count",
    "last_sync_positions_count",
    "last_sync_duration_ms",
)


def upgrade() -> None:
    from _guards import missing_columns

    bind = op.get_bind()
    to_add = missing_columns(
        bind,
        "broker_connections",
        {name: sa.Column(name, sa.Integer(), nullable=True) for name in _COLUMNS},
    )
    if not to_add:
        return
    with op.batch_alter_table("broker_connections", schema=None) as batch_op:
        for col in to_add.values():
            batch_op.add_column(col)


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    to_drop = [c for c in reversed(_COLUMNS) if has_column(bind, "broker_connections", c)]
    if not to_drop:
        return
    with op.batch_alter_table("broker_connections", schema=None) as batch_op:
        for name in to_drop:
            batch_op.drop_column(name)

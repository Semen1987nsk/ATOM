"""PR 18: Trade.entry_value / exit_value — cost-basis в валюте инструмента

Revision ID: 0008_trade_entry_value
Revises: 0007_sync_details
Create Date: 2026-05-13 21:30:00.000000

Для фьючерсов entry_price хранится в пунктах (например, 16.39), а pnl
в рублях (после умножения на point_value). Из-за этого формула
pnl_pct = pnl / (entry_price × quantity) даёт ерунду типа +678% при
реальной прибыли +8.82%.

Новые колонки entry_value / exit_value содержат сумму payment'ов в
валюте инструмента, посчитанную FIFO-движком. Это правильный знаменатель
для процента у любого типа инструмента.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_trade_entry_value"
down_revision: Union[str, Sequence[str], None] = "0007_sync_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("entry_value", sa.Numeric(precision=18, scale=8), nullable=True)
        )
        batch_op.add_column(
            sa.Column("exit_value", sa.Numeric(precision=18, scale=8), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("trades", schema=None) as batch_op:
        batch_op.drop_column("exit_value")
        batch_op.drop_column("entry_value")

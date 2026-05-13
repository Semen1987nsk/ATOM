"""PR 7: расширить UniqueConstraint у trades — добавить exit_at и data_source

Revision ID: 0006_pr7_trade_unique_with_exit
Revises: 0005_pr5_operations_table
Create Date: 2026-05-13 18:45:00.000000

Старая дедупликация `uq_trades_dedup(account_id, symbol, entry_at, direction)`
покрывала ручной импорт (один и тот же ордер не должен попасть дважды).
В новом FIFO-движке (PR 7) для одной BUY-операции часто формируется
несколько Trade-записей (по partial-SELL'ам) — все с одинаковым `entry_at`.
Старый constraint их блокировал.

Решение — расширить ключ до `(account_id, symbol, entry_at, exit_at,
direction, data_source)`. Это:
* сохраняет дедупликацию по entry_at для legacy/manual записей с одинаковым
  exit_at (или обоими null для открытых);
* разводит partial-trades нового sync по exit_at;
* разделяет namespaces legacy / tinkoff_v2 / manual через data_source.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_pr7_trade_unique_with_exit"
down_revision: Union[str, Sequence[str], None] = "0005_pr5_operations_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_NAME = "uq_trades_dedup_v2"
_OLD_NAME = "uq_trades_dedup"


def upgrade() -> None:
    """SQLite/PG-friendly: пересоздаём constraint через batch_alter_table."""
    with op.batch_alter_table("trades", schema=None) as batch_op:
        # Не все БД хранят constraint под именем, попытка drop'а в try-блоке.
        try:
            batch_op.drop_constraint(_OLD_NAME, type_="unique")
        except Exception:
            pass
        batch_op.create_unique_constraint(
            _NEW_NAME,
            ["account_id", "symbol", "entry_at", "exit_at", "direction", "data_source"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trades", schema=None) as batch_op:
        try:
            batch_op.drop_constraint(_NEW_NAME, type_="unique")
        except Exception:
            pass
        batch_op.create_unique_constraint(
            _OLD_NAME,
            ["account_id", "symbol", "entry_at", "direction"],
        )

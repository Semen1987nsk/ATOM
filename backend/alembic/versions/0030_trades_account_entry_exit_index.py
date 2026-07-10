"""S4-19: ix_trades_account_entry_exit — недостающая миграция под индекс из models.py.

Revision ID: 0030_trades_account_entry_exit_index
Revises: 0029_broker_conn_cascade
Create Date: 2026-07-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_trades_account_entry_exit_index"
down_revision: Union[str, Sequence[str], None] = "0029_broker_conn_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "ix_trades_account_entry_exit"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} "
                "ON trades (account_id, entry_at, exit_at)"
            )
    else:
        from _guards import has_index
        bind = op.get_bind()
        if not has_index(bind, "trades", _INDEX):
            op.create_index(
                _INDEX, "trades", ["account_id", "entry_at", "exit_at"], unique=False
            )


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
    else:
        from _guards import has_index
        bind = op.get_bind()
        if has_index(bind, "trades", _INDEX):
            op.drop_index(_INDEX, table_name="trades")

"""PR 26 Scenario #35: UNIQUE (account_id, broker, broker_account_id)

Revision ID: 0015_broker_conn_unique
Revises: 0014_sync_events
Create Date: 2026-05-14 15:00:00.000000

Защита от дубликатов: юзер не может подключить ОДИН Tinkoff broker_account_id
к одному local Account дважды. Без этого constraint'а повторное подключение
создавало вторую BrokerConnection, и FIFO matching работал с дублирующими
operations.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0015_broker_conn_unique"
down_revision: Union[str, Sequence[str], None] = "0014_sync_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("broker_connections", schema=None) as batch:
        batch.create_unique_constraint(
            "uq_broker_conn_account_broker_brokeracct",
            ["account_id", "broker", "broker_account_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("broker_connections", schema=None) as batch:
        batch.drop_constraint(
            "uq_broker_conn_account_broker_brokeracct", type_="unique"
        )

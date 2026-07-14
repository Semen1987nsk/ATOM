"""AU-stream Phase 1+: stream_enabled column для real-time push-syncing

Revision ID: 0020_broker_conn_stream_enabled
Revises: 0019_reverse_trial
Create Date: 2026-05-16 12:00:00.000000

Добавляет boolean флаг `stream_enabled` в broker_connections. Когда =True,
StreamTaskManager создаёт long-lived asyncio task на стартапе backend'a
который держит open gRPC stream (operations_stream) для этой connection
и push'ит операции в режиме real-time (вместо poll каждые N минут).

По умолчанию False — все existing connections продолжают использовать
polling. Включается per-connection через admin endpoint stream-toggle
или прямым UPDATE в БД.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020_broker_conn_stream_enabled"
down_revision: Union[str, Sequence[str], None] = "0019_reverse_trial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    # DATA-01: на чистой БД колонку уже создал 0001 (create_all из models).
    if has_column(bind, "broker_connections", "stream_enabled"):
        return

    with op.batch_alter_table("broker_connections", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "stream_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    if not has_column(bind, "broker_connections", "stream_enabled"):
        return

    with op.batch_alter_table("broker_connections", schema=None) as batch:
        batch.drop_column("stream_enabled")

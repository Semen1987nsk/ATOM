"""PR 0: add Trade.data_source and mark all existing rows as 'legacy'

Revision ID: 0003_pr0_trade_data_source
Revises: 0002_add_pd_consents
Create Date: 2026-05-09 00:00:00.000000

Контекст: greenfield-переписывание Tinkoff-интеграции (PR 0..16). Все
сделки, импортированные старым `tinkoff_service` (удалён в PR 0), помечаем
как `legacy`. Новый sync, который появится в PR 5+, будет писать
`tinkoff_v2`. Ручной ввод и Excel-импорт остаются `manual`.

Поле — обычный String (без Enum), чтобы миграция была SQLite/PG-совместимой.
Допустимые значения проверяются на уровне Python (см. models.py::Trade).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_pr0_trade_data_source"
down_revision: Union[str, Sequence[str], None] = "0002_add_pd_consents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    trade_columns = {c["name"] for c in inspector.get_columns("trades")}

    if "data_source" not in trade_columns:
        with op.batch_alter_table("trades", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "data_source",
                    sa.String(length=32),
                    nullable=False,
                    server_default="legacy",
                )
            )

        # Все существующие записи к этому моменту — старый импорт; явно
        # подтверждаем 'legacy', даже если server_default уже сработал
        # (на некоторых движках NULL-фоллбэк может не сохраниться).
        op.execute(
            "UPDATE trades SET data_source = 'legacy' "
            "WHERE data_source IS NULL OR data_source = ''"
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    trade_columns = {c["name"] for c in inspector.get_columns("trades")}
    if "data_source" in trade_columns:
        with op.batch_alter_table("trades", schema=None) as batch_op:
            batch_op.drop_column("data_source")

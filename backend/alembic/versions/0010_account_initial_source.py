"""PR 21: Account.initial_balance_source — auto vs manual

Revision ID: 0010_account_initial_source
Revises: 0009_sync_health_check
Create Date: 2026-05-13 23:00:00.000000

Чтобы дашборд знал источник initial_balance:
- 'tinkoff_derived' — авто-подставлен из portfolio.total_amount при первом sync
- 'manual' — введён юзером (legacy, новые юзеры этого пути не получат)
- NULL — не задан

UI на дашборде использует это поле чтобы:
- для tinkoff_derived показать «Капитал на старт периода: X ₽ (авто)»
- для NULL у manual-юзеров — скрыть ROI/RoR карточки
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0010_account_initial_source"
down_revision: Union[str, Sequence[str], None] = "0009_sync_health_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("initial_balance_source", sa.String(32), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_column("initial_balance_source")

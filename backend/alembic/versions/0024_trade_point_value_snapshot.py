"""Phase 9: point_value snapshot per Trade (для futures)

Revision ID: 0024_trade_point_value_snapshot
Revises: 0023_position_authoritative_fields
Create Date: 2026-05-17 19:30:00.000000

Phase 9 (2026-05-17): для futures Trade сохраняем snapshot point_value,
который использовался при вычислении Trade.pnl. Без snapshot последующее
обновление InstrumentORM.min_price_increment_amount (например, для USD-
denominated контрактов где Tinkoff dynamically обновляет FX-scaling) меняет
исторический P&L закрытых сделок.

Phase 9 audit показал что для acc#4 (Tinkoff API не возвращает spec'ы
expired контрактов, кеш ORM хранит stale значения):
- BBZ4 cache pv=1000, empirical pv=93 (real)
- DXH5 cache pv=1000, empirical pv=1.03 (real)
- ETU5 cache pv=1000, empirical pv=80 (real)
- BBH5 cache pv=1000, empirical pv=102 (real)

`point_value_source` отслеживает откуда взято значение:
- `live_api` — на момент closing был свежий API call
- `cache` — из InstrumentORM cache (доверяем для active контрактов где cache OK)
- `empirical_payment` — |payment|/(qty×price) из BUY/SELL op (fallback для expired)
- `manual_override` — explicit override в `POINT_VALUE_OVERRIDES` (если такой будет)

Empirical pv формула опирается на Tinkoff convention для futures BUY/SELL:
  payment_per_unit = price × point_value
  → pv = |payment| / (qty × price)
Validated на active контрактах (PSU5, GLM6, S0M6, TIZ4): empirical ≈ cache pv ✓
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0024_trade_point_value_snapshot"
down_revision: Union[str, Sequence[str], None] = "0023_position_authoritative_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    # DATA-01: на чистой БД колонки уже создал 0001 (create_all из models).
    if has_column(bind, "trades", "point_value"):
        return

    with op.batch_alter_table("trades", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "point_value",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
                comment="Snapshot point_value at trade close (futures only). RUB per 1 price point.",
            )
        )
        batch.add_column(
            sa.Column(
                "point_value_source",
                sa.String(32),
                nullable=True,
                comment="Origin of point_value: live_api|cache|empirical_payment|manual_override.",
            )
        )


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    if not has_column(bind, "trades", "point_value"):
        return

    with op.batch_alter_table("trades", schema=None) as batch:
        batch.drop_column("point_value_source")
        batch.drop_column("point_value")

"""Phase 7: authoritative Tinkoff fields на PositionORM

Revision ID: 0023_position_authoritative_fields
Revises: 0022_trade_fee_breakdown
Create Date: 2026-05-17 18:00:00.000000

Phase 7 (2026-05-17): добавляем поля которые Tinkoff PortfolioPosition
отдаёт напрямую и которые мы раньше игнорировали:

- `expected_yield_rub` — Tinkoff's authoritative position P&L в рублях
  (≈ -25,671 для S0M6 acc#4). Источник истины для UI «совокупный unrealized
  PnL». Заменяет нашу формулу `(current - avg) × qty × pv` которая для
  USD-denominated futures (XIM6, ETM6) даёт неверный результат из-за
  static point_value vs dynamic FX-adjusted Tinkoff calculation.

- `var_margin_rub` — Tinkoff's intraday variation margin (после последнего
  клиринга, в рублях). Информационное поле; помогает диагностировать.

- `daily_yield_rub` — daily change for the position (в рублях).

После этой миграции [pipeline._replace_positions_from_live] начинает читать
и сохранять эти поля из live Tinkoff portfolio.

Live validation (acc#4, 2026-05-17):
- Σ Position.expected_yield (futures) = -69,125.36 ₽
- Σ closed Trade.net_pnl = -163,350.44 ₽
- orphan adjustments = -17,458 ₽
- Σ = -249,933 ≈ cash_truth -248,553 (diff < 0.6%) — natural convergence.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0023_position_authoritative_fields"
down_revision: Union[str, Sequence[str], None] = "0022_trade_fee_breakdown"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    # DATA-01: на чистой БД колонки уже создал 0001 (create_all из models).
    if has_column(bind, "positions", "expected_yield_rub"):
        return

    with op.batch_alter_table("positions", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "expected_yield_rub",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
                comment="Tinkoff authoritative expected_yield (futures position P&L in RUB).",
            )
        )
        batch.add_column(
            sa.Column(
                "var_margin_rub",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
                comment="Tinkoff variation margin (intraday MTM since last clearing).",
            )
        )
        batch.add_column(
            sa.Column(
                "daily_yield_rub",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
                comment="Tinkoff daily_yield (P&L change since last clearing).",
            )
        )


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    if not has_column(bind, "positions", "expected_yield_rub"):
        return

    with op.batch_alter_table("positions", schema=None) as batch:
        batch.drop_column("daily_yield_rub")
        batch.drop_column("var_margin_rub")
        batch.drop_column("expected_yield_rub")

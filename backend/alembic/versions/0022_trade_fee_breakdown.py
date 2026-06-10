"""TR1.3: per-trade attribution для account-level fees

Revision ID: 0022_trade_fee_breakdown
Revises: 0020_broker_conn_stream_enabled
Create Date: 2026-05-16 21:00:00.000000

Добавляет 4 nullable Decimal колонки в trades для allocation account-level
fees (которые Tinkoff API отдаёт без instrument_uid):

- `varmargin_attributed` — доля account-level varmargin приходящаяся на
   trade (proportional by notional × time).
- `margin_fee_attributed` — доля margin_fee (плата за маржу) на trade.
- `service_fee_attributed` — доля service_fee.
- `other_fees_attributed` — generic tax + прочие account-level расходы.

После attribution recompute Trade.net_pnl уже включает all fees, и:
   Σ Trade.net_pnl ≈ current_portfolio_value - net_deposits (cash truth).

Алгоритм attribution: см. domain/pnl/fee_attribution.py.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0022_trade_fee_breakdown"
down_revision: Union[str, Sequence[str], None] = "0020_broker_conn_stream_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    # DATA-01: на чистой БД колонки уже создал 0001 (create_all из models).
    if has_column(bind, "trades", "varmargin_attributed"):
        return

    with op.batch_alter_table("trades", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "varmargin_attributed",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "margin_fee_attributed",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "service_fee_attributed",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "other_fees_attributed",
                sa.Numeric(precision=18, scale=8),
                nullable=True,
                comment="Generic tax и прочие account-level расходы",
            )
        )


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    if not has_column(bind, "trades", "varmargin_attributed"):
        return

    with op.batch_alter_table("trades", schema=None) as batch:
        batch.drop_column("other_fees_attributed")
        batch.drop_column("service_fee_attributed")
        batch.drop_column("margin_fee_attributed")
        batch.drop_column("varmargin_attributed")

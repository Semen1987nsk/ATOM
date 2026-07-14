"""PR 22: Account.last_portfolio_value + last_portfolio_at

Revision ID: 0011_account_portfolio_snapshot
Revises: 0010_account_initial_source
Create Date: 2026-05-13 23:30:00.000000

Snapshot последнего известного portfolio.total_amount_portfolio от брокера.
Обновляется при каждом sync в pipeline._stage_mark_to_market. Используется
для реконструкции исторических балансов:

    balance_at(D) = last_portfolio_value − Σ payments(op.date > D)

где Σ payments — все операции (buy/sell/varmargin/fee/coupon/dividend/
input/output/inp_multi/tax) после даты D.

Заменяет broken-формулу autoset initial_balance, которая не учитывала
INPUT/OUTPUT-операции и поэтому давала систематически завышенный
старт капитала.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_account_portfolio_snapshot"
down_revision: Union[str, Sequence[str], None] = "0010_account_initial_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import missing_columns

    bind = op.get_bind()
    to_add = missing_columns(
        bind,
        "accounts",
        {
            "last_portfolio_value": sa.Column(
                "last_portfolio_value", sa.Numeric(precision=18, scale=8), nullable=True
            ),
            "last_portfolio_at": sa.Column(
                "last_portfolio_at", sa.DateTime(), nullable=True
            ),
        },
    )
    if not to_add:
        return
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        for col in to_add.values():
            batch_op.add_column(col)


def downgrade() -> None:
    from _guards import has_column

    bind = op.get_bind()
    to_drop = [
        c
        for c in ("last_portfolio_at", "last_portfolio_value")
        if has_column(bind, "accounts", c)
    ]
    if not to_drop:
        return
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        for name in to_drop:
            batch_op.drop_column(name)

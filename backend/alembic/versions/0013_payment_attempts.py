"""PR 26: PaymentAttemptORM — idempotency для YooKassa webhook'ов

Revision ID: 0013_payment_attempts
Revises: 0012_security_tables
Create Date: 2026-05-14 13:00:00.000000

YooKassa повторяет webhook до 30 раз пока не получит 200. Без таблицы
с unique constraint на external_id (=YooKassa payment.id) каждая повторная
доставка → дублирующая активация подписки → двойной charge.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013_payment_attempts"
down_revision: Union[str, Sequence[str], None] = "0012_security_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from _guards import has_table

    bind = op.get_bind()
    # DATA-01: на чистой БД таблицу уже создал 0001 (create_all из models).
    if has_table(bind, "payment_attempts"):
        return

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_payment_attempts_external_id", "payment_attempts", ["external_id"])
    op.create_index("ix_payment_attempts_user", "payment_attempts", ["user_id"])
    op.create_index("ix_payment_attempts_created", "payment_attempts", ["created_at"])


def downgrade() -> None:
    from _guards import has_table

    bind = op.get_bind()
    if not has_table(bind, "payment_attempts"):
        return

    op.drop_index("ix_payment_attempts_created", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_user", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_external_id", table_name="payment_attempts")
    op.drop_table("payment_attempts")

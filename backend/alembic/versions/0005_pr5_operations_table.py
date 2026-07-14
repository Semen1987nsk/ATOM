"""PR 5: operations table for Tinkoff sync (OperationsByCursor → upsert)

Revision ID: 0005_pr5_operations_table
Revises: 0004_broker_v2_schema
Create Date: 2026-05-13 00:00:00.000000

Сырое хранилище операций из T-Invest API. Source of truth для:
* FIFO-движка (PR 7);
* mark-to-market открытых позиций (PR 11);
* истории варм-маржи для фьючерсов (PR 9).

UNIQUE (account_id, operation_id) — Tinkoff гарантирует уникальность
operation_id per broker_account_id, наш account_id (FK на accounts.id)
агрегирует возможно несколько broker-счетов.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005_pr5_operations_table"
down_revision: Union[str, Sequence[str], None] = "0004_broker_v2_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("operations"):
        return

    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker_account_id", sa.String(length=64), nullable=False),
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("parent_operation_id", sa.String(length=64), nullable=True),
        sa.Column("instrument_uid", sa.String(length=64), nullable=True),
        sa.Column("instrument_figi", sa.String(length=32), nullable=True),
        sa.Column("instrument_type", sa.String(length=32), nullable=True),
        sa.Column("operation_type", sa.String(length=48), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_units", sa.Integer(), nullable=True),
        sa.Column("price_nano", sa.Integer(), nullable=True),
        sa.Column("price_currency", sa.String(length=8), nullable=True),
        sa.Column("payment_units", sa.Integer(), nullable=True),
        sa.Column("payment_nano", sa.Integer(), nullable=True),
        sa.Column("payment_currency", sa.String(length=8), nullable=True),
        sa.Column("commission_units", sa.Integer(), nullable=True),
        sa.Column("commission_nano", sa.Integer(), nullable=True),
        sa.Column("commission_currency", sa.String(length=8), nullable=True),
        sa.Column("aci_units", sa.Integer(), nullable=True),
        sa.Column("aci_nano", sa.Integer(), nullable=True),
        sa.Column("aci_currency", sa.String(length=8), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "account_id", "operation_id", name="uq_operations_account_opid"
        ),
    )
    op.create_index(
        "ix_operations_account_executed_at",
        "operations",
        ["account_id", "executed_at"],
        unique=False,
    )
    op.create_index(
        "ix_operations_broker_account_id",
        "operations",
        ["broker_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_operations_instrument_uid",
        "operations",
        ["instrument_uid"],
        unique=False,
    )
    op.create_index(
        "ix_operations_type",
        "operations",
        ["operation_type"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("operations"):
        return

    op.drop_index("ix_operations_type", table_name="operations")
    op.drop_index("ix_operations_instrument_uid", table_name="operations")
    op.drop_index("ix_operations_broker_account_id", table_name="operations")
    op.drop_index("ix_operations_account_executed_at", table_name="operations")
    op.drop_table("operations")

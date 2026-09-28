"""PR 2: broker v2 schema — instruments, positions, token_audit_log + new fields

Revision ID: 0004_broker_v2_schema
Revises: 0003_pr0_trade_data_source
Create Date: 2026-05-09 12:00:00.000000

Подготовка БД к новому Tinkoff sync (PR 5+):

* `broker_connections`: + sync_cursor, key_id, consecutive_failures,
  circuit_open_until, last_audit_at.
* `trades`: + instrument_uid, instrument_figi, position_uid, instrument_type_v2.
* `instruments` (new): кэш справочника.
* `positions` (new): открытые позиции с MTM PnL.
* `token_audit_log` (new): audit вызовов Tinkoff API (без токенов).

SQLite-совместимость: используем `batch_alter_table` и idempotent guard'ы.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_broker_v2_schema"
down_revision: Union[str, Sequence[str], None] = "0003_pr0_trade_data_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ───── 1. broker_connections: новые поля ─────
    bc_columns = {c["name"] for c in inspector.get_columns("broker_connections")}
    new_bc_cols = {
        "sync_cursor": sa.Column("sync_cursor", sa.String(length=256), nullable=True),
        "key_id": sa.Column(
            "key_id",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        "consecutive_failures": sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        "circuit_open_until": sa.Column("circuit_open_until", sa.DateTime(), nullable=True),
        "last_audit_at": sa.Column("last_audit_at", sa.DateTime(), nullable=True),
    }
    missing_bc = {name: col for name, col in new_bc_cols.items() if name not in bc_columns}
    if missing_bc:
        with op.batch_alter_table("broker_connections", schema=None) as batch_op:
            for col in missing_bc.values():
                batch_op.add_column(col)

    # ───── 2. trades: новые поля для UID-based матчинга ─────
    trade_columns = {c["name"] for c in inspector.get_columns("trades")}
    new_trade_cols = {
        "instrument_uid": sa.Column("instrument_uid", sa.String(length=64), nullable=True),
        "instrument_figi": sa.Column("instrument_figi", sa.String(length=32), nullable=True),
        "position_uid": sa.Column("position_uid", sa.String(length=64), nullable=True),
        "instrument_type_v2": sa.Column("instrument_type_v2", sa.String(length=32), nullable=True),
    }
    missing_trade = {name: col for name, col in new_trade_cols.items() if name not in trade_columns}
    if missing_trade:
        with op.batch_alter_table("trades", schema=None) as batch_op:
            for col in missing_trade.values():
                batch_op.add_column(col)

        # Индексы на UID (поиск по инструменту в FIFO-движке).
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("trades")}
        if "ix_trades_instrument_uid" not in existing_indexes:
            op.create_index(
                "ix_trades_instrument_uid",
                "trades",
                ["instrument_uid"],
                unique=False,
            )
        if "ix_trades_position_uid" not in existing_indexes:
            op.create_index(
                "ix_trades_position_uid",
                "trades",
                ["position_uid"],
                unique=False,
            )

    # ───── 3. instruments (cache) ─────
    if not inspector.has_table("instruments"):
        op.create_table(
            "instruments",
            sa.Column("uid", sa.String(length=64), primary_key=True, nullable=False),
            sa.Column("figi", sa.String(length=32), nullable=True),
            sa.Column("ticker", sa.String(length=32), nullable=True),
            sa.Column("class_code", sa.String(length=32), nullable=True),
            sa.Column("instrument_type", sa.String(length=32), nullable=False),
            sa.Column("isin", sa.String(length=32), nullable=True),
            sa.Column("name", sa.String(length=256), nullable=True),
            sa.Column("lot", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="rub"),
            sa.Column("nominal", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("min_price_increment", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("min_price_increment_amount", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("coupon_quantity_per_year", sa.Integer(), nullable=True),
            sa.Column("amortization_flag", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("floating_coupon_flag", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("maturity_date", sa.DateTime(), nullable=True),
            sa.Column("placement_price", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("expiration_date", sa.DateTime(), nullable=True),
            sa.Column("basic_asset_size", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("basic_asset_uid", sa.String(length=64), nullable=True),
            sa.Column("strike_price", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("option_direction", sa.String(length=8), nullable=True),
            sa.Column("option_style", sa.String(length=16), nullable=True),
            sa.Column("option_multiplier", sa.Integer(), nullable=True),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column("cached_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_instruments_figi", "instruments", ["figi"], unique=False)
        op.create_index(
            "ix_instruments_ticker_class",
            "instruments",
            ["ticker", "class_code"],
            unique=False,
        )
        op.create_index(
            "ix_instruments_type",
            "instruments",
            ["instrument_type"],
            unique=False,
        )

    # ───── 4. positions ─────
    if not inspector.has_table("positions"):
        op.create_table(
            "positions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "account_id",
                sa.Integer(),
                sa.ForeignKey("accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("instrument_uid", sa.String(length=64), nullable=False),
            sa.Column("instrument_type", sa.String(length=32), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("avg_entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
            sa.Column("current_price", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("unrealized_pnl", sa.Numeric(precision=18, scale=8), nullable=True),
            sa.Column("last_priced_at", sa.DateTime(), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="rub"),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "account_id",
                "instrument_uid",
                name="uq_positions_account_instrument",
            ),
        )
        op.create_index(
            "ix_positions_account_id",
            "positions",
            ["account_id"],
            unique=False,
        )

    # ───── 5. token_audit_log ─────
    if not inspector.has_table("token_audit_log"):
        op.create_table(
            "token_audit_log",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("user_id_hash", sa.String(length=64), nullable=True),
            sa.Column("method", sa.String(length=64), nullable=False),
            sa.Column("endpoint", sa.String(length=128), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("error_detail", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_token_audit_account_time",
            "token_audit_log",
            ["account_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_token_audit_status",
            "token_audit_log",
            ["status_code"],
            unique=False,
        )
        op.create_index(
            "ix_token_audit_log_created_at",
            "token_audit_log",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("token_audit_log"):
        op.drop_index("ix_token_audit_log_created_at", table_name="token_audit_log")
        op.drop_index("ix_token_audit_status", table_name="token_audit_log")
        op.drop_index("ix_token_audit_account_time", table_name="token_audit_log")
        op.drop_table("token_audit_log")

    if inspector.has_table("positions"):
        op.drop_index("ix_positions_account_id", table_name="positions")
        op.drop_table("positions")

    if inspector.has_table("instruments"):
        op.drop_index("ix_instruments_type", table_name="instruments")
        op.drop_index("ix_instruments_ticker_class", table_name="instruments")
        op.drop_index("ix_instruments_figi", table_name="instruments")
        op.drop_table("instruments")

    trade_indexes = {ix["name"] for ix in inspector.get_indexes("trades")}
    if "ix_trades_instrument_uid" in trade_indexes:
        op.drop_index("ix_trades_instrument_uid", table_name="trades")
    if "ix_trades_position_uid" in trade_indexes:
        op.drop_index("ix_trades_position_uid", table_name="trades")

    trade_columns = {c["name"] for c in inspector.get_columns("trades")}
    drop_trade = [
        "instrument_type_v2",
        "position_uid",
        "instrument_figi",
        "instrument_uid",
    ]
    cols_to_drop_trade = [c for c in drop_trade if c in trade_columns]
    if cols_to_drop_trade:
        with op.batch_alter_table("trades", schema=None) as batch_op:
            for c in cols_to_drop_trade:
                batch_op.drop_column(c)

    bc_columns = {c["name"] for c in inspector.get_columns("broker_connections")}
    drop_bc = [
        "last_audit_at",
        "circuit_open_until",
        "consecutive_failures",
        "key_id",
        "sync_cursor",
    ]
    cols_to_drop_bc = [c for c in drop_bc if c in bc_columns]
    if cols_to_drop_bc:
        with op.batch_alter_table("broker_connections", schema=None) as batch_op:
            for c in cols_to_drop_bc:
                batch_op.drop_column(c)

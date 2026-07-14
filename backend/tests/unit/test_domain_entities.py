"""
Smoke-тесты для domain.entities (Pydantic v2). Проверяем что:

* модели создаются и заполняются;
* `frozen=True` действительно read-only;
* валидация (`quantity > 0` для Trade, `min_length=1` для UID) работает.

Бизнес-логика PnL и FIFO matching — отдельные тесты в PR 7+.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from domain.entities import Instrument, Operation, Position, Trade
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDirection,
)
from domain.value_objects import MoneyValue


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestOperation:
    def test_minimal_operation_ok(self) -> None:
        op = Operation(
            operation_id="op-1",
            account_id="acc-1",
            operation_type=OperationType.BUY,
            state=OperationState.EXECUTED,
            executed_at=_utc(2026, 5, 9, 10, 0, 0),
        )
        assert op.operation_id == "op-1"
        assert op.quantity == 0
        assert op.price is None

    def test_operation_with_money(self) -> None:
        op = Operation(
            operation_id="op-1",
            account_id="acc-1",
            instrument_uid="uid-sber",
            instrument_type=InstrumentType.SHARE,
            operation_type=OperationType.BUY,
            state=OperationState.EXECUTED,
            quantity=100,
            price=MoneyValue(units=270, nano=500_000_000, currency="rub"),
            payment=MoneyValue(units=-27050, nano=0, currency="rub"),
            executed_at=_utc(2026, 5, 9, 10, 0, 0),
        )
        assert op.price is not None
        assert op.price.to_decimal() == Decimal("270.5")
        assert op.payment is not None
        assert op.payment.to_decimal() == Decimal("-27050")

    def test_operation_frozen(self) -> None:
        op = Operation(
            operation_id="op-1",
            account_id="acc-1",
            operation_type=OperationType.BUY,
            state=OperationState.EXECUTED,
            executed_at=_utc(2026, 5, 9, 10, 0, 0),
        )
        with pytest.raises(ValidationError):
            op.operation_id = "changed"  # type: ignore[misc]

    def test_empty_operation_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Operation(
                operation_id="",
                account_id="acc-1",
                operation_type=OperationType.BUY,
                state=OperationState.EXECUTED,
                executed_at=_utc(2026, 5, 9, 10, 0, 0),
            )


class TestTrade:
    def test_open_trade(self) -> None:
        trade = Trade(
            account_id="acc-1",
            instrument_uid="uid-sber",
            instrument_type=InstrumentType.SHARE,
            direction=TradeDirection.LONG,
            quantity=100,
            entry_price=Decimal("270.5"),
            entry_at=_utc(2026, 5, 9, 10, 0, 0),
        )
        assert trade.exit_price is None
        assert trade.exit_at is None
        assert trade.pnl is None

    def test_closed_trade_with_pnl(self) -> None:
        trade = Trade(
            account_id="acc-1",
            instrument_uid="uid-sber",
            instrument_type=InstrumentType.SHARE,
            direction=TradeDirection.LONG,
            quantity=100,
            entry_price=Decimal("270.50"),
            exit_price=Decimal("275.00"),
            entry_at=_utc(2026, 5, 9, 10, 0, 0),
            exit_at=_utc(2026, 5, 9, 14, 0, 0),
            pnl=Decimal("450"),
            net_pnl=Decimal("440.50"),
            commission_total=Decimal("9.50"),
        )
        assert trade.pnl == Decimal("450")
        assert trade.net_pnl == Decimal("440.50")
        assert trade.exit_price > trade.entry_price

    def test_zero_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Trade(
                account_id="acc-1",
                instrument_uid="uid-sber",
                instrument_type=InstrumentType.SHARE,
                direction=TradeDirection.LONG,
                quantity=0,  # gt=0
                entry_price=Decimal("270"),
                entry_at=_utc(2026, 5, 9, 10, 0, 0),
            )


class TestPosition:
    def test_long_position_with_mtm(self) -> None:
        pos = Position(
            account_id="acc-1",
            instrument_uid="uid-sber",
            instrument_type=InstrumentType.SHARE,
            quantity=100,
            avg_entry_price=Decimal("270.50"),
            current_price=Decimal("275.00"),
            unrealized_pnl=Decimal("450"),
            last_priced_at=_utc(2026, 5, 9, 14, 0, 0),
        )
        assert pos.quantity == 100
        assert pos.unrealized_pnl == Decimal("450")

    def test_short_position(self) -> None:
        pos = Position(
            account_id="acc-1",
            instrument_uid="uid-si-fut",
            instrument_type=InstrumentType.FUTURES,
            quantity=-1,  # signed: SHORT
            avg_entry_price=Decimal("85100"),
            extra={"point_value_snapshot": "10.0", "accumulated_varmargin": "1500.0"},
        )
        assert pos.quantity == -1
        assert pos.extra["accumulated_varmargin"] == "1500.0"


class TestInstrument:
    def test_share_instrument(self) -> None:
        inst = Instrument(
            uid="uid-sber",
            figi="BBG004730N88",
            ticker="SBER",
            class_code="TQBR",
            instrument_type=InstrumentType.SHARE,
            isin="RU0009029540",
            name="Сбер Банк",
            lot=10,
        )
        assert inst.lot == 10
        assert inst.amortization_flag is False  # default

    def test_bond_instrument_with_coupons(self) -> None:
        inst = Instrument(
            uid="uid-ofz-26247",
            figi="BBG00X3WDLQ7",
            ticker="SU26247RMFS5",
            instrument_type=InstrumentType.BOND,
            nominal=Decimal("1000"),
            coupon_quantity_per_year=2,
            amortization_flag=False,
            maturity_date=_utc(2039, 5, 11),
        )
        assert inst.nominal == Decimal("1000")
        assert inst.coupon_quantity_per_year == 2

    def test_futures_with_point_value(self) -> None:
        inst = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            ticker="Si-6.25",
            instrument_type=InstrumentType.FUTURES,
            min_price_increment=Decimal("1"),
            min_price_increment_amount=Decimal("10"),
            expiration_date=_utc(2026, 6, 19),
            basic_asset_size=Decimal("1000"),
        )
        assert inst.min_price_increment_amount == Decimal("10")

    def test_option_with_strike(self) -> None:
        inst = Instrument(
            uid="uid-yndx-call-4000",
            instrument_type=InstrumentType.OPTION,
            strike_price=Decimal("4000"),
            option_direction="call",
            option_style="european",
            option_multiplier=100,
            expiration_date=_utc(2026, 6, 19),
            basic_asset_uid="uid-yndx",
        )
        # Опционы часто без figi — это нормально.
        assert inst.figi is None
        assert inst.option_multiplier == 100

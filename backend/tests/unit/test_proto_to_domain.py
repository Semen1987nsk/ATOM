"""
Unit-тесты конвертеров proto → domain. Проверяем:

* `MoneyValue` (proto) ↔ `Decimal` точная конвертация (включая знак),
* `Quotation` отдельно,
* `parse_operation_type/state/instrument_type` устойчивы к пустым/неизвестным
  значениям,
* `operation_from_proto` корректно строит domain.Operation из mock-объекта,
* datetime приходит в UTC.

Используем простые stub-объекты вместо реального protobuf — нам не важна
сериализация, важны только имена и типы атрибутов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import pytest

from adapters.tinkoff.proto_to_domain import (
    instrument_from_proto,
    money_to_decimal,
    money_to_money_value,
    operation_from_proto,
    parse_instrument_type,
    parse_operation_state,
    parse_operation_type,
    quotation_to_decimal,
)
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
)


# ── Простые proto-стабы ──


@dataclass
class _Money:
    units: int = 0
    nano: int = 0
    currency: str = ""


@dataclass
class _Quot:
    units: int = 0
    nano: int = 0


@dataclass
class _OpItem:
    id: str = "op-1"
    broker_account_id: str = "acc-1"
    parent_operation_id: Optional[str] = None
    instrument_uid: Optional[str] = None
    figi: Optional[str] = None
    instrument_type: Any = "share"
    instrument_kind: Any = None
    type: Any = "OPERATION_TYPE_BUY"
    state: Any = "OPERATION_STATE_EXECUTED"
    quantity: int = 0
    price: Optional[_Money] = None
    payment: Optional[_Money] = None
    commission: Optional[_Money] = None
    accrued_int: Optional[_Money] = None
    date: Any = None
    description: Optional[str] = None


# Имитация enum-объекта с .name (frozen для использования как default
# в других dataclass'ах — Python 3.11+ запрещает mutable defaults).
@dataclass(frozen=True)
class _EnumLike:
    name: str

    def __str__(self) -> str:
        return self.name


# ── Money / Quotation ──


class TestMoneyToMoneyValue:
    def test_basic(self) -> None:
        m = _Money(units=1, nano=500_000_000, currency="rub")
        mv = money_to_money_value(m)
        assert mv is not None
        assert mv.to_decimal() == Decimal("1.5")
        assert mv.currency == "rub"

    def test_uppercase_currency_normalized(self) -> None:
        m = _Money(units=1, nano=0, currency="RUB")
        mv = money_to_money_value(m)
        assert mv is not None
        assert mv.currency == "rub"

    def test_empty_treated_as_none(self) -> None:
        m = _Money(units=0, nano=0, currency="")
        assert money_to_money_value(m) is None

    def test_zero_with_currency_kept(self) -> None:
        """Нулевая комиссия не должна быть None — currency задан."""
        m = _Money(units=0, nano=0, currency="rub")
        mv = money_to_money_value(m)
        assert mv is not None
        assert mv.to_decimal() == Decimal("0")

    def test_negative(self) -> None:
        m = _Money(units=-1, nano=-500_000_000, currency="rub")
        mv = money_to_money_value(m)
        assert mv is not None
        assert mv.to_decimal() == Decimal("-1.5")

    def test_money_to_decimal(self) -> None:
        m = _Money(units=27050, nano=0, currency="rub")
        assert money_to_decimal(m) == Decimal("27050")
        assert money_to_decimal(None) is None

    def test_none_input(self) -> None:
        assert money_to_money_value(None) is None


class TestQuotationToDecimal:
    def test_basic(self) -> None:
        q = _Quot(units=85100, nano=500_000_000)
        assert quotation_to_decimal(q) == Decimal("85100.5")

    def test_zero_returns_zero(self) -> None:
        # Quotation(0,0) — это валидное число 0, не None.
        q = _Quot(units=0, nano=0)
        assert quotation_to_decimal(q) == Decimal("0")

    def test_none(self) -> None:
        assert quotation_to_decimal(None) is None


# ── Enum parsers ──


class TestEnumParsers:
    def test_operation_type_buy(self) -> None:
        assert parse_operation_type("OPERATION_TYPE_BUY") == OperationType.BUY

    def test_operation_type_via_enum_like(self) -> None:
        assert (
            parse_operation_type(_EnumLike("OPERATION_TYPE_DIVIDEND"))
            == OperationType.DIVIDEND
        )

    def test_operation_type_unknown_falls_back(self) -> None:
        assert parse_operation_type("OPERATION_TYPE_NONEXISTENT") == OperationType.UNSPECIFIED

    def test_operation_state(self) -> None:
        assert parse_operation_state("OPERATION_STATE_EXECUTED") == OperationState.EXECUTED
        assert parse_operation_state("OPERATION_STATE_CANCELED") == OperationState.CANCELED

    def test_instrument_type_by_proto_name(self) -> None:
        assert parse_instrument_type(_EnumLike("INSTRUMENT_TYPE_BOND")) == InstrumentType.BOND

    def test_instrument_type_by_string(self) -> None:
        # OperationItem.instrument_type — строка типа 'share'.
        assert parse_instrument_type("share") == InstrumentType.SHARE
        assert parse_instrument_type("bond") == InstrumentType.BOND
        assert parse_instrument_type("futures") == InstrumentType.FUTURES

    def test_instrument_type_none(self) -> None:
        assert parse_instrument_type(None) is None


# ── Operation ──


class TestOperationFromProto:
    def test_minimal_buy(self) -> None:
        item = _OpItem(
            id="op-buy-1",
            broker_account_id="2000000",
            instrument_uid="uid-sber",
            figi="BBG004730N88",
            instrument_type="share",
            type="OPERATION_TYPE_BUY",
            state="OPERATION_STATE_EXECUTED",
            quantity=100,
            price=_Money(units=270, nano=500_000_000, currency="rub"),
            payment=_Money(units=-27050, nano=0, currency="rub"),
            commission=_Money(units=0, nano=-29_000_000, currency="rub"),  # -0.029
            date=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        )
        op = operation_from_proto(item)
        assert op.operation_id == "op-buy-1"
        assert op.account_id == "2000000"
        assert op.instrument_uid == "uid-sber"
        assert op.instrument_figi == "BBG004730N88"
        assert op.operation_type == OperationType.BUY
        assert op.state == OperationState.EXECUTED
        assert op.quantity == 100
        assert op.price is not None
        assert op.price.to_decimal() == Decimal("270.5")
        assert op.payment is not None
        assert op.payment.to_decimal() == Decimal("-27050")

    def test_naive_datetime_normalized_to_utc(self) -> None:
        item = _OpItem(
            id="op-1",
            broker_account_id="acc-1",
            type="OPERATION_TYPE_BUY",
            state="OPERATION_STATE_EXECUTED",
            date=datetime(2026, 5, 9, 10, 0),  # naive
        )
        op = operation_from_proto(item)
        assert op.executed_at.tzinfo is not None
        assert op.executed_at == datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)

    def test_account_id_fallback(self) -> None:
        """Если в OperationItem нет broker_account_id, берём из аргумента."""
        item = _OpItem(
            id="op-1",
            broker_account_id="",
            type="OPERATION_TYPE_BUY",
            state="OPERATION_STATE_EXECUTED",
            date=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        )
        op = operation_from_proto(item, account_id="external-acc")
        assert op.account_id == "external-acc"

    def test_dividend_no_instrument_uid(self) -> None:
        """Дивиденд без instrument_uid — это допустимо."""
        item = _OpItem(
            id="op-div",
            broker_account_id="acc-1",
            type="OPERATION_TYPE_DIVIDEND",
            state="OPERATION_STATE_EXECUTED",
            payment=_Money(units=100, nano=0, currency="rub"),
            date=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        )
        op = operation_from_proto(item)
        assert op.operation_type == OperationType.DIVIDEND
        assert op.instrument_uid is None


# ── Instrument ──


@dataclass
class _Share:
    figi: str = "BBG004730N88"
    ticker: str = "SBER"
    class_code: str = "TQBR"
    isin: str = "RU0009029540"
    lot: int = 10
    currency: str = "rub"
    name: str = "Сбер"
    nominal: Optional[_Quot] = None
    min_price_increment: Optional[_Quot] = None
    uid: str = "uid-sber"


@dataclass
class _Bond:
    figi: str = "BBG00X3WDLQ7"
    ticker: str = "SU26247RMFS5"
    class_code: str = "TQOB"
    isin: str = "RU000A105A87"
    lot: int = 1
    currency: str = "rub"
    name: str = "ОФЗ 26247"
    nominal: Optional[_Quot] = None
    min_price_increment: Optional[_Quot] = None
    coupon_quantity_per_year: int = 2
    maturity_date: Optional[datetime] = None
    placement_price: Optional[_Money] = None
    floating_coupon_flag: bool = False
    amortization_flag: bool = False
    uid: str = "uid-ofz-26247"


@dataclass
class _Future:
    figi: str = "FUTSI0625"
    ticker: str = "Si-6.25"
    class_code: str = "SPBFUT"
    isin: str = ""
    lot: int = 1
    currency: str = "rub"
    name: str = "Фьючерс Si"
    min_price_increment: Optional[_Quot] = None
    min_price_increment_amount: Optional[_Money] = None
    expiration_date: Optional[datetime] = None
    basic_asset: str = "Si"
    basic_asset_size: Optional[_Quot] = None
    basic_asset_position_uid: str = ""
    uid: str = "uid-si"


@dataclass
class _Option:
    figi: str = ""  # часто пусто у опционов
    ticker: str = "YDU4-Call4000"
    class_code: str = "SPBOPT"
    isin: str = ""
    lot: int = 1
    currency: str = "rub"
    name: str = "YNDX call 4000"
    direction: Any = field(default_factory=lambda: _EnumLike("OPTION_DIRECTION_CALL"))
    style: Any = field(default_factory=lambda: _EnumLike("OPTION_STYLE_EUROPEAN"))
    strike_price: Optional[_Quot] = None
    basic_asset_size: Optional[_Quot] = None
    basic_asset_position_uid: str = "uid-yndx"
    expiration_date: Optional[datetime] = None
    uid: str = "uid-yndx-call-4000"


class TestInstrumentFromProto:
    def test_share(self) -> None:
        raw = _Share(min_price_increment=_Quot(units=0, nano=10_000_000))  # 0.01 RUB
        inst = instrument_from_proto(raw, InstrumentType.SHARE)
        assert inst.uid == "uid-sber"
        assert inst.ticker == "SBER"
        assert inst.lot == 10
        assert inst.min_price_increment == Decimal("0.01")
        assert inst.amortization_flag is False  # default

    def test_bond_with_amortization(self) -> None:
        raw = _Bond(
            nominal=_Quot(units=1000, nano=0),
            amortization_flag=True,
            maturity_date=datetime(2039, 5, 11, tzinfo=timezone.utc),
        )
        inst = instrument_from_proto(raw, InstrumentType.BOND)
        assert inst.nominal == Decimal("1000")
        assert inst.amortization_flag is True
        assert inst.coupon_quantity_per_year == 2
        assert inst.maturity_date is not None
        assert inst.maturity_date.year == 2039

    def test_future_with_point_value(self) -> None:
        raw = _Future(
            min_price_increment=_Quot(units=1, nano=0),
            min_price_increment_amount=_Money(units=10, nano=0, currency="rub"),
            expiration_date=datetime(2026, 6, 19, tzinfo=timezone.utc),
            basic_asset_size=_Quot(units=1000, nano=0),
        )
        inst = instrument_from_proto(raw, InstrumentType.FUTURES)
        assert inst.min_price_increment == Decimal("1")
        assert inst.min_price_increment_amount == Decimal("10")
        assert inst.basic_asset_size == Decimal("1000")
        assert inst.expiration_date is not None

    def test_option_call(self) -> None:
        raw = _Option(
            strike_price=_Quot(units=4000, nano=0),
            basic_asset_size=_Quot(units=100, nano=0),
            expiration_date=datetime(2026, 6, 19, tzinfo=timezone.utc),
        )
        inst = instrument_from_proto(raw, InstrumentType.OPTION)
        assert inst.uid == "uid-yndx-call-4000"
        # Опционы часто без figi → нормально что None.
        assert inst.figi is None or inst.figi == ""
        assert inst.strike_price == Decimal("4000")
        assert inst.option_direction == "call"
        assert inst.option_style == "european"
        assert inst.option_multiplier == 100  # вычислен из basic_asset_size
        assert inst.basic_asset_uid == "uid-yndx"

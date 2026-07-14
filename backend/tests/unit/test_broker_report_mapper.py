"""
PR 26 (Phase 3) — unit tests для BrokerReport mapper + nano bounds check (T5).

Покрывает:
- broker_report_trade_from_proto: все поля корректно конвертируются
- _clamp_nano: T5 fix — malformed nano > 1e9 → warn + clamp
- _normalize_direction: кириллические execute_sign ('Б'/'П') → buy/sell
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import pytest

from adapters.tinkoff.proto_to_domain import (
    _clamp_nano,
    _normalize_direction,
    broker_report_trade_from_proto,
    money_to_money_value,
    quotation_to_decimal,
)


@dataclass
class _Money:
    units: int = 0
    nano: int = 0
    currency: str = "rub"


@dataclass
class _Quot:
    units: int = 0
    nano: int = 0


@dataclass
class _BrokerReportRow:
    trade_id: str = "trade-1"
    order_id: Optional[str] = "order-1"
    figi: Optional[str] = "BBG004730N88"
    ticker: Optional[str] = "SBER"
    name: Optional[str] = "Сбербанк"
    class_code: Optional[str] = "TQBR"
    execute_sign: Optional[str] = "Б"
    exchange: Optional[str] = "MOEX"
    trade_datetime: datetime = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    quantity: int = 10
    price: Optional[_Money] = None
    order_amount: Optional[_Money] = None
    total_order_amount: Optional[_Money] = None
    aci_value: Optional[_Money] = None
    broker_commission: Optional[_Money] = None
    exchange_commission: Optional[_Money] = None
    exchange_clearing_commission: Optional[_Money] = None
    repo_rate: Optional[_Quot] = None
    party: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# _clamp_nano (T5 fix)
# ════════════════════════════════════════════════════════════════════════


class TestClampNano:
    def test_in_bounds_unchanged(self):
        assert _clamp_nano(500_000_000, units=1) == 500_000_000

    def test_max_value_unchanged(self):
        assert _clamp_nano(999_999_999, units=1) == 999_999_999

    def test_negative_in_bounds_unchanged(self):
        assert _clamp_nano(-500_000_000, units=-1) == -500_000_000

    def test_zero_unchanged(self):
        assert _clamp_nano(0, units=0) == 0

    def test_overflow_clamped_positive(self):
        # nano=2_000_000_000 → должно зажаться до 999_999_999, не давать ×10
        result = _clamp_nano(2_000_000_000, units=1)
        assert result == 999_999_999

    def test_overflow_clamped_negative(self):
        result = _clamp_nano(-2_000_000_000, units=-1)
        assert result == -999_999_999

    def test_money_with_overflow_nano_clamped(self):
        """E2E: malformed nano не даёт portfolio value ×10 (T5 баг)."""
        bad_money = _Money(units=1000, nano=2_000_000_000, currency="rub")
        mv = money_to_money_value(bad_money)
        assert mv is not None
        # До фикса было бы 1000 + 2 = 1002 RUB. После фикса 1000.999999... RUB.
        assert mv.to_decimal() < Decimal("1002")
        assert mv.to_decimal() > Decimal("1000.99")


# ════════════════════════════════════════════════════════════════════════
# _normalize_direction
# ════════════════════════════════════════════════════════════════════════


class TestNormalizeDirection:
    def test_cyrillic_buy(self):
        assert _normalize_direction("Б") == "buy"

    def test_cyrillic_sell(self):
        assert _normalize_direction("П") == "sell"

    def test_latin_buy(self):
        assert _normalize_direction("B") == "buy"

    def test_latin_sell(self):
        assert _normalize_direction("S") == "sell"

    def test_word_buy(self):
        assert _normalize_direction("buy") == "buy"
        assert _normalize_direction("BUY") == "buy"

    def test_word_sell(self):
        assert _normalize_direction("sell") == "sell"
        assert _normalize_direction("SELL") == "sell"

    def test_empty(self):
        assert _normalize_direction("") is None
        assert _normalize_direction(None) is None

    def test_unknown(self):
        assert _normalize_direction("X") is None


# ════════════════════════════════════════════════════════════════════════
# broker_report_trade_from_proto
# ════════════════════════════════════════════════════════════════════════


class TestBrokerReportTradeFromProto:
    def test_basic_buy_trade(self):
        row = _BrokerReportRow(
            trade_id="t-001",
            execute_sign="Б",
            ticker="SBER",
            quantity=10,
            price=_Money(units=200, nano=500_000_000, currency="rub"),
            order_amount=_Money(units=2005, nano=0, currency="rub"),
            total_order_amount=_Money(units=2005, nano=0, currency="rub"),
            broker_commission=_Money(units=0, nano=600_000_000, currency="rub"),  # 0.6 ₽
        )
        result = broker_report_trade_from_proto(row)

        assert result.trade_id == "t-001"
        assert result.direction == "buy"
        assert result.ticker == "SBER"
        assert result.quantity == 10
        assert result.price == Decimal("200.5")
        assert result.order_amount == Decimal("2005")
        assert result.broker_commission == Decimal("0.6")
        assert result.currency == "rub"

    def test_sell_trade(self):
        row = _BrokerReportRow(
            trade_id="t-002",
            execute_sign="П",
            quantity=5,
            price=_Money(units=210, nano=0, currency="rub"),
        )
        result = broker_report_trade_from_proto(row)
        assert result.direction == "sell"

    def test_none_money_fields_become_none(self):
        row = _BrokerReportRow(trade_id="t-003")
        result = broker_report_trade_from_proto(row)
        assert result.price is None
        assert result.broker_commission is None
        assert result.aci_value is None

    def test_bond_with_aci(self):
        """Облигация: aci_value заполнен, total = order + aci."""
        row = _BrokerReportRow(
            trade_id="bond-1",
            ticker="SU26238RMFS4",
            execute_sign="Б",
            quantity=10,
            price=_Money(units=950, nano=0, currency="rub"),  # 95% от 1000 nominal
            order_amount=_Money(units=9500, nano=0, currency="rub"),
            aci_value=_Money(units=12, nano=500_000_000, currency="rub"),  # 12.5 ₽
            total_order_amount=_Money(units=9512, nano=500_000_000, currency="rub"),
        )
        result = broker_report_trade_from_proto(row)
        assert result.order_amount == Decimal("9500")
        assert result.aci_value == Decimal("12.5")
        assert result.total_order_amount == Decimal("9512.5")

    def test_currency_from_price(self):
        row = _BrokerReportRow(
            trade_id="t-usd",
            price=_Money(units=100, nano=0, currency="usd"),
        )
        result = broker_report_trade_from_proto(row)
        assert result.currency == "usd"

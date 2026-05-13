"""
Unit-тесты value_objects: критическая проверка точности конвертации
MoneyValue / Quotation ↔ Decimal.

Любой баг здесь = неверный PnL у пользователя. Проверяем граничные случаи:
* нулевые значения,
* отрицательные с обоими знаками (units и nano одного знака),
* большие значения (миллионы рублей).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.value_objects import InstrumentRef, MoneyValue, Quotation


class TestMoneyValueRoundtrip:
    @pytest.mark.parametrize(
        "units,nano,expected",
        [
            (1, 500_000_000, Decimal("1.5")),
            (0, 0, Decimal("0")),
            (1000, 0, Decimal("1000")),
            (-1, -500_000_000, Decimal("-1.5")),
            (0, 100_000_000, Decimal("0.1")),
            (0, -100_000_000, Decimal("-0.1")),
            (0, 1, Decimal("0.000000001")),  # 1 nano
            (123456, 789_012_345, Decimal("123456.789012345")),
        ],
    )
    def test_to_decimal_known_values(self, units: int, nano: int, expected: Decimal) -> None:
        mv = MoneyValue(units=units, nano=nano, currency="rub")
        assert mv.to_decimal() == expected

    @pytest.mark.parametrize(
        "value,currency",
        [
            (Decimal("1.5"), "rub"),
            (Decimal("0"), "rub"),
            (Decimal("-1.5"), "usd"),
            (Decimal("123456.789012345"), "rub"),
            (Decimal("-0.000000001"), "rub"),
            (Decimal("1000000.0"), "eur"),
        ],
    )
    def test_from_decimal_roundtrip(self, value: Decimal, currency: str) -> None:
        """Decimal → MoneyValue → Decimal: значение точно совпадает."""
        mv = MoneyValue.from_decimal(value, currency)
        assert mv.to_decimal() == value
        assert mv.currency == currency

    def test_negative_decimal_roundtrip_keeps_sign(self) -> None:
        """Знак сохраняется на обоих компонентах (units и nano)."""
        mv = MoneyValue.from_decimal(Decimal("-1.5"), "rub")
        assert mv.units == -1
        assert mv.nano == -500_000_000
        assert mv.to_decimal() == Decimal("-1.5")

    def test_immutability(self) -> None:
        mv = MoneyValue(units=1, nano=0, currency="rub")
        with pytest.raises((AttributeError, Exception)):
            mv.units = 99  # type: ignore[misc]

    def test_str_format(self) -> None:
        mv = MoneyValue(units=1500, nano=500_000_000, currency="rub")
        assert "1500.5" in str(mv)
        assert "RUB" in str(mv)


class TestQuotationRoundtrip:
    @pytest.mark.parametrize(
        "value",
        [
            Decimal("85100.5"),  # фьючерс Si
            Decimal("0.000000001"),
            Decimal("-100.25"),
            Decimal("0"),
            Decimal("100"),  # шаг цены
        ],
    )
    def test_quotation_roundtrip(self, value: Decimal) -> None:
        q = Quotation.from_decimal(value)
        assert q.to_decimal() == value


class TestInstrumentRef:
    def test_minimal_ref(self) -> None:
        ref = InstrumentRef(uid="some-uid")
        assert ref.uid == "some-uid"
        assert ref.figi is None
        assert ref.instrument_type is None

    def test_with_figi(self) -> None:
        ref = InstrumentRef(uid="some-uid", figi="BBG004730N88", instrument_type="share")
        assert "BBG004730N88" in str(ref)
        assert ref.instrument_type == "share"

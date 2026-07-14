"""MATH-11: weighted-avg PV across all entry slices (не first-slice).

Scaled-in трейды (1 lot @ price1, потом 9 lots @ price2) раньше получали
pv от первого slice'а, что давало bias на индексных фьючерсах где cached
pv (Tinkoff metadata) врёт. Теперь берём Σ (pv_i × qty_i) / Σ qty_i.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.entities import Instrument
from domain.enums import InstrumentType, TradeDirection
from domain.pnl.base import ExitFill, FillSlice, FifoLot, MatchedTrade
from domain.pnl.futures import FuturesPnLCalculator

UTC = timezone.utc


def _slice(price: Decimal, qty: int, payment_per_unit: Decimal, op_id: str) -> FillSlice:
    """FillSlice со сконфигурированным empirical pv = |payment| / price."""
    lot = FifoLot(
        operation_id=op_id,
        direction=TradeDirection.LONG,
        quantity_remaining=0,
        quantity_original=qty,
        price_per_unit=price,
        payment_per_unit=payment_per_unit,
        commission_per_unit=Decimal(0),
        executed_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    return FillSlice(lot=lot, matched_qty=qty)


def _matched_long_two_slices(
    slice1: FillSlice, slice2: FillSlice, exit_price: Decimal
) -> MatchedTrade:
    total_qty = slice1.matched_qty + slice2.matched_qty
    exit_fill = ExitFill(
        operation_id="sell1",
        quantity=total_qty,
        price_per_unit=exit_price,
        payment_per_unit=exit_price,  # знак для long-exit положительный
        commission_per_unit=Decimal(0),
        executed_at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    return MatchedTrade(
        direction=TradeDirection.LONG,
        entry_slices=(slice1, slice2),
        exit=exit_fill,
        instrument_uid="uid-test-futures",
        currency="rub",
    )


def _instr_with_cached_pv(cached_pv: Decimal) -> Instrument:
    """Instrument где cached pv = min_pi_amt / min_pi."""
    return Instrument(
        uid="uid-test-futures",
        figi="FUT-TEST",
        instrument_type=InstrumentType.FUTURES,
        min_price_increment=Decimal("1"),
        min_price_increment_amount=cached_pv,
    )


class TestResolvePvWeighted:
    def test_weighted_avg_across_two_slices(self) -> None:
        """MATH-11: 1 lot @ price=100 (pv=1), 9 lots @ price=110 (pv=10)
        → weighted = (1×1 + 10×9) / 10 = 9.1.
        First-slice бы дал 1 (старое поведение)."""
        # Slice 1: 1 lot at price=100, payment_per_unit=-100 → empirical pv = 1
        s1 = _slice(price=Decimal("100"), qty=1, payment_per_unit=Decimal("-100"), op_id="b1")
        # Slice 2: 9 lots at price=110, payment_per_unit=-1100 → empirical pv = 10
        s2 = _slice(price=Decimal("110"), qty=9, payment_per_unit=Decimal("-1100"), op_id="b2")
        matched = _matched_long_two_slices(s1, s2, exit_price=Decimal("120"))
        # Cached pv = 1 (наивный, ведёт себя как индексный фьючерс
        # где Tinkoff metadata неправильное). Drift между empirical=9.1 и
        # cached=1 — огромный → empirical wins.
        instr = _instr_with_cached_pv(Decimal("1"))
        pv = FuturesPnLCalculator._resolve_pv(matched, instr)
        # Weighted = (1×1 + 10×9) / (1 + 9) = 91 / 10 = 9.1
        assert pv == pytest.approx(Decimal("9.1"), abs=Decimal("0.01")), (
            f"weighted-avg pv должно быть 9.1, получили {pv}"
        )

    def test_single_slice_falls_back_to_old_behavior(self) -> None:
        """С одним slice — weighted-avg = pv этого slice'а
        (формула идентична старой first-slice)."""
        s1 = _slice(price=Decimal("100"), qty=5, payment_per_unit=Decimal("-100"), op_id="b1")
        exit_fill = ExitFill(
            operation_id="sell1",
            quantity=5,
            price_per_unit=Decimal("110"),
            payment_per_unit=Decimal("110"),
            commission_per_unit=Decimal(0),
            executed_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        matched = MatchedTrade(
            direction=TradeDirection.LONG,
            entry_slices=(s1,),
            exit=exit_fill,
            instrument_uid="uid-test-futures",
            currency="rub",
        )
        # Cached = 5 (далеко от empirical=1 → drift > 5% → empirical wins)
        instr = _instr_with_cached_pv(Decimal("5"))
        pv = FuturesPnLCalculator._resolve_pv(matched, instr)
        assert pv == pytest.approx(Decimal("1"), abs=Decimal("0.01")), (
            f"single-slice pv должно быть 1 (empirical), получили {pv}"
        )

    def test_cached_wins_when_drift_small(self) -> None:
        """Если weighted empirical в пределах 5% от cached — оставляем cached."""
        # Slice 1: pv = 1
        s1 = _slice(price=Decimal("100"), qty=1, payment_per_unit=Decimal("-100"), op_id="b1")
        # Slice 2: pv = 1.02 (немного отличается)
        s2 = _slice(price=Decimal("100"), qty=1, payment_per_unit=Decimal("-102"), op_id="b2")
        matched = _matched_long_two_slices(s1, s2, exit_price=Decimal("105"))
        instr = _instr_with_cached_pv(Decimal("1"))
        pv = FuturesPnLCalculator._resolve_pv(matched, instr)
        # weighted = (1 + 1.02) / 2 = 1.01 — drift 1% < 5% → cached wins
        assert pv == Decimal("1"), (
            f"при малом drift'е cached pv должно выиграть, получили {pv}"
        )

    def test_first_slice_bias_eliminated(self) -> None:
        """Регрессия: при scaled-in entry старая формула брала только pv
        первого slice'а. Если первый slice был «нерепрезентативно мелким»
        с empirical pv близким к cached — старая формула не выбирала
        empirical, теряя реальную поправку. После MATH-11 weighted-avg
        правильно отражает основную массу позиции."""
        # Slice 1: 1 lot, pv близко к cached (1) — старая формула вернула
        # бы cached.
        s1 = _slice(price=Decimal("100"), qty=1, payment_per_unit=Decimal("-100"), op_id="b1")
        # Slice 2: 99 lots, pv = 1000 — реальная масса позиции.
        s2 = _slice(
            price=Decimal("100"),
            qty=99,
            payment_per_unit=Decimal("-100000"),
            op_id="b2",
        )
        matched = _matched_long_two_slices(s1, s2, exit_price=Decimal("105"))
        instr = _instr_with_cached_pv(Decimal("1"))  # cached врёт
        pv = FuturesPnLCalculator._resolve_pv(matched, instr)
        # Weighted = (1×1 + 1000×99) / 100 = 990.01 → empirical wins
        assert pv > Decimal("900"), (
            f"weighted-avg должен подхватить массу второго slice'а, "
            f"получили {pv} (старая формула вернула бы ~1)"
        )

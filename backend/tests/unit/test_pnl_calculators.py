"""
Unit-тесты per-instrument PnL калькуляторов (PR 8/9/10).

Сценарии:

* Bonds: ОФЗ с двумя купонами, корп. с амортизацией, удержание до погашения,
  купонный налог.
* Futures: фьючерс с положительной и отрицательной варм-маржей, фильтр по
  figi/uid.
* Options: купить call → продать call, экспирация OTM (всё пропало), ITM
  с settlement payment.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from domain.entities import Instrument, Operation
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
)
from domain.pnl.base import ExitFill, FillSlice, FifoLot, MatchedTrade
from domain.pnl.bonds import BondsPnLCalculator
from domain.pnl.futures import FuturesPnLCalculator
from domain.pnl.options import OptionsPnLCalculator
from domain.enums import TradeDirection
from domain.value_objects import MoneyValue


UTC = timezone.utc


def _op(
    op_id: str,
    type_: OperationType,
    payment: Decimal,
    *,
    instrument_uid: str | None = "uid-bond",
    figi: str | None = None,
    executed_at: datetime | None = None,
) -> Operation:
    return Operation(
        operation_id=op_id,
        account_id="2000000",
        instrument_uid=instrument_uid,
        instrument_figi=figi,
        operation_type=type_,
        state=OperationState.EXECUTED,
        quantity=0,
        payment=MoneyValue.from_decimal(payment, "rub"),
        executed_at=executed_at or datetime(2026, 5, 9, 10, 0, tzinfo=UTC),
    )


def _matched(
    *,
    instrument_uid: str,
    entry_price: Decimal,
    entry_qty: int,
    exit_price: Decimal,
    direction: TradeDirection = TradeDirection.LONG,
    entry_at: datetime | None = None,
    exit_at: datetime | None = None,
    entry_op_id: str = "buy1",
    exit_op_id: str = "sell1",
) -> MatchedTrade:
    sign_entry = -1 if direction == TradeDirection.LONG else 1
    sign_exit = 1 if direction == TradeDirection.LONG else -1
    entry_lot = FifoLot(
        operation_id=entry_op_id,
        direction=direction,
        quantity_remaining=0,
        quantity_original=entry_qty,
        price_per_unit=entry_price,
        payment_per_unit=Decimal(sign_entry) * entry_price,
        commission_per_unit=Decimal(0),
        executed_at=entry_at or datetime(2026, 5, 1, tzinfo=UTC),
    )
    exit_fill = ExitFill(
        operation_id=exit_op_id,
        quantity=entry_qty,
        price_per_unit=exit_price,
        payment_per_unit=Decimal(sign_exit) * exit_price,
        commission_per_unit=Decimal(0),
        executed_at=exit_at or datetime(2026, 5, 10, tzinfo=UTC),
    )
    return MatchedTrade(
        direction=direction,
        entry_slices=(FillSlice(lot=entry_lot, matched_qty=entry_qty),),
        exit=exit_fill,
        instrument_uid=instrument_uid,
        currency="rub",
    )


# ── Bonds ────────────────────────────────────────────────────────────


class TestBonds:
    def test_body_pnl_payment_based(self) -> None:
        calc = BondsPnLCalculator()
        instr = Instrument(uid="uid-ofz", instrument_type=InstrumentType.BOND)
        m = _matched(
            instrument_uid="uid-ofz",
            entry_price=Decimal("950"),
            entry_qty=10,
            exit_price=Decimal("980"),
        )
        gross, net = calc.compute(m, instr, extra_operations=[])
        # gross = +9800 - 9500 = 300
        assert gross == Decimal("300")
        assert net == Decimal("300")

    def test_two_coupons_added_to_net(self) -> None:
        calc = BondsPnLCalculator()
        instr = Instrument(uid="uid-ofz", instrument_type=InstrumentType.BOND)
        entry_at = datetime(2026, 1, 1, tzinfo=UTC)
        exit_at = datetime(2026, 12, 31, tzinfo=UTC)
        m = _matched(
            instrument_uid="uid-ofz",
            entry_price=Decimal("950"),
            entry_qty=10,
            exit_price=Decimal("950"),  # ноль body PnL
            entry_at=entry_at,
            exit_at=exit_at,
        )
        extras = [
            _op(
                "c1",
                OperationType.COUPON,
                Decimal("450"),
                instrument_uid="uid-ofz",
                executed_at=entry_at + timedelta(days=180),
            ),
            _op(
                "c2",
                OperationType.COUPON,
                Decimal("450"),
                instrument_uid="uid-ofz",
                executed_at=entry_at + timedelta(days=360),
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert gross == Decimal("0")
        assert net == Decimal("900")

    def test_coupon_tax_subtracted(self) -> None:
        calc = BondsPnLCalculator()
        instr = Instrument(uid="uid-ofz", instrument_type=InstrumentType.BOND)
        m = _matched(
            instrument_uid="uid-ofz",
            entry_price=Decimal("950"),
            entry_qty=10,
            exit_price=Decimal("950"),
        )
        extras = [
            _op("c1", OperationType.COUPON, Decimal("100"), instrument_uid="uid-ofz"),
            _op(
                "t1",
                OperationType.BOND_TAX,
                Decimal("-13"),  # 13% от 100
                instrument_uid="uid-ofz",
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert gross == Decimal("0")
        assert net == Decimal("87")

    def test_amortization_in_window(self) -> None:
        calc = BondsPnLCalculator()
        instr = Instrument(
            uid="uid-amort",
            instrument_type=InstrumentType.BOND,
            amortization_flag=True,
        )
        m = _matched(
            instrument_uid="uid-amort",
            entry_price=Decimal("1000"),
            entry_qty=5,
            exit_price=Decimal("950"),
        )
        extras = [
            _op(
                "amort1",
                # PR 24: PARTIAL_BOND_REPAYMENT не существует в SDK; амортизация
                # приходит как BOND_REPAYMENT (без full).
                OperationType.BOND_REPAYMENT,
                Decimal("250"),  # 50 руб × 5 шт
                instrument_uid="uid-amort",
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        # body = (950-1000)*5 = -250 ⇒ gross -250.
        assert gross == Decimal("-250")
        # net = -250 + 250 (амортизация) = 0.
        assert net == Decimal("0")

    def test_extras_for_other_instrument_ignored(self) -> None:
        """Купон по другой облигации не должен попадать в этот трейд."""
        calc = BondsPnLCalculator()
        instr = Instrument(uid="uid-A", instrument_type=InstrumentType.BOND)
        m = _matched(
            instrument_uid="uid-A",
            entry_price=Decimal("1000"),
            entry_qty=1,
            exit_price=Decimal("1000"),
        )
        extras = [
            _op("c1", OperationType.COUPON, Decimal("999"), instrument_uid="uid-OTHER"),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert gross == Decimal("0")
        assert net == Decimal("0")


# ── Futures ──────────────────────────────────────────────────────────


class TestFutures:
    def test_body_from_prices_phase8(self) -> None:
        """Phase 8 (2026-05-17): body = (exit − entry) × qty × point_value × sign.

        Прямой расчёт body P&L из цен. Математическое тождество с MOEX
        variation margin telescoping sum (см. domain/pnl/futures.py docstring
        + plan Phase 8). Без min_price_increment* → pv fallback = 1.
        """
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            instrument_type=InstrumentType.FUTURES,
        )
        m = _matched(
            instrument_uid="uid-si",
            entry_price=Decimal("85000"),
            entry_qty=1,
            exit_price=Decimal("86000"),
        )
        gross, net = calc.compute(m, instr, extra_operations=[])
        # Phase 8: body = (86000 − 85000) × 1 × 1 (pv fallback) × +1 (LONG) = 1000.
        assert gross == Decimal("1000")
        assert net == Decimal("1000")  # commission=0 в этом тесте

    def test_body_with_explicit_point_value(self) -> None:
        """Phase 8: SiH6-style контракт с pv ≠ 1.

        min_price_increment=1, min_price_increment_amount=100 → cached pv = 100.
        Real Tinkoff payment для Si embeds pv: payment = -qty×price×pv =
        -1×85000×100 = -8,500,000. Empirical pv = |payment|/price = 100 → ≈
        cached → drift < 5% → cached wins.

        body = (86000 − 85000) × 1 × 100 = +100,000 ₽.
        """
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            instrument_type=InstrumentType.FUTURES,
            min_price_increment=Decimal("1"),
            min_price_increment_amount=Decimal("100"),
        )
        # Реалистичный payment_per_unit: для Si pv=100 → entry payment = -8,500,000
        entry_lot = FifoLot(
            operation_id="buy1",
            direction=TradeDirection.LONG,
            quantity_remaining=0,
            quantity_original=1,
            price_per_unit=Decimal("85000"),
            payment_per_unit=Decimal("-8500000"),  # 85000 × 100 × sign(BUY)
            commission_per_unit=Decimal(0),
            executed_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        exit_fill = ExitFill(
            operation_id="sell1",
            quantity=1,
            price_per_unit=Decimal("86000"),
            payment_per_unit=Decimal("8600000"),
            commission_per_unit=Decimal(0),
            executed_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        m = MatchedTrade(
            direction=TradeDirection.LONG,
            entry_slices=(FillSlice(lot=entry_lot, matched_qty=1),),
            exit=exit_fill,
            instrument_uid="uid-si",
            currency="rub",
        )
        gross, net = calc.compute(m, instr, extra_operations=[])
        assert gross == Decimal("100000")
        assert net == Decimal("100000")

    def test_body_short_direction(self) -> None:
        """Phase 8: SHORT — entry высоко, exit низко → body > 0.

        SHORT body = (exit − entry) × qty × pv × −1 = (low − high) × qty × pv × −1.
        Для прибыльного шорта (high → low): negative × negative = positive.
        """
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            instrument_type=InstrumentType.FUTURES,
        )
        m = _matched(
            instrument_uid="uid-si",
            entry_price=Decimal("86000"),  # SHORT в высокой
            entry_qty=1,
            exit_price=Decimal("85000"),   # covered в низкой
            direction=TradeDirection.SHORT,
        )
        gross, net = calc.compute(m, instr, extra_operations=[])
        # body = (85000 − 86000) × 1 × 1 × (−1) = +1000
        assert gross == Decimal("1000")
        assert net == Decimal("1000")

    def test_varmargin_NOT_added_to_net_phase8(self) -> None:
        """Phase 8: FuturesPnLCalculator не добавляет varmargin к net.

        body = (exit − entry) × qty × pv уже включает ВСЕ varmargin
        в окне entry→exit (telescoping identity). Varmargin для OPEN
        trades attribute'тся через fee_attribution (Phase 8.2 skip closed).
        """
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            instrument_type=InstrumentType.FUTURES,
        )
        entry_at = datetime(2026, 5, 1, tzinfo=UTC)
        exit_at = datetime(2026, 5, 3, tzinfo=UTC)
        m = _matched(
            instrument_uid="uid-si",
            entry_price=Decimal("85000"),
            entry_qty=1,
            exit_price=Decimal("85100"),
            entry_at=entry_at,
            exit_at=exit_at,
        )
        extras = [
            _op("vm1", OperationType.ACCRUING_VARMARGIN, Decimal("1200"),
                instrument_uid="uid-si", executed_at=entry_at + timedelta(hours=12)),
            _op("vm2", OperationType.WRITING_OFF_VARMARGIN, Decimal("-500"),
                instrument_uid="uid-si", executed_at=entry_at + timedelta(hours=36)),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        # Phase 8: body = (85100 − 85000) × 1 × 1 × +1 = 100.
        # Varmargin в extras игнорируется compute() (attribution отдельно).
        assert gross == Decimal("100")
        assert net == Decimal("100")

    def test_varmargin_in_extras_ignored_TR13(self) -> None:
        """TR1.3: даже с uid/figi match calculator игнорирует varmargin —
        она teперь обрабатывается attribution module."""
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            instrument_type=InstrumentType.FUTURES,
        )
        m = _matched(
            instrument_uid="uid-si",
            entry_price=Decimal("85000"),
            entry_qty=1,
            exit_price=Decimal("85000"),
        )
        extras = [
            _op("vm1", OperationType.ACCRUING_VARMARGIN, Decimal("500"),
                instrument_uid=None, figi="FUTSI0625"),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert net == Decimal("0")  # body 0, varmargin attribution в pipeline

    def test_varmargin_without_identifier_ignored(self) -> None:
        """Безопасно: без uid и figi не относим к конкретному трейду."""
        calc = FuturesPnLCalculator()
        instr = Instrument(uid="uid-si", figi="FUTSI0625", instrument_type=InstrumentType.FUTURES)
        m = _matched(
            instrument_uid="uid-si",
            entry_price=Decimal("85000"),
            entry_qty=1,
            exit_price=Decimal("85000"),
        )
        extras = [
            _op("vm1", OperationType.ACCRUING_VARMARGIN, Decimal("500"), instrument_uid=None, figi=None),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert net == Decimal("0")  # игнорируем

    def test_varmargin_for_other_future_ignored(self) -> None:
        calc = FuturesPnLCalculator()
        instr = Instrument(uid="uid-si", figi="FUTSI0625", instrument_type=InstrumentType.FUTURES)
        m = _matched(
            instrument_uid="uid-si",
            entry_price=Decimal("85000"),
            entry_qty=1,
            exit_price=Decimal("85000"),
        )
        extras = [
            _op(
                "vm1",
                OperationType.ACCRUING_VARMARGIN,
                Decimal("999"),
                instrument_uid="uid-OTHER-future",
                figi="FUTOTHER01",
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert net == Decimal("0")

    def test_empirical_pv_overrides_cached_when_drift_high(self) -> None:
        """2026-05-19: для индексных фьючерсов (DAX/Brent/foreign) cached pv
        от Tinkoff metadata завышено в 1000x — payment к ним не применяет
        этот множитель. Empirical pv = |payment|/(qty×price) — truth.

        Cached pv = min_pi_amt/min_pi = 1000/1 = 1000 (DAX-style).
        Empirical pv = 178265.86/(10×17276) ≈ 1.0319 (truth from payment).
        Drift = (1000-1.03)/1000 ≈ 99.9% >> 5% → empirical wins.

        Без этого fix body для DAX-style контракта = -2,630,000 ₽ (1000x).
        """
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-dax",
            figi="FUTDAX0325",
            instrument_type=InstrumentType.FUTURES,
            # Cached metadata — misleading 1000 для индексных
            min_price_increment=Decimal("1"),
            min_price_increment_amount=Decimal("1000"),
        )
        # Empirical: payment=178265.86, qty=10, price=17276 → pv ≈ 1.0319
        # Это SHORT (sell first @ 17276, buy back @ 17539)
        entry_price = Decimal("17276")
        exit_price = Decimal("17539")
        qty = 10
        # payment_per_unit for entry SELL = +17826.586 (with pv=1.03 embedded)
        entry_payment_per_unit = Decimal("17826.586")  # = 178265.86 / 10
        exit_payment_per_unit = Decimal("-17818.922")  # = -178189.22 / 10
        entry_lot = FifoLot(
            operation_id="sell1",
            direction=TradeDirection.SHORT,
            quantity_remaining=0,
            quantity_original=qty,
            price_per_unit=entry_price,
            payment_per_unit=entry_payment_per_unit,
            commission_per_unit=Decimal(0),
            executed_at=datetime(2025, 1, 27, tzinfo=UTC),
        )
        exit_fill = ExitFill(
            operation_id="buy1",
            quantity=qty,
            price_per_unit=exit_price,
            payment_per_unit=exit_payment_per_unit,
            commission_per_unit=Decimal(0),
            executed_at=datetime(2025, 1, 28, tzinfo=UTC),
        )
        m = MatchedTrade(
            direction=TradeDirection.SHORT,
            entry_slices=(FillSlice(lot=entry_lot, matched_qty=qty),),
            exit=exit_fill,
            instrument_uid="uid-dax",
            currency="rub",
        )
        gross, _ = calc.compute(m, instr, extra_operations=[])
        # С empirical pv ≈ 1.03: body = (17539 - 17276) × 10 × 1.03 × (-1) ≈ -2710
        # С old cached pv = 1000:                       ≈ -2,630,000  ❌
        # Проверяем что gross в реалистичном диапазоне:
        assert Decimal("-3000") < gross < Decimal("-2500"), (
            f"empirical pv должна быть выбрана: gross={gross}, "
            f"ожидаем ~-2710 ₽ (drift > 5% → empirical wins)"
        )

    def test_cached_pv_used_when_drift_small(self) -> None:
        """Когда empirical и cached в пределах 5% — используем cached
        (для стабильности и совместимости). Si/RTS контракты где Tinkoff
        metadata корректное.
        """
        calc = FuturesPnLCalculator()
        instr = Instrument(
            uid="uid-si",
            figi="FUTSI0625",
            instrument_type=InstrumentType.FUTURES,
            min_price_increment=Decimal("1"),
            min_price_increment_amount=Decimal("100"),  # cached pv = 100
        )
        # Empirical: payment = qty × price × 99 → pv ≈ 99 (within 5% of 100)
        entry_lot = FifoLot(
            operation_id="buy1",
            direction=TradeDirection.LONG,
            quantity_remaining=0,
            quantity_original=1,
            price_per_unit=Decimal("85000"),
            payment_per_unit=Decimal("-8415000"),  # = -85000 × 99
            commission_per_unit=Decimal(0),
            executed_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        exit_fill = ExitFill(
            operation_id="sell1",
            quantity=1,
            price_per_unit=Decimal("86000"),
            payment_per_unit=Decimal("8514000"),
            commission_per_unit=Decimal(0),
            executed_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        m = MatchedTrade(
            direction=TradeDirection.LONG,
            entry_slices=(FillSlice(lot=entry_lot, matched_qty=1),),
            exit=exit_fill,
            instrument_uid="uid-si",
            currency="rub",
        )
        gross, _ = calc.compute(m, instr, extra_operations=[])
        # Cached pv=100 wins (drift 1% < 5%): body = 1000 × 1 × 100 = 100,000
        assert gross == Decimal("100000")


# ── Options ──────────────────────────────────────────────────────────


class TestOptions:
    def test_buy_call_sell_call_profit(self) -> None:
        calc = OptionsPnLCalculator()
        instr = Instrument(
            uid="uid-call-4000",
            instrument_type=InstrumentType.OPTION,
            strike_price=Decimal("4000"),
            option_direction="call",
            option_multiplier=100,
        )
        # Купил премию 50, продал премию 70 → +20 за единицу × 1 контракт = +20.
        # Multiplier учтён через payment (Tinkoff payment = premium × multiplier × qty).
        m = _matched(
            instrument_uid="uid-call-4000",
            entry_price=Decimal("50"),
            entry_qty=1,
            exit_price=Decimal("70"),
        )
        gross, net = calc.compute(m, instr, extra_operations=[])
        assert gross == Decimal("20")
        assert net == Decimal("20")

    def test_expiration_otm_premium_lost(self) -> None:
        """Если экспирация OTM — Tinkoff не присылает settlement payment."""
        calc = OptionsPnLCalculator()
        instr = Instrument(
            uid="uid-call-4000",
            instrument_type=InstrumentType.OPTION,
            strike_price=Decimal("4000"),
            option_direction="call",
        )
        # Гипотетически: купил премию 50, "продали" по нулю (Tinkoff в нашем
        # представлении emit'нул бы synthetic SELL по 0).
        m = _matched(
            instrument_uid="uid-call-4000",
            entry_price=Decimal("50"),
            entry_qty=1,
            exit_price=Decimal("0"),
        )
        gross, net = calc.compute(m, instr, extra_operations=[])
        assert gross == Decimal("-50")
        assert net == Decimal("-50")

    def test_expiration_itm_with_settlement(self) -> None:
        """Купил call, удержал до экспирации, OPTION_EXPIRATION + settlement payment."""
        calc = OptionsPnLCalculator()
        instr = Instrument(
            uid="uid-call-4000",
            instrument_type=InstrumentType.OPTION,
            strike_price=Decimal("4000"),
        )
        m = _matched(
            instrument_uid="uid-call-4000",
            entry_price=Decimal("50"),
            entry_qty=1,
            exit_price=Decimal("0"),
        )
        extras = [
            _op(
                "exp1",
                OperationType.OPTION_EXPIRATION,
                Decimal("100"),  # intrinsic 100 — например базовый актив на 4100
                instrument_uid="uid-call-4000",
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert gross == Decimal("-50")
        assert net == Decimal("50")  # -50 премия + 100 settlement

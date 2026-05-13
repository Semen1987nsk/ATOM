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
                OperationType.PARTIAL_BOND_REPAYMENT,
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
    def test_body_only_no_varmargin(self) -> None:
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
        assert gross == Decimal("1000")
        assert net == Decimal("1000")

    def test_varmargin_added_to_net(self) -> None:
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
        # Два клиринговых начисления: +1200 и -500 = net +700 от маржи.
        extras = [
            _op(
                "vm1",
                OperationType.ACCRUING_VARMARGIN,
                Decimal("1200"),
                instrument_uid="uid-si",
                executed_at=entry_at + timedelta(hours=12),
            ),
            _op(
                "vm2",
                OperationType.WRITING_OFF_VARMARGIN,
                Decimal("-500"),
                instrument_uid="uid-si",
                executed_at=entry_at + timedelta(hours=36),
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert gross == Decimal("100")  # body 100
        assert net == Decimal("800")    # 100 + 1200 - 500

    def test_varmargin_matched_by_figi_when_no_uid(self) -> None:
        """Tinkoff иногда даёт варм-маржу только с figi."""
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
            _op(
                "vm1",
                OperationType.ACCRUING_VARMARGIN,
                Decimal("500"),
                instrument_uid=None,
                figi="FUTSI0625",
            ),
        ]
        gross, net = calc.compute(m, instr, extra_operations=extras)
        assert net == Decimal("500")

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

"""
Unit-тесты `FIFOMatchingService` (PR 7).

Сценарии:

* long-only (single fill, multi fill, partial),
* short-only,
* flip long→short, short→long,
* multi-instrument (независимые очереди),
* фильтрация: только EXECUTED, только trading_types,
* PnL точность (Decimal до 8 знаков).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from application.fifo_matching import FIFOMatchingService
from domain.entities import Instrument, Operation
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDirection,
)
from domain.value_objects import MoneyValue


# ── builders ──────────────────────────────────────────────────────────


SHARE = Instrument(
    uid="uid-sber",
    figi="BBG004730N88",
    ticker="SBER",
    instrument_type=InstrumentType.SHARE,
    lot=10,
)

ETF = Instrument(
    uid="uid-tmos",
    figi="BBG00X1",
    ticker="TMOS",
    instrument_type=InstrumentType.ETF,
    lot=1,
)


def _op(
    op_id: str,
    type_: OperationType,
    qty: int,
    price: Decimal,
    *,
    instrument_uid: str = "uid-sber",
    executed_at: datetime | None = None,
    state: OperationState = OperationState.EXECUTED,
    commission: Decimal = Decimal("0"),
    currency: str = "rub",
) -> Operation:
    # Payment: BUY < 0 (деньги ушли), SELL > 0 (деньги пришли).
    sign = -1 if type_ in (OperationType.BUY, OperationType.BUY_CARD, OperationType.BUY_MARGIN) else 1
    payment_total = sign * price * qty
    return Operation(
        operation_id=op_id,
        account_id="2000000",
        instrument_uid=instrument_uid,
        instrument_type=InstrumentType.SHARE,
        operation_type=type_,
        state=state,
        quantity=qty,
        price=MoneyValue.from_decimal(price, currency),
        payment=MoneyValue.from_decimal(payment_total, currency),
        commission=MoneyValue.from_decimal(commission, currency),
        executed_at=executed_at or datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
    )


# ── tests ─────────────────────────────────────────────────────────────


class TestLongOnly:
    def test_single_buy_then_single_sell(self) -> None:
        svc = FIFOMatchingService()
        ops = [
            _op("buy1", OperationType.BUY, 100, Decimal("270")),
            _op(
                "sell1",
                OperationType.SELL,
                100,
                Decimal("275"),
                executed_at=datetime(2026, 5, 9, 11, 0, tzinfo=timezone.utc),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert not r.open_lots

        t = r.closed_trades[0]
        assert t.direction == TradeDirection.LONG
        assert t.quantity == 100
        assert t.entry_price == Decimal("270")
        assert t.exit_price == Decimal("275")
        assert t.pnl == Decimal("500")  # (275 - 270) * 100
        assert t.net_pnl == Decimal("500")  # без комиссии
        assert t.entry_operation_ids == ("buy1",)
        assert t.exit_operation_ids == ("sell1",)

    def test_two_buys_one_sell_full(self) -> None:
        """Два входа разной ценой → закрытие даёт MatchedTrade с двумя slices."""
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("buy1", OperationType.BUY, 50, Decimal("270"), executed_at=base),
            _op(
                "buy2",
                OperationType.BUY,
                50,
                Decimal("280"),
                executed_at=base + timedelta(hours=1),
            ),
            _op(
                "sell1",
                OperationType.SELL,
                100,
                Decimal("275"),
                executed_at=base + timedelta(hours=2),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert not r.open_lots

        t = r.closed_trades[0]
        assert t.quantity == 100
        assert t.entry_price == Decimal("275")  # (270*50 + 280*50)/100
        assert t.exit_price == Decimal("275")
        # PnL = 275*100 - 270*50 - 280*50 = 27500 - 13500 - 14000 = 0
        assert t.pnl == Decimal("0")

    def test_one_buy_then_partial_sell(self) -> None:
        """BUY 100 → SELL 30 → SELL 30 → SELL 40 = 3 trades."""
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("buy1", OperationType.BUY, 100, Decimal("100"), executed_at=base),
            _op("s1", OperationType.SELL, 30, Decimal("110"), executed_at=base + timedelta(hours=1)),
            _op("s2", OperationType.SELL, 30, Decimal("115"), executed_at=base + timedelta(hours=2)),
            _op("s3", OperationType.SELL, 40, Decimal("120"), executed_at=base + timedelta(hours=3)),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 3
        assert not r.open_lots

        # Каждый closed trade должен иметь entry_operation_ids = ("buy1",).
        for t in r.closed_trades:
            assert t.entry_operation_ids == ("buy1",)
            assert t.entry_price == Decimal("100")

        # PnL'ы соответствуют разнице цен.
        assert r.closed_trades[0].pnl == Decimal("300")   # (110-100)*30
        assert r.closed_trades[1].pnl == Decimal("450")   # (115-100)*30
        assert r.closed_trades[2].pnl == Decimal("800")   # (120-100)*40

    def test_unsold_remainder_in_open_lots(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("buy1", OperationType.BUY, 100, Decimal("100"), executed_at=base),
            _op("s1", OperationType.SELL, 30, Decimal("110"), executed_at=base + timedelta(hours=1)),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert len(r.open_lots) == 1

        lot = r.open_lots[0]
        assert lot.direction == TradeDirection.LONG
        assert lot.quantity_remaining == 70  # 100 - 30
        assert lot.quantity_original == 100
        assert lot.price_per_unit == Decimal("100")


class TestShortOnly:
    def test_short_then_buy_cover(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("sell1", OperationType.SELL, 100, Decimal("100"), executed_at=base),
            _op(
                "buy1",
                OperationType.BUY,
                100,
                Decimal("90"),
                executed_at=base + timedelta(hours=1),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert not r.open_lots

        t = r.closed_trades[0]
        assert t.direction == TradeDirection.SHORT
        assert t.quantity == 100
        assert t.entry_price == Decimal("100")
        assert t.exit_price == Decimal("90")
        # SHORT-сделка: entry SELL payment = +10000, exit BUY payment = -9000.
        # gross = +10000 + (-9000) = +1000 (заработали 1000 на падении).
        assert t.pnl == Decimal("1000")


class TestFlip:
    def test_long_to_short_flip(self) -> None:
        """BUY 100 → SELL 250 = 1 closed (long 100), 1 open short (150)."""
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("buy1", OperationType.BUY, 100, Decimal("100"), executed_at=base),
            _op(
                "s1",
                OperationType.SELL,
                250,
                Decimal("110"),
                executed_at=base + timedelta(hours=1),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert len(r.open_lots) == 1

        closed = r.closed_trades[0]
        assert closed.direction == TradeDirection.LONG
        assert closed.quantity == 100
        # gross = 110*100 + (-100*100) = 1000
        assert closed.pnl == Decimal("1000")

        open_lot = r.open_lots[0]
        assert open_lot.direction == TradeDirection.SHORT
        assert open_lot.quantity_remaining == 150
        # Цена в открытом лоте — цена sell-операции (110).
        assert open_lot.price_per_unit == Decimal("110")

    def test_short_to_long_flip(self) -> None:
        """SELL 100 → BUY 250 = 1 closed (short 100, профит на падении) + 1 open long 150."""
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("s1", OperationType.SELL, 100, Decimal("100"), executed_at=base),
            _op(
                "b1",
                OperationType.BUY,
                250,
                Decimal("90"),
                executed_at=base + timedelta(hours=1),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert len(r.open_lots) == 1

        closed = r.closed_trades[0]
        assert closed.direction == TradeDirection.SHORT
        assert closed.quantity == 100
        # gross = +10000 + (-9000) = +1000 (зашортили высоко, выкупили дёшево)
        assert closed.pnl == Decimal("1000")

        open_lot = r.open_lots[0]
        assert open_lot.direction == TradeDirection.LONG
        assert open_lot.quantity_remaining == 150
        assert open_lot.price_per_unit == Decimal("90")


class TestFiltering:
    def test_progress_state_ignored(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("buy1", OperationType.BUY, 100, Decimal("100"), executed_at=base),
            _op(
                "s1",
                OperationType.SELL,
                100,
                Decimal("110"),
                executed_at=base + timedelta(hours=1),
                state=OperationState.PROGRESS,  # ← в матчинг не должна попасть
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert not r.closed_trades  # SELL не EXECUTED — открытая позиция не закрылась
        assert len(r.open_lots) == 1
        assert r.open_lots[0].quantity_remaining == 100

    def test_non_trading_ops_ignored(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("div1", OperationType.DIVIDEND, 0, Decimal("0"), executed_at=base),
            _op("buy1", OperationType.BUY, 100, Decimal("100"), executed_at=base + timedelta(hours=1)),
            _op("coupon1", OperationType.COUPON, 0, Decimal("0"), executed_at=base + timedelta(hours=2)),
            _op(
                "s1",
                OperationType.SELL,
                100,
                Decimal("110"),
                executed_at=base + timedelta(hours=3),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        # DIVIDEND / COUPON не должны порождать Trade.
        assert r.closed_trades[0].direction == TradeDirection.LONG

    def test_out_of_order_ops_sorted_chronologically(self) -> None:
        """Алгоритм должен сортировать по `executed_at` независимо от input order."""
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("s1", OperationType.SELL, 100, Decimal("110"), executed_at=base + timedelta(hours=1)),
            _op("buy1", OperationType.BUY, 100, Decimal("100"), executed_at=base),  # ранее
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        assert r.closed_trades[0].direction == TradeDirection.LONG


class TestEmpty:
    def test_no_operations_returns_empty(self) -> None:
        svc = FIFOMatchingService()
        r = svc.match(account_id=1, instrument=SHARE, operations=[])
        assert not r.closed_trades
        assert not r.open_lots

    def test_only_buys_no_trades(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("b1", OperationType.BUY, 50, Decimal("100"), executed_at=base),
            _op("b2", OperationType.BUY, 30, Decimal("110"), executed_at=base + timedelta(hours=1)),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert not r.closed_trades
        assert len(r.open_lots) == 2


class TestCommissions:
    def test_commission_reduces_net_pnl(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op(
                "buy1",
                OperationType.BUY,
                100,
                Decimal("100"),
                executed_at=base,
                commission=Decimal("-3.00"),  # broker fee
            ),
            _op(
                "s1",
                OperationType.SELL,
                100,
                Decimal("110"),
                executed_at=base + timedelta(hours=1),
                commission=Decimal("-3.30"),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        assert len(r.closed_trades) == 1
        t = r.closed_trades[0]
        # gross = (110-100)*100 = 1000.
        assert t.pnl == Decimal("1000")
        # net = 1000 + (-3) + (-3.30) = 993.70.
        assert t.net_pnl == Decimal("993.70")
        # commission_total = |sum of commissions| = 6.30.
        assert t.commission_total == Decimal("6.30")


# ── regression tests for PR 18 (cost-basis, canceled filter) ────────────


class TestEntryValueExitValue:
    """
    Гарантия от регрессии: Trade.entry_value / exit_value заполняются FIFO
    из payment'ов. Это нужно для корректного pnl_pct (особенно у фьючерсов,
    где цена в пунктах, а pnl в рублях).
    """

    def test_long_share_entry_value_equals_buy_payment_abs(self) -> None:
        svc = FIFOMatchingService()
        ops = [
            _op("b1", OperationType.BUY, 100, Decimal("270")),
            _op("s1", OperationType.SELL, 100, Decimal("275"),
                executed_at=datetime(2026, 5, 9, 11, 0, tzinfo=timezone.utc)),
        ]
        t = svc.match(account_id=1, instrument=SHARE, operations=ops).closed_trades[0]
        # entry_value = |sum buy payments| = 270 × 100 = 27000.
        assert t.entry_value == Decimal("27000")
        # exit_value = |sum sell payments| = 275 × 100 = 27500.
        assert t.exit_value == Decimal("27500")
        # pnl ≈ exit - entry для LONG.
        assert t.pnl == t.exit_value - t.entry_value

    def test_short_entry_value_correct_for_payment_inversion(self) -> None:
        """
        Для SHORT: sell payment > 0, buy_to_cover payment < 0.
        entry_value (сумма sells) должен быть положителен (cost-basis).
        pnl должен быть положителен если cover дешевле sell.
        """
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("s1", OperationType.SELL, 100, Decimal("100"), executed_at=base),
            _op("b1", OperationType.BUY, 100, Decimal("90"),
                executed_at=base + timedelta(hours=1)),
        ]
        t = svc.match(account_id=1, instrument=SHARE, operations=ops).closed_trades[0]
        assert t.direction == TradeDirection.SHORT
        # entry_value = |sell.payment| = 10000.
        assert t.entry_value == Decimal("10000")
        # exit_value = |buy_to_cover.payment| = 9000.
        assert t.exit_value == Decimal("9000")
        # Положительный pnl: продали дороже, откупили дешевле.
        assert t.pnl == Decimal("1000")

    def test_partial_close_entry_value_proportional(self) -> None:
        """Partial close: entry_value пропорциональна matched_qty."""
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            _op("b1", OperationType.BUY, 100, Decimal("100"), executed_at=base),
            _op("s1", OperationType.SELL, 30, Decimal("110"),
                executed_at=base + timedelta(hours=1)),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        t = r.closed_trades[0]
        # Закрыли 30 из 100. entry_value = 30 × 100 = 3000 (а не 10000 всей покупки).
        assert t.quantity == 30
        assert t.entry_value == Decimal("3000")
        assert t.exit_value == Decimal("3300")
        # 70 шт остаются открытыми.
        assert len(r.open_lots) == 1
        assert r.open_lots[0].quantity_remaining == 70


class TestCanceledOperationsFilter:
    """
    Гарантия от регрессии: операции с state=CANCELED не должны попадать в
    FIFO. Tinkoff API иногда возвращает отменённые buy с положительным
    payment'ом (= отмена транзакции) — без фильтра FIFO считал их как
    реальные сделки и выдавал ошибочные Trade'ы вроде OZON +369%.
    Фактический фильтр стоит в operation_repo.fetch_for_instrument
    (state != 'canceled'), но FIFO тоже должен корректно работать если
    canceled случайно попадут на вход — current behavior проверяется.
    """

    def test_canceled_operation_is_not_matched_into_trade(self) -> None:
        svc = FIFOMatchingService()
        base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        ops = [
            # Реальная покупка.
            _op("b1", OperationType.BUY, 100, Decimal("100"), executed_at=base),
            # Отменённая "покупка" с PnL-инверсией (бывает у Tinkoff).
            _op(
                "b2_canceled",
                OperationType.BUY,
                50,
                Decimal("200"),
                executed_at=base + timedelta(hours=1),
                state=OperationState.CANCELED,
            ),
            # Реальная продажа всех 100.
            _op(
                "s1",
                OperationType.SELL,
                100,
                Decimal("110"),
                executed_at=base + timedelta(hours=2),
            ),
        ]
        r = svc.match(account_id=1, instrument=SHARE, operations=ops)
        # Один trade на 100 шт (canceled buy не учтён).
        assert len(r.closed_trades) == 1
        t = r.closed_trades[0]
        assert t.quantity == 100
        assert t.entry_price == Decimal("100")  # без 200 от canceled.
        assert t.pnl == Decimal("1000")  # (110-100)*100, не искажено.

"""TR1: тесты position_id allocation в FIFOMatchingService.

Сценарии:
1. Single buy → 1 position, 1 open lot, position_id=1
2. Scale-in (buy + buy одного направления) → 1 position, 2 lots, same position_id
3. Round-trip (buy → sell полностью) → 1 closed trade, position_id=1
4. Sequential round-trips (buy→sell, buy→sell) → 2 closed trades, position_ids=[1, 2]
5. Reversal (buy 100 → sell 150 → flip к short 50) → close long pid=1, open short pid=2
6. Partial close + scale-in (buy 100, sell 30, buy 50) → mix: 1 closed pid=1, 2 open pid=1

Все позиции должны получить position_id внутри одного match() call.
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


SHARE = Instrument(
    uid="uid-sber",
    figi="BBG004730N88",
    ticker="SBER",
    instrument_type=InstrumentType.SHARE,
    lot=10,
)


def _op(
    op_id: str,
    type_: OperationType,
    qty: int,
    price: Decimal,
    *,
    minutes_offset: int = 0,
) -> Operation:
    sign = -1 if type_ in (OperationType.BUY, OperationType.BUY_CARD) else 1
    payment_total = sign * price * qty
    return Operation(
        operation_id=op_id,
        account_id="2000000",
        instrument_uid=SHARE.uid,
        instrument_type=InstrumentType.SHARE,
        operation_type=type_,
        state=OperationState.EXECUTED,
        quantity=qty,
        price=MoneyValue.from_decimal(price, "rub"),
        payment=MoneyValue.from_decimal(payment_total, "rub"),
        commission=MoneyValue.from_decimal(Decimal("0"), "rub"),
        executed_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
        + timedelta(minutes=minutes_offset),
    )


def test_single_buy_assigns_position_id_1():
    """Given: один BUY 100 @ 100. When: match. Then: 1 open lot с position_id=1."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[_op("b1", OperationType.BUY, 100, Decimal("100"))],
    )
    assert len(result.open_lots) == 1
    assert result.open_lots[0].position_id == 1
    assert len(result.closed_trades) == 0


def test_scale_in_shares_same_position_id():
    """Given: BUY 100 @ 100, потом BUY 50 @ 110 (scale-in). When: match.
    Then: 2 open lots, оба с position_id=1 (один lifecycle)."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[
            _op("b1", OperationType.BUY, 100, Decimal("100")),
            _op("b2", OperationType.BUY, 50, Decimal("110"), minutes_offset=1),
        ],
    )
    assert len(result.open_lots) == 2
    assert result.open_lots[0].position_id == 1
    assert result.open_lots[1].position_id == 1, "scale-in должен reuse position_id"


def test_round_trip_buy_sell_one_position():
    """Given: BUY 100, SELL 100 (полное закрытие).
    Then: 1 closed trade с position_id=1, 0 open lots."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[
            _op("b1", OperationType.BUY, 100, Decimal("100")),
            _op("s1", OperationType.SELL, 100, Decimal("110"), minutes_offset=1),
        ],
    )
    assert len(result.closed_trades) == 1
    assert result.closed_trades[0].position_id == 1
    assert len(result.open_lots) == 0


def test_sequential_round_trips_increment_position_id():
    """Given: BUY 100→SELL 100, потом BUY 50→SELL 50. Два независимых
    round-trip'а. Then: 2 closed trades, position_ids = [1, 2]."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[
            _op("b1", OperationType.BUY, 100, Decimal("100"), minutes_offset=0),
            _op("s1", OperationType.SELL, 100, Decimal("110"), minutes_offset=1),
            _op("b2", OperationType.BUY, 50, Decimal("120"), minutes_offset=2),
            _op("s2", OperationType.SELL, 50, Decimal("125"), minutes_offset=3),
        ],
    )
    assert len(result.closed_trades) == 2
    pids = [t.position_id for t in result.closed_trades]
    assert pids == [1, 2], f"sequential round-trips должны получить pids [1, 2], got {pids}"


def test_reversal_long_to_short_two_positions():
    """Given: BUY 100 → SELL 150 (закрывает long и открывает short 50).
    Then: 1 closed long trade pid=1, 1 open short lot pid=2."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[
            _op("b1", OperationType.BUY, 100, Decimal("100"), minutes_offset=0),
            _op("s1", OperationType.SELL, 150, Decimal("110"), minutes_offset=1),
        ],
    )
    assert len(result.closed_trades) == 1
    assert result.closed_trades[0].position_id == 1
    assert result.closed_trades[0].direction == TradeDirection.LONG

    assert len(result.open_lots) == 1
    assert result.open_lots[0].position_id == 2, "flip должен инкрементить pid"
    assert result.open_lots[0].direction == TradeDirection.SHORT


def test_partial_close_then_scale_in_same_position():
    """Given: BUY 100 → SELL 30 (partial close, 70 остаётся open) → BUY 50
    (scale-in пока позиция ещё открыта).
    Then: 1 closed trade pid=1 (sell 30), 2 open lots оба pid=1."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[
            _op("b1", OperationType.BUY, 100, Decimal("100"), minutes_offset=0),
            _op("s1", OperationType.SELL, 30, Decimal("110"), minutes_offset=1),
            _op("b2", OperationType.BUY, 50, Decimal("105"), minutes_offset=2),
        ],
    )
    assert len(result.closed_trades) == 1
    assert result.closed_trades[0].position_id == 1

    assert len(result.open_lots) == 2
    assert all(lot.position_id == 1 for lot in result.open_lots), \
        "partial close НЕ должен инкрементить pid если позиция всё ещё открыта"


def test_position_id_isolated_between_match_calls():
    """Given: два независимых match() вызова. Then: каждый стартует с pid=1.
    Это важно для pipeline где каждый instrument обрабатывается отдельно."""
    fifo = FIFOMatchingService()
    r1 = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[_op("b1", OperationType.BUY, 100, Decimal("100"))],
    )
    r2 = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[_op("b2", OperationType.BUY, 50, Decimal("200"))],
    )
    assert r1.open_lots[0].position_id == 1
    assert r2.open_lots[0].position_id == 1, "each match() resets counter"


def test_open_trades_from_lots_preserves_position_id():
    """T7 + TR1: open_trades_from_lots должен сохранить position_id
    при конвертации FifoLot → Trade."""
    fifo = FIFOMatchingService()
    result = fifo.match(
        account_id=1,
        instrument=SHARE,
        operations=[
            _op("b1", OperationType.BUY, 100, Decimal("100"), minutes_offset=0),
            _op("b2", OperationType.BUY, 50, Decimal("110"), minutes_offset=1),
        ],
    )
    open_trades = FIFOMatchingService.open_trades_from_lots(
        lots=result.open_lots,
        instrument=SHARE,
        account_id=1,
    )
    assert len(open_trades) == 2
    assert all(t.position_id == 1 for t in open_trades)

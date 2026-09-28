"""MATH-10: PRIMARY_ORDER должен матчиться FIFO как BUY.

Контекст:
* `domain/pnl/cash_flow_classification.py` классифицирует PRIMARY_ORDER как
  `CashFlowCategory.TRADE` (cash-anchored journal-сторона учитывает).
* До этого фикса `application/fifo_matching.py::_BUY_TYPES` не содержал
  PRIMARY_ORDER → операция проходила мимо FIFO, создавая orphan-риск:
  journal видит сделку, FIFO не строит лот → расхождение в
  cash-anchored reconciliation.

Семантика PRIMARY_ORDER = первичное размещение (IPO/SPO),
направление LONG, payment отрицательный (деньги исходящие).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from application.fifo_matching import _BUY_TYPES, _SELL_TYPES, FIFOMatchingService
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


_BUY_LIKE_TYPES = {
    OperationType.BUY,
    OperationType.BUY_CARD,
    OperationType.BUY_MARGIN,
    OperationType.PRIMARY_ORDER,
}


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
    """Совпадает с фабрикой из test_fifo_matching.py, но знает про PRIMARY_ORDER."""
    sign = -1 if type_ in _BUY_LIKE_TYPES else 1
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


def test_primary_order_in_buy_types() -> None:
    """PRIMARY_ORDER должен быть в _BUY_TYPES (первичное размещение = покупка)."""
    assert OperationType.PRIMARY_ORDER in _BUY_TYPES
    assert OperationType.PRIMARY_ORDER not in _SELL_TYPES


def test_primary_order_creates_long_lot_matchable_by_sell() -> None:
    """End-to-end: PRIMARY_ORDER + SELL дают один matched LONG trade."""
    svc = FIFOMatchingService()
    base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
    ops = [
        _op("ipo1", OperationType.PRIMARY_ORDER, 10, Decimal("100"), executed_at=base),
        _op(
            "sell1",
            OperationType.SELL,
            10,
            Decimal("120"),
            executed_at=base + timedelta(hours=1),
        ),
    ]
    r = svc.match(account_id=1, instrument=SHARE, operations=ops)
    assert len(r.closed_trades) == 1
    assert not r.open_lots

    t = r.closed_trades[0]
    assert t.direction == TradeDirection.LONG
    assert t.quantity == 10
    assert t.entry_price == Decimal("100")
    assert t.exit_price == Decimal("120")
    assert t.pnl == Decimal("200")  # (120 - 100) * 10
    assert t.entry_operation_ids == ("ipo1",)
    assert t.exit_operation_ids == ("sell1",)


def test_primary_order_only_remains_as_open_long_lot() -> None:
    """PRIMARY_ORDER без последующей продажи → один open LONG-лот (не orphan)."""
    svc = FIFOMatchingService()
    ops = [_op("ipo1", OperationType.PRIMARY_ORDER, 10, Decimal("100"))]
    r = svc.match(account_id=1, instrument=SHARE, operations=ops)

    assert not r.closed_trades
    assert len(r.open_lots) == 1
    lot = r.open_lots[0]
    assert lot.direction == TradeDirection.LONG
    assert lot.quantity_remaining == 10
    assert lot.quantity_original == 10
    assert lot.price_per_unit == Decimal("100")

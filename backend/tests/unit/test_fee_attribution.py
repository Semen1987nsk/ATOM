"""TR1.3: тесты attribution account-level fees по trades."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from domain.entities import Operation, Trade
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDirection,
)
from domain.pnl.fee_attribution import (
    FeeAttribution,
    apply_attribution_to_trade,
    attribute_fees,
)
from domain.value_objects import MoneyValue


T0 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 5, 30, 18, 0, tzinfo=timezone.utc)


def _trade(
    *,
    instrument_uid: str = "uid-A",
    direction: TradeDirection = TradeDirection.LONG,
    qty: int = 100,
    entry_price: Decimal = Decimal("100"),
    entry_offset_min: int = 0,
    exit_offset_min: int | None = None,
    net_pnl: Decimal | None = None,
) -> Trade:
    entry_at = T0 + timedelta(minutes=entry_offset_min)
    exit_at = T0 + timedelta(minutes=exit_offset_min) if exit_offset_min is not None else None
    return Trade(
        account_id="1",
        instrument_uid=instrument_uid,
        instrument_type=InstrumentType.SHARE,
        direction=direction,
        quantity=qty,
        entry_price=entry_price,
        exit_price=Decimal("105") if exit_at else None,
        entry_at=entry_at,
        exit_at=exit_at,
        pnl=net_pnl,
        net_pnl=net_pnl,
        currency="RUB",
    )


def _fee_op(
    *,
    op_type: OperationType,
    payment: Decimal,
    minutes_offset: int = 30,
    instrument_uid: str | None = None,
) -> Operation:
    return Operation(
        operation_id=f"op-{op_type.value}-{minutes_offset}",
        account_id="1",
        instrument_uid=instrument_uid,
        instrument_type=InstrumentType.SHARE,
        operation_type=op_type,
        state=OperationState.EXECUTED,
        quantity=0,
        price=None,
        payment=MoneyValue.from_decimal(payment, "RUB"),
        commission=None,
        executed_at=T0 + timedelta(minutes=minutes_offset),
    )


def _pv_one(_: str) -> Decimal:
    return Decimal(1)


# ── tests ─────────────────────────────────────────────────────────────


def test_single_trade_single_fee_full_attribution():
    """1 trade open during fee time → 100% attribution."""
    trade = _trade(qty=100, entry_offset_min=0, exit_offset_min=60)
    fee = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-500"), minutes_offset=30)
    result = attribute_fees(fee_ops=[fee], trades=[trade], now=NOW, point_value_for=_pv_one)
    assert len(result) == 1
    assert result[0].margin_fee == Decimal("-500")
    assert result[0].varmargin == 0


def test_two_concurrent_trades_proportional_50_50():
    """2 trades same notional concurrent → 50/50 split."""
    t1 = _trade(qty=100, entry_price=Decimal("100"), entry_offset_min=0, exit_offset_min=60)
    t2 = _trade(qty=100, entry_price=Decimal("100"), entry_offset_min=10, exit_offset_min=50)
    fee = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-1000"), minutes_offset=30)
    result = attribute_fees(fee_ops=[fee], trades=[t1, t2], now=NOW, point_value_for=_pv_one)
    assert result[0].margin_fee == Decimal("-500")
    assert result[1].margin_fee == Decimal("-500")


def test_proportional_split_by_notional():
    """3 trades с разным notional → proportional."""
    t1 = _trade(qty=100, entry_price=Decimal("100"), entry_offset_min=0, exit_offset_min=60)  # 10000
    t2 = _trade(qty=200, entry_price=Decimal("100"), entry_offset_min=0, exit_offset_min=60)  # 20000
    t3 = _trade(qty=100, entry_price=Decimal("200"), entry_offset_min=0, exit_offset_min=60)  # 20000
    # total notional = 10000 + 20000 + 20000 = 50000
    # t1 gets 10/50 = 20%, t2,t3 get 40% each
    fee = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-1000"), minutes_offset=30)
    result = attribute_fees(fee_ops=[fee], trades=[t1, t2, t3], now=NOW, point_value_for=_pv_one)
    assert result[0].margin_fee == Decimal("-200")
    assert result[1].margin_fee == Decimal("-400")
    assert result[2].margin_fee == Decimal("-400")


def test_fee_outside_trade_window_skipped():
    """Fee op до entry_at или после exit_at → не attributed."""
    trade = _trade(qty=100, entry_offset_min=30, exit_offset_min=60)
    fee_before = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-100"), minutes_offset=10)
    fee_after = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-100"), minutes_offset=120)
    result = attribute_fees(
        fee_ops=[fee_before, fee_after], trades=[trade], now=NOW, point_value_for=_pv_one
    )
    assert result[0].margin_fee == 0


def test_open_trade_gets_attribution():
    """Open trade (exit_at=None) → fee attributed до now."""
    trade = _trade(qty=100, entry_offset_min=0, exit_offset_min=None)
    fee = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-200"), minutes_offset=30)
    result = attribute_fees(fee_ops=[fee], trades=[trade], now=NOW, point_value_for=_pv_one)
    assert result[0].margin_fee == Decimal("-200")


def test_different_fee_types_routed_to_separate_buckets():
    """Varmargin, margin_fee, service_fee, tax → разные columns.

    Phase 8.2: varmargin распределяется только на OPEN trades (для closed
    она уже в Trade.pnl через body formula). Поэтому для varmargin assertion
    trade здесь open (exit_offset_min=None).
    """
    trade = _trade(qty=100, entry_offset_min=0, exit_offset_min=None)
    fees = [
        _fee_op(op_type=OperationType.ACCRUING_VARMARGIN, payment=Decimal("100"), minutes_offset=10),
        _fee_op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-50"), minutes_offset=20),
        _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-30"), minutes_offset=30),
        _fee_op(op_type=OperationType.SERVICE_FEE, payment=Decimal("-10"), minutes_offset=40),
        _fee_op(op_type=OperationType.TAX, payment=Decimal("-5"), minutes_offset=50),
    ]
    result = attribute_fees(fee_ops=fees, trades=[trade], now=NOW, point_value_for=_pv_one)
    assert result[0].varmargin == Decimal("50")  # 100 + (-50)
    assert result[0].margin_fee == Decimal("-30")
    assert result[0].service_fee == Decimal("-10")
    assert result[0].other == Decimal("-5")


def test_uid_match_filters_active_trades():
    """Fee op с instrument_uid → атрибутируется только trades этого инструмента.

    Phase 8.2: для varmargin testing trades open (closed varmargin уже в body).
    """
    t1 = _trade(instrument_uid="uid-A", qty=100, entry_offset_min=0, exit_offset_min=None)
    t2 = _trade(instrument_uid="uid-B", qty=100, entry_offset_min=0, exit_offset_min=None)
    # Fee для uid-A only
    fee = _fee_op(
        op_type=OperationType.WRITING_OFF_VARMARGIN,
        payment=Decimal("-1000"),
        minutes_offset=30,
        instrument_uid="uid-A",
    )
    result = attribute_fees(fee_ops=[fee], trades=[t1, t2], now=NOW, point_value_for=_pv_one)
    assert result[0].varmargin == Decimal("-1000")
    assert result[1].varmargin == 0


def test_phase8_varmargin_skipped_for_closed_trades_with_body():
    """Phase 8.2 regression: VARMARGIN для closed trades с pnl != 0 НЕ distributed
    (она уже в Trade.pnl через body=(exit−entry)×qty×pv formula).

    Conditional: legacy closed trades с pnl=0 продолжают получать varmargin
    (backwards-compat для acc'ов без Phase 8 recompute) — см. test ниже.
    """
    # closed trade с body уже вычисленным (Phase 8 recompute сделан)
    closed_trade = _trade(
        instrument_uid="uid-F", qty=1, entry_offset_min=0, exit_offset_min=60,
        net_pnl=Decimal("-100"),  # set pnl via _trade helper (uses net_pnl param)
    )
    open_trade = _trade(
        instrument_uid="uid-F", qty=1, entry_offset_min=0, exit_offset_min=None
    )
    fee = _fee_op(
        op_type=OperationType.WRITING_OFF_VARMARGIN,
        payment=Decimal("-500"),
        minutes_offset=30,
        instrument_uid="uid-F",
    )
    result = attribute_fees(
        fee_ops=[fee],
        trades=[closed_trade, open_trade],
        now=NOW,
        point_value_for=_pv_one,
    )
    # Phase 8.2: closed с pnl != 0 → skip; всё уходит на open
    assert result[0].varmargin == Decimal("0"), \
        f"closed trade с pnl != 0 must skip varmargin (Phase 8.2), got {result[0].varmargin}"
    assert result[1].varmargin == Decimal("-500")


def test_phase8_legacy_closed_with_zero_pnl_still_gets_varmargin():
    """Phase 8.2 conditional: closed trades с pnl=0 (legacy Phase 6 fallback
    или pre-sync history без надёжных pv) продолжают получать varmargin
    attribution — backwards-compat."""
    # closed trade с pnl=0 (Phase 6 legacy state)
    closed_legacy = _trade(
        instrument_uid="uid-F", qty=1, entry_offset_min=0, exit_offset_min=60,
        net_pnl=Decimal("0"),  # pnl=0 → legacy mode
    )
    fee = _fee_op(
        op_type=OperationType.WRITING_OFF_VARMARGIN,
        payment=Decimal("-500"),
        minutes_offset=30,
        instrument_uid="uid-F",
    )
    result = attribute_fees(
        fee_ops=[fee],
        trades=[closed_legacy],
        now=NOW,
        point_value_for=_pv_one,
    )
    # Legacy mode: pnl=0 → varmargin attributed
    assert result[0].varmargin == Decimal("-500"), \
        f"legacy closed trade с pnl=0 must get varmargin attribution, got {result[0].varmargin}"


def test_apply_attribution_recomputes_net_pnl_for_closed():
    """apply_attribution_to_trade: closed trade net_pnl += sum of fees."""
    trade = _trade(qty=100, entry_offset_min=0, exit_offset_min=60, net_pnl=Decimal("1000"))
    attr = FeeAttribution(
        varmargin=Decimal("100"),
        margin_fee=Decimal("-50"),
        service_fee=Decimal("-20"),
        other=Decimal("-10"),
    )
    new_trade = apply_attribution_to_trade(trade, attr)
    # 1000 + 100 - 50 - 20 - 10 = 1020
    assert new_trade.net_pnl == Decimal("1020")
    assert new_trade.varmargin_attributed == Decimal("100")
    assert new_trade.margin_fee_attributed == Decimal("-50")


def test_apply_attribution_open_trade_keeps_net_pnl_none():
    """Open trade (net_pnl=None) — attribution fields filled, net_pnl остаётся None."""
    trade = _trade(qty=100, entry_offset_min=0, exit_offset_min=None, net_pnl=None)
    attr = FeeAttribution(margin_fee=Decimal("-200"))
    new_trade = apply_attribution_to_trade(trade, attr)
    assert new_trade.net_pnl is None
    assert new_trade.margin_fee_attributed == Decimal("-200")


def test_zero_weight_skipped_gracefully():
    """Trade с entry_price=0 → weight=0, skip без crash."""
    trade = _trade(qty=1, entry_price=Decimal("0"), entry_offset_min=0, exit_offset_min=60)
    fee = _fee_op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-100"), minutes_offset=30)
    result = attribute_fees(fee_ops=[fee], trades=[trade], now=NOW, point_value_for=_pv_one)
    # No crash, no attribution (zero weight → skip with warning log)
    assert result[0].margin_fee == 0

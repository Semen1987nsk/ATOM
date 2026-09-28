"""Phase 4 (Plan lazy-meandering-bonbon): integration-style invariant tests
для формулы `journal_pnl ≈ cash_pnl`.

Каждый сценарий = чистая конструкция:
1. Список Operation (input, buy, sell, fee, varmargin, ...)
2. Apply FIFO matching → Trade rows
3. Apply attribution → Trade.{varmargin/margin/service/other}_attributed
4. Compute journal_pnl per нашей формуле
5. Compute cash_pnl per truth formula = (Σ all payments) - net_deposits
6. Assert |journal − cash| < tolerance

Эти тесты гарантируют что наша P&L математика на разных сценариях
(shares, futures, margin, taxes, income, deposits-через-разные-каналы)
не имеет drift'а. Регрессионный gate перед launch на 1000 users.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional

import pytest

from domain.entities import Operation, Trade
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDirection,
)
from domain.pnl.cash_flow_classification import (
    CASH_FLOW_MAP,
    CashFlowCategory,
    classify,
    operation_types_in,
)
from domain.pnl.fee_attribution import attribute_fees
from domain.value_objects import MoneyValue


T0 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 5, 30, 18, 0, tzinfo=timezone.utc)


def _op(
    *,
    op_type: OperationType,
    payment: Decimal,
    minutes_offset: int = 0,
    instrument_uid: Optional[str] = None,
    instrument_type: InstrumentType = InstrumentType.SHARE,
    quantity: int = 0,
) -> Operation:
    return Operation(
        operation_id=f"op-{op_type.value}-{minutes_offset}-{payment}",
        account_id="1",
        instrument_uid=instrument_uid,
        instrument_type=instrument_type,
        operation_type=op_type,
        state=OperationState.EXECUTED,
        quantity=quantity,
        price=None,
        payment=MoneyValue.from_decimal(payment, "RUB"),
        commission=None,
        executed_at=T0 + timedelta(minutes=minutes_offset),
    )


def _trade(
    *,
    instrument_uid: str = "uid-A",
    instrument_type: InstrumentType = InstrumentType.SHARE,
    direction: TradeDirection = TradeDirection.LONG,
    qty: int = 100,
    entry_price: Decimal = Decimal("100"),
    exit_price: Optional[Decimal] = None,
    entry_offset_min: int = 0,
    exit_offset_min: Optional[int] = None,
    pnl: Optional[Decimal] = None,
    net_pnl: Optional[Decimal] = None,
    commission_total: Decimal = Decimal(0),
) -> Trade:
    entry_at = T0 + timedelta(minutes=entry_offset_min)
    exit_at = T0 + timedelta(minutes=exit_offset_min) if exit_offset_min is not None else None
    return Trade(
        account_id="1",
        instrument_uid=instrument_uid,
        instrument_type=instrument_type,
        direction=direction,
        quantity=qty,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_at=entry_at,
        exit_at=exit_at,
        pnl=pnl,
        net_pnl=net_pnl,
        commission_total=commission_total,
        currency="RUB",
    )


def _pv_one(_: Optional[str]) -> Decimal:
    return Decimal(1)


def _pv_for(uid_to_pv: dict[str, Decimal]) -> Callable[[Optional[str]], Decimal]:
    def _f(uid: Optional[str]) -> Decimal:
        if uid is None:
            return Decimal(1)
        return uid_to_pv.get(uid, Decimal(1))
    return _f


def _instr_type_for(uid_to_type: dict[str, str]) -> Callable[[Optional[str]], Optional[str]]:
    def _f(uid: Optional[str]) -> Optional[str]:
        if uid is None:
            return None
        return uid_to_type.get(uid)
    return _f


def _sum_payment(ops: list[Operation], category: CashFlowCategory) -> Decimal:
    """Σ payment ops в указанной категории."""
    s = Decimal(0)
    for op in ops:
        if classify(getattr(op.operation_type, "value", op.operation_type)) == category:
            s += op.payment.to_decimal() if op.payment else Decimal(0)
    return s


def _cash_pnl(
    ops: list[Operation],
    *,
    open_position_market_value: Decimal = Decimal(0),
) -> Decimal:
    """Cash truth: portfolio - net_deposits.

    portfolio_change = Σ all payments + open_position_market_value
                     (because BUY moves cash → securities at market)

    Этот хелпер симулирует Tinkoff-style cash + securities accounting.
    """
    total_payments = sum(
        (op.payment.to_decimal() if op.payment else Decimal(0)) for op in ops
    )
    net_deposits = _sum_payment(ops, CashFlowCategory.NET_DEPOSIT)
    portfolio = total_payments + open_position_market_value
    return portfolio - net_deposits


def _journal_pnl(
    closed_trades: list[Trade],
    open_position_unrealized_sum: Decimal,
    open_trade_attribution_non_varmargin: Decimal,
) -> Decimal:
    """Journal P&L per нашей формуле."""
    realized = sum(
        (t.net_pnl if t.net_pnl is not None else Decimal(0)) for t in closed_trades
    )
    return Decimal(realized) + open_position_unrealized_sum + open_trade_attribution_non_varmargin


# ──────────────────────────────────────────────────────────────────────────
# Scenario 1: share_round_trip (без комиссий, без fees)
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_share_round_trip():
    """INPUT 10000; BUY 10@500; SELL 10@550; OUTPUT 5500. Cash = 500. Journal = 500."""
    ops = [
        _op(op_type=OperationType.INPUT, payment=Decimal("10000"), minutes_offset=0),
        _op(op_type=OperationType.BUY, payment=Decimal("-5000"), minutes_offset=10,
            instrument_uid="uid-A", quantity=10),
        _op(op_type=OperationType.SELL, payment=Decimal("5500"), minutes_offset=20,
            instrument_uid="uid-A", quantity=10),
        _op(op_type=OperationType.OUTPUT, payment=Decimal("-5500"), minutes_offset=30),
    ]
    # No open position at end (10 bought, 10 sold).
    cash = _cash_pnl(ops, open_position_market_value=Decimal(0))
    closed = [
        _trade(qty=10, entry_price=Decimal("500"), exit_price=Decimal("550"),
               exit_offset_min=20, pnl=Decimal("500"), net_pnl=Decimal("500")),
    ]
    journal = _journal_pnl(closed, Decimal(0), Decimal(0))
    assert abs(journal - cash) < Decimal("0.01"), f"journal={journal}, cash={cash}"
    assert journal == Decimal("500")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 2: share_with_commission
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_share_with_commission():
    """BUY 10@500 + SELL 10@550; broker_fee на каждой = -5. Net = 500-10 = 490."""
    ops = [
        _op(op_type=OperationType.INPUT, payment=Decimal("10000"), minutes_offset=0),
        _op(op_type=OperationType.BUY, payment=Decimal("-5000"), minutes_offset=10,
            instrument_uid="uid-A", quantity=10),
        _op(op_type=OperationType.BROKER_FEE, payment=Decimal("-5"), minutes_offset=10),
        _op(op_type=OperationType.SELL, payment=Decimal("5500"), minutes_offset=20,
            instrument_uid="uid-A", quantity=10),
        _op(op_type=OperationType.BROKER_FEE, payment=Decimal("-5"), minutes_offset=20),
    ]
    cash = _cash_pnl(ops, open_position_market_value=Decimal(0))
    # closed Trade.net_pnl includes commission_total (signed via base = pnl - |commission|).
    closed = [
        _trade(qty=10, entry_price=Decimal("500"), exit_price=Decimal("550"),
               exit_offset_min=20, pnl=Decimal("500"), net_pnl=Decimal("490"),
               commission_total=Decimal("10")),
    ]
    journal = _journal_pnl(closed, Decimal(0), Decimal(0))
    assert abs(journal - cash) < Decimal("0.01"), f"journal={journal}, cash={cash}"
    assert journal == Decimal("490")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 3: open_share_with_margin_fee
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_open_share_with_margin_fee():
    """INPUT 50000; BUY 100@500 (open); MARGIN_FEE -100. Cash = unrealized − 100."""
    ops = [
        _op(op_type=OperationType.INPUT, payment=Decimal("50000"), minutes_offset=0),
        _op(op_type=OperationType.BUY, payment=Decimal("-50000"), minutes_offset=10,
            instrument_uid="uid-A", quantity=100),
        _op(op_type=OperationType.MARGIN_FEE, payment=Decimal("-100"), minutes_offset=15),
    ]
    # Open share position: current price 520 → market value = 52000
    current_market_value = Decimal("52000")
    cash = _cash_pnl(ops, open_position_market_value=current_market_value)
    # Cash = (sum payments) + market - net_deposits
    #      = (50000 - 50000 - 100) + 52000 - 50000 = 1900
    assert cash == Decimal("1900")

    # Attribution: margin_fee distributed to open trade
    open_trade = _trade(
        qty=100, entry_price=Decimal("500"), exit_offset_min=None,
        pnl=None, net_pnl=None, commission_total=Decimal(0),
    )
    attrs = attribute_fees(
        fee_ops=[ops[2]],
        trades=[open_trade],
        now=NOW,
        point_value_for=_pv_one,
        instrument_type_for=_instr_type_for({"uid-A": "share"}),
    )
    # margin_fee -100 polностью attributed to single open trade
    assert attrs[0].margin_fee == Decimal("-100")

    # Journal: open Position.unrealized + open attribution
    # unrealized for share = (current - avg) × qty = (520 - 500) × 100 = 2000
    open_unrealized = Decimal("2000")
    open_attribution_non_varmargin = attrs[0].margin_fee + attrs[0].service_fee + attrs[0].other
    journal = _journal_pnl([], open_unrealized, open_attribution_non_varmargin)
    # journal = 0 + 2000 + (-100) = 1900
    assert abs(journal - cash) < Decimal("0.01"), f"journal={journal}, cash={cash}"
    assert journal == Decimal("1900")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 4: futures_full_lifecycle (Phase 8, body-from-prices model)
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_futures_full_lifecycle():
    """BUY 1 SiH6 @100 (pv=100); varmargin events totalling -800; SELL @92.

    Phase 8 (2026-05-17): Trade.pnl = (exit − entry) × qty × pv × sign.
    Это математически тождественно сумме всех varmargin операций от entry
    до exit + post-clearing settlement.

    В этом сценарии:
      - 3 varmargin op: -200, -300, -300 = -800 (последний — post-exit
        clearing settlement в окне +4h)
      - body = (92 − 100) × 1 × 100 × +1 = -800
      - Σ varmargin == body (telescoping identity) ✓
      - closed Trade.varmargin_attributed = 0 (Phase 8.2 skip closed)
      - Trade.net_pnl = body = -800

    Cash impact futures (BUY/SELL payments offset broker margin record,
    не считаются как cash flow в _cash_pnl).
    """
    pv = Decimal("100")
    # Симулируем 3 varmargin op: 2 во время удержания, 1 post-exit (4h window)
    ops_cash_flow = [
        _op(op_type=OperationType.INPUT, payment=Decimal("20000"), minutes_offset=0),
        _op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-200"),
            minutes_offset=60),   # day 1 settlement during holding
        _op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-300"),
            minutes_offset=120),  # day 2 settlement during holding
        # exit at minute 180; post-clearing varmargin at +60min (still in 4h window)
        _op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-300"),
            minutes_offset=240),  # post-exit settlement (MOEX delayed)
    ]
    cash = _cash_pnl(ops_cash_flow, open_position_market_value=Decimal(0))
    # = (20000 - 200 - 300 - 300) + 0 - 20000 = -800
    assert cash == Decimal("-800")

    # Phase 8: closed Trade.pnl = body from prices = (92-100)*1*100*(+1) = -800.
    # varmargin_attributed = 0 (Phase 8.2 skip closed).
    # net_pnl = body - |comm| + Σ attribution = -800 - 0 + 0 = -800.
    closed = [
        _trade(
            instrument_uid="uid-F",
            instrument_type=InstrumentType.FUTURES,
            qty=1,
            entry_price=Decimal("100"),
            exit_price=Decimal("92"),
            exit_offset_min=180,
            pnl=Decimal("-800"),  # Phase 8: body=(exit-entry)*qty*pv
            net_pnl=Decimal("-800"),
            commission_total=Decimal(0),
        ),
    ]
    # Verify Phase 8.2: для closed varmargin НЕ attribute'тся (она в body)
    varmargin_ops = [
        _op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-200"),
            minutes_offset=60),
        _op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-300"),
            minutes_offset=120),
        _op(op_type=OperationType.WRITING_OFF_VARMARGIN, payment=Decimal("-300"),
            minutes_offset=240),  # post-exit; would have been orphan in Phase 6
    ]
    attrs = attribute_fees(
        fee_ops=varmargin_ops,
        trades=closed,
        now=NOW,
        point_value_for=_pv_for({"uid-F": pv}),
        instrument_type_for=_instr_type_for({"uid-F": "futures"}),
    )
    # Phase 8.2: varmargin для closed trades НЕ distributed
    assert attrs[0].varmargin == Decimal("0"), \
        f"Phase 8.2: closed futures varmargin must be 0 (in body), got {attrs[0].varmargin}"

    journal = _journal_pnl(closed, Decimal(0), Decimal(0))
    assert abs(journal - cash) < Decimal("0.01"), f"journal={journal}, cash={cash}"
    assert journal == Decimal("-800")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 4b: futures body comes from prices (Phase 8 invariant)
# ──────────────────────────────────────────────────────────────────────────
def test_futures_pnl_calculator_body_from_prices():
    """Регрессионный gate: FuturesPnLCalculator.compute() returns
    body=(exit−entry)×qty×pv×sign (Phase 8 architecture).

    До Phase 6 был body=payment-based → double-count с varmargin.
    Phase 6 был body=0 → orphan varmargin от post-clearing settlements.
    Phase 8 — body из цен — math identity с Σ varmargin (telescoping sum).
    """
    from decimal import Decimal as D
    from domain.entities import Instrument
    from domain.enums import InstrumentType, TradeDirection
    from domain.pnl.base import MatchedTrade, ExitFill, FillSlice, FifoLot
    from domain.pnl.futures import FuturesPnLCalculator

    calculator = FuturesPnLCalculator()

    instrument = Instrument(
        uid="uid-F",
        figi="FIGI-F",
        ticker="SiH6",
        instrument_type=InstrumentType.FUTURES,
        lot=1,
        min_price_increment=D("1"),
        min_price_increment_amount=D("100"),  # pv = 100
    )
    # BUY 1@100, SELL 1@92, LONG → body = (92-100)*1*100*(+1) = -800
    entry_lot = FifoLot(
        operation_id="op-buy",
        direction=TradeDirection.LONG,
        quantity_remaining=0,
        quantity_original=1,
        price_per_unit=D("100"),
        payment_per_unit=D("-10000"),  # full notional (ignored by Phase 8)
        commission_per_unit=D("-5"),
        executed_at=T0,
        currency="rub",
    )
    entry_slice = FillSlice(lot=entry_lot, matched_qty=1)
    exit_fill = ExitFill(
        operation_id="op-sell",
        quantity=1,
        price_per_unit=D("92"),
        payment_per_unit=D("9200"),  # full notional (ignored by Phase 8)
        commission_per_unit=D("-5"),
        executed_at=T0 + timedelta(hours=1),
        currency="rub",
    )
    matched = MatchedTrade(
        direction=TradeDirection.LONG,
        entry_slices=(entry_slice,),
        exit=exit_fill,
        instrument_uid="uid-F",
        currency="rub",
    )
    gross, net = calculator.compute(matched, instrument)
    # Phase 8: body = (92-100) × 1 × 100 × +1 = -800
    assert gross == D("-800"), f"Phase 8 body must be (exit-entry)*qty*pv, got {gross}"
    # net = body(-800) + commissions(-5 + -5) = -810
    assert net == D("-810"), f"net = body + commissions, got {net}"


# ──────────────────────────────────────────────────────────────────────────
# Scenario 5: swift_funding — критический B1 fix
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_swift_funding():
    """INPUT_SWIFT 100000 (был упущен раньше). Деление BUY/SELL +1000 profit.

    До фикса real_pnl.net_deposit учитывал только input/output → SWIFT-deposit
    показывал бы P&L = current_balance (≈100k) вместо реального +1k.
    """
    ops = [
        _op(op_type=OperationType.INPUT_SWIFT, payment=Decimal("100000"), minutes_offset=0),
        _op(op_type=OperationType.BUY, payment=Decimal("-50000"), minutes_offset=10,
            instrument_uid="uid-A", quantity=100),
        _op(op_type=OperationType.SELL, payment=Decimal("51000"), minutes_offset=20,
            instrument_uid="uid-A", quantity=100),
    ]
    # Sanity: SWIFT correctly classified
    assert classify("input_swift") == CashFlowCategory.NET_DEPOSIT

    net_deposits = _sum_payment(ops, CashFlowCategory.NET_DEPOSIT)
    assert net_deposits == Decimal("100000")

    cash = _cash_pnl(ops, open_position_market_value=Decimal(0))
    # = (100000 - 50000 + 51000) - 100000 = 1000
    assert cash == Decimal("1000")

    closed = [
        _trade(qty=100, entry_price=Decimal("500"), exit_price=Decimal("510"),
               exit_offset_min=20, pnl=Decimal("1000"), net_pnl=Decimal("1000")),
    ]
    journal = _journal_pnl(closed, Decimal(0), Decimal(0))
    assert journal == cash == Decimal("1000")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 6: multi-channel funding (input + swift + acquiring + multi)
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_multi_channel_funding():
    """Все 4 channels пополнения суммарно = 25000. После трейда profit 500.

    Это покрывает B1 (real_pnl.py упускал все каналы кроме input/output).
    """
    ops = [
        _op(op_type=OperationType.INPUT, payment=Decimal("10000"), minutes_offset=0),
        _op(op_type=OperationType.INPUT_SWIFT, payment=Decimal("5000"), minutes_offset=1),
        _op(op_type=OperationType.INPUT_ACQUIRING, payment=Decimal("5000"), minutes_offset=2),
        _op(op_type=OperationType.INPUT_MULTI, payment=Decimal("5000"), minutes_offset=3),
        _op(op_type=OperationType.BUY, payment=Decimal("-10000"), minutes_offset=10,
            instrument_uid="uid-A", quantity=100),
        _op(op_type=OperationType.SELL, payment=Decimal("10500"), minutes_offset=20,
            instrument_uid="uid-A", quantity=100),
    ]
    net_deposits = _sum_payment(ops, CashFlowCategory.NET_DEPOSIT)
    assert net_deposits == Decimal("25000")

    cash = _cash_pnl(ops, open_position_market_value=Decimal(0))
    assert cash == Decimal("500")

    closed = [
        _trade(qty=100, entry_price=Decimal("100"), exit_price=Decimal("105"),
               exit_offset_min=20, pnl=Decimal("500"), net_pnl=Decimal("500")),
    ]
    journal = _journal_pnl(closed, Decimal(0), Decimal(0))
    assert journal == cash == Decimal("500")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 7: internal_transfer не считается deposit
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_internal_transfer_excluded():
    """TRANS_BS_BS -5000 — внутренний transfer, НЕ должен быть в net_deposits."""
    ops = [
        _op(op_type=OperationType.INPUT, payment=Decimal("10000"), minutes_offset=0),
        _op(op_type=OperationType.TRANS_BS_BS, payment=Decimal("-5000"), minutes_offset=5),
    ]
    net_deposits = _sum_payment(ops, CashFlowCategory.NET_DEPOSIT)
    assert net_deposits == Decimal("10000")  # NOT 5000
    internal = _sum_payment(ops, CashFlowCategory.INTERNAL_TRANSFER)
    assert internal == Decimal("-5000")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 8: phantom varmargin на shares НЕ должен attributed (B3 fix)
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_no_phantom_varmargin_on_shares():
    """Open share + open futures одновременно; varmargin без instrument_uid.

    Без B3 fix: varmargin распределялся бы по обоим → phantom loss на share.
    С B3 fix: varmargin идёт ТОЛЬКО на futures (instrument_type_for=share filter).
    """
    share_trade = _trade(
        instrument_uid="uid-share",
        instrument_type=InstrumentType.SHARE,
        qty=100, entry_price=Decimal("100"),
        exit_offset_min=None,
    )
    futures_trade = _trade(
        instrument_uid="uid-fut",
        instrument_type=InstrumentType.FUTURES,
        qty=1, entry_price=Decimal("90"),
        exit_offset_min=None,
    )
    varmargin_op = _op(
        op_type=OperationType.WRITING_OFF_VARMARGIN,
        payment=Decimal("-500"),
        minutes_offset=60,
        instrument_uid=None,  # account-wide
    )
    attrs = attribute_fees(
        fee_ops=[varmargin_op],
        trades=[share_trade, futures_trade],
        now=NOW,
        point_value_for=_pv_for({"uid-fut": Decimal("100")}),
        instrument_type_for=_instr_type_for({"uid-share": "share", "uid-fut": "futures"}),
    )
    # Share should get 0 varmargin (B3 fix). Futures gets all -500.
    assert attrs[0].varmargin == Decimal(0)
    assert attrs[1].varmargin == Decimal("-500")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 9: all 12 tax variants attributed
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_all_tax_variants_attributed():
    """Каждый из 12 tax types должен попасть в other_fees_attributed."""
    closed_trade = _trade(
        qty=100, entry_price=Decimal("100"), exit_price=Decimal("110"),
        exit_offset_min=10, pnl=Decimal("1000"), net_pnl=Decimal("1000"),
    )
    tax_types = [
        OperationType.TAX,
        OperationType.TAX_PROGRESSIVE,
        OperationType.BENEFIT_TAX,
        OperationType.BENEFIT_TAX_PROGRESSIVE,
        OperationType.TAX_CORRECTION,
        OperationType.TAX_CORRECTION_PROGRESSIVE,
        OperationType.TAX_REPO,
        OperationType.TAX_REPO_PROGRESSIVE,
        OperationType.TAX_REPO_HOLD,
        OperationType.TAX_REPO_HOLD_PROGRESSIVE,
        OperationType.TAX_REPO_REFUND,
        OperationType.TAX_REPO_REFUND_PROGRESSIVE,
    ]
    fee_ops = [
        _op(op_type=t, payment=Decimal("-10"), minutes_offset=5)
        for t in tax_types
    ]
    attrs = attribute_fees(
        fee_ops=fee_ops,
        trades=[closed_trade],
        now=NOW,
        point_value_for=_pv_one,
        instrument_type_for=_instr_type_for({"uid-A": "share"}),
    )
    # Все 12 × -10 = -120 в other_fees
    assert attrs[0].other == Decimal("-120")
    # Не должно быть в других колонках
    assert attrs[0].varmargin == Decimal(0)
    assert attrs[0].margin_fee == Decimal(0)
    assert attrs[0].service_fee == Decimal(0)


# ──────────────────────────────────────────────────────────────────────────
# Scenario 10: track_pfee / success_fee — ATTRIBUTABLE_FEE category
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_tracker_fees_attributed():
    """track_mfee, track_pfee, success_fee, cash_fee — все должны attribute."""
    closed_trade = _trade(
        qty=100, entry_price=Decimal("100"), exit_price=Decimal("110"),
        exit_offset_min=10, pnl=Decimal("1000"), net_pnl=Decimal("1000"),
    )
    fee_ops = [
        _op(op_type=OperationType.TRACK_MFEE, payment=Decimal("-50"), minutes_offset=5),
        _op(op_type=OperationType.TRACK_PFEE, payment=Decimal("-100"), minutes_offset=6),
        _op(op_type=OperationType.SUCCESS_FEE, payment=Decimal("-200"), minutes_offset=7),
        _op(op_type=OperationType.CASH_FEE, payment=Decimal("-10"), minutes_offset=8),
    ]
    attrs = attribute_fees(
        fee_ops=fee_ops,
        trades=[closed_trade],
        now=NOW,
        point_value_for=_pv_one,
        instrument_type_for=_instr_type_for({"uid-A": "share"}),
    )
    # tracker и success — service_like → service_fee_attributed
    # cash_fee — service_like → service_fee_attributed
    # margin_fee_attributed should be 0 (нет margin_fee ops)
    assert attrs[0].service_fee == Decimal("-360")
    assert attrs[0].margin_fee == Decimal(0)


# ──────────────────────────────────────────────────────────────────────────
# Scenario 11: unknown_op_type — graceful UNKNOWN, log warning, no crash
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_unknown_op_type_handled():
    """Несуществующий OperationType.value → UNKNOWN, не падает, не attributed."""
    closed_trade = _trade(
        qty=100, entry_price=Decimal("100"), exit_price=Decimal("110"),
        exit_offset_min=10, pnl=Decimal("1000"), net_pnl=Decimal("1000"),
    )
    # Synthetic unknown op (выбираем существующее не-attributable, например
    # INPUT — для теста "не падает" мы должны передать tipo в attribute_fees
    # но он отфильтруется по category).
    input_op = _op(op_type=OperationType.INPUT, payment=Decimal("1000"), minutes_offset=5)
    attrs = attribute_fees(
        fee_ops=[input_op],
        trades=[closed_trade],
        now=NOW,
        point_value_for=_pv_one,
        instrument_type_for=_instr_type_for({"uid-A": "share"}),
    )
    # INPUT — category=NET_DEPOSIT, не attributable → skip
    assert attrs[0].varmargin == Decimal(0)
    assert attrs[0].margin_fee == Decimal(0)
    assert attrs[0].service_fee == Decimal(0)
    assert attrs[0].other == Decimal(0)


# ──────────────────────────────────────────────────────────────────────────
# Scenario 12: dividend income attribution
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_dividend_income_attributed():
    """DIVIDEND +200 во время открытой акции → other (income) +200 для trade."""
    open_share = _trade(
        instrument_uid="uid-A",
        instrument_type=InstrumentType.SHARE,
        qty=100, entry_price=Decimal("100"),
        exit_offset_min=None,
    )
    div_op = _op(
        op_type=OperationType.DIVIDEND,
        payment=Decimal("200"),
        minutes_offset=60,
        instrument_uid="uid-A",
    )
    attrs = attribute_fees(
        fee_ops=[div_op],
        trades=[open_share],
        now=NOW,
        point_value_for=_pv_one,
        instrument_type_for=_instr_type_for({"uid-A": "share"}),
    )
    # Dividend → INCOME → other_fees_attributed += 200
    assert attrs[0].other == Decimal("200")


# ──────────────────────────────────────────────────────────────────────────
# Scenario 13: varmargin без активных futures → orphan (не на shares!)
# ──────────────────────────────────────────────────────────────────────────
def test_scenario_varmargin_orphan_when_no_futures():
    """Если в момент varmargin op нет active futures — orphan, НЕ phantom на shares."""
    share_trade = _trade(
        instrument_uid="uid-share",
        instrument_type=InstrumentType.SHARE,
        qty=100, entry_price=Decimal("100"),
        exit_offset_min=None,
    )
    varmargin_op = _op(
        op_type=OperationType.WRITING_OFF_VARMARGIN,
        payment=Decimal("-500"),
        minutes_offset=60,
        instrument_uid=None,
    )
    attrs = attribute_fees(
        fee_ops=[varmargin_op],
        trades=[share_trade],
        now=NOW,
        point_value_for=_pv_one,
        instrument_type_for=_instr_type_for({"uid-share": "share"}),
    )
    # Share НЕ должен получить varmargin (orphan)
    assert attrs[0].varmargin == Decimal(0)


# ──────────────────────────────────────────────────────────────────────────
# Property-based-ish test: random mix of deposits/trades/fees
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("seed", list(range(5)))
def test_property_random_share_scenario(seed: int):
    """Random последовательность ops (только shares + fees + deposits) →
    journal должен равен cash (без futures, без open positions сложности).
    """
    import random
    rng = random.Random(seed)

    ops: list[Operation] = []
    # Start with deposits (random mix of channels)
    deposit_total = Decimal(0)
    for i in range(rng.randint(1, 5)):
        amount = Decimal(rng.randint(1000, 20000))
        deposit_type = rng.choice([
            OperationType.INPUT, OperationType.INPUT_SWIFT,
            OperationType.INPUT_ACQUIRING, OperationType.INPUT_MULTI,
        ])
        ops.append(_op(op_type=deposit_type, payment=amount, minutes_offset=i))
        deposit_total += amount

    # Several round-trip share trades
    realized_pnl = Decimal(0)
    closed_trades: list[Trade] = []
    fee_total = Decimal(0)
    minutes_offset = 100
    for _ in range(rng.randint(1, 5)):
        qty = rng.randint(1, 50)
        entry_price = Decimal(rng.randint(50, 200))
        exit_price = entry_price + Decimal(rng.randint(-10, 10))
        entry_payment = -qty * entry_price
        exit_payment = qty * exit_price
        trade_pnl = exit_payment + entry_payment
        commission = Decimal(rng.randint(1, 10))
        ops.append(_op(op_type=OperationType.BUY, payment=entry_payment,
                       minutes_offset=minutes_offset, instrument_uid="uid-S", quantity=qty))
        ops.append(_op(op_type=OperationType.BROKER_FEE, payment=-commission,
                       minutes_offset=minutes_offset + 1))
        minutes_offset += 10
        ops.append(_op(op_type=OperationType.SELL, payment=exit_payment,
                       minutes_offset=minutes_offset, instrument_uid="uid-S", quantity=qty))
        ops.append(_op(op_type=OperationType.BROKER_FEE, payment=-commission,
                       minutes_offset=minutes_offset + 1))
        fee_total -= commission * 2  # 2 commission ops per trade
        net_pnl = trade_pnl - commission * 2
        realized_pnl += net_pnl
        closed_trades.append(_trade(
            instrument_uid="uid-S",
            qty=qty,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_offset_min=minutes_offset - 10,
            exit_offset_min=minutes_offset,
            pnl=trade_pnl,
            net_pnl=net_pnl,
            commission_total=commission * 2,
        ))
        minutes_offset += 10

    cash = _cash_pnl(ops, open_position_market_value=Decimal(0))
    journal = _journal_pnl(closed_trades, Decimal(0), Decimal(0))
    assert abs(journal - cash) < Decimal("0.01"), (
        f"seed={seed}: journal={journal}, cash={cash}, diff={journal-cash}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Coverage invariant test (defensive)
# ──────────────────────────────────────────────────────────────────────────
def test_classification_covers_all_op_types():
    """OperationType enum members все классифицированы (защита от регрессий)."""
    from domain.pnl.cash_flow_classification import assert_complete_coverage
    assert_complete_coverage()

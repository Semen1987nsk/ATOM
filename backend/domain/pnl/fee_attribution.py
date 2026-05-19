"""TR1.3 + Phase 3c (2026-05-17): distribution account-level cash flows по trades.

Tinkoff API отдаёт fee/income operations часто без `instrument_uid/figi`.
Для honest per-trade journal эти cash flows нужно attribute к конкретным trades.

Алгоритм per fee_op:
  1. Categorize via `domain.pnl.cash_flow_classification.classify`.
  2. Найти active trades в `op.executed_at` (`entry_at <= executed_at <=
     (exit_at OR now)`).
  3. Если op имеет `instrument_uid` — фильтр по нему.
     ИНАЧЕ для VARMARGIN — фильтр только FUTURES trades (важно! shares не имеют
     варм-маржи, иначе phantom loss на акциях — см. plan B3+phase1).
     Остальные категории (margin/service/tax/income) распределяются на все
     active trades.
  4. Compute notional weights (|qty × price × point_value|).
  5. Distribute `op.payment` proportionally → запись в соответствующую
     Trade column (varmargin/margin_fee/service_fee/other_fees).

Open trades (`exit_at is None`) получают свою долю — деньги реально потрачены.
Recompute Trade.net_pnl делается только для CLOSED (pipeline-side).

История архитектуры:
- TR1.3 (2026-05-15): introduced fee_attribution для closed trades, чтобы
  убрать double-count между Trade.varmargin_attributed и Position.unrealized_pnl.
- Phase 1 audit (2026-05-17): обнаружил что varmargin attributed на closed
  SHARES (acc#4 phantom -9,174₽). Восстановили фильтр FUTURES-only для varmargin
  без instrument_uid.
- Phase 3c (2026-05-17): расширили coverage всех ATTRIBUTABLE_FEE + TAX + INCOME
  + INCOME_TAX категорий вместо hardcoded списка из 4-х.

Edge cases:
- Fee op в моменте когда нет active trades подходящего instrument_type — log
  warning, skip (включается в orphan report).
- Active trade с quantity=0 (внутри FIFO) — игнорируем (weight=0).
- Multiple instruments с разным point_value — корректно через `point_value_for`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional, Sequence

from domain.entities import Operation, Trade
from domain.pnl.cash_flow_classification import (
    CashFlowCategory,
    classify,
)
from logger import get_logger

log = get_logger("fee_attribution")


@dataclass
class FeeAttribution:
    """Сумма distributed cash flows per trade.

    Колонки в Trade ORM:
      - varmargin_attributed  ← VARMARGIN
      - margin_fee_attributed ← ATTRIBUTABLE_FEE (margin_fee, overnight, ...)
      - service_fee_attributed ← ATTRIBUTABLE_FEE (service_fee, track_*, ...)
      - other_fees_attributed ← TAX, INCOME_TAX, INCOME (с знаком: income добавляет +, tax вычитает −)

    Для INCOME (dividends, coupons, expirations) знак автоматически от
    payment_value (>0 = income, <0 = redemption/expiry с loss).
    """

    varmargin: Decimal = field(default_factory=lambda: Decimal(0))
    margin_fee: Decimal = field(default_factory=lambda: Decimal(0))
    service_fee: Decimal = field(default_factory=lambda: Decimal(0))
    other: Decimal = field(default_factory=lambda: Decimal(0))

    def is_zero(self) -> bool:
        return (
            self.varmargin == 0
            and self.margin_fee == 0
            and self.service_fee == 0
            and self.other == 0
        )


# Mapping ATTRIBUTABLE_FEE OperationType.value → конкретная FeeAttribution column.
# margin-like → margin_fee_attributed; всё остальное → service_fee_attributed.
# Это сохраняет совместимость с UI которое разделяет margin vs service fees.
MARGIN_LIKE_FEE_TYPES = frozenset({
    "margin_fee",
    "overnight",      # ночная margin
    "over_com",       # commission на overnight
})

SERVICE_LIKE_FEE_TYPES = frozenset({
    "service_fee",
    "track_mfee",
    "track_pfee",
    "success_fee",
    "cash_fee",
    "out_fee",
    "out_stamp_duty",
    "output_penalty",
    "advice_fee",
})


def _attributable_fee_column(op_type: str) -> str:
    """ATTRIBUTABLE_FEE op_type → 'margin_fee' / 'service_fee' / 'other'."""
    if op_type in MARGIN_LIKE_FEE_TYPES:
        return "margin_fee"
    if op_type in SERVICE_LIKE_FEE_TYPES:
        return "service_fee"
    return "other"


def _trade_notional_weight(
    trade: Trade,
    point_value_for: Callable[[str], Decimal],
) -> Decimal:
    """Notional value позиции = |qty × entry_price × point_value|.

    Используется как weight при пропорциональном split. Для futures
    point_value делает SiH6 (pv=100) heavier чем MMU4 (pv=1), что
    отражает реальный margin risk.
    """
    qty = Decimal(trade.quantity or 0)
    if qty == 0:
        return Decimal(0)
    price = Decimal(trade.entry_price or 0)
    if price == 0:
        return Decimal(0)
    pv = point_value_for(trade.instrument_uid) if trade.instrument_uid else Decimal(1)
    return abs(qty * price * pv)


def _is_active_at(trade: Trade, at: datetime, now: datetime) -> bool:
    """Проверка: была ли сделка открыта в момент `at`."""
    if trade.entry_at is None:
        return False
    if trade.entry_at > at:
        return False
    # Закрытая сделка: exit_at >= at
    if trade.exit_at is not None:
        return trade.exit_at >= at
    # Открытая: считается активной до now
    return at <= now


def attribute_fees(
    *,
    fee_ops: Sequence[Operation],
    trades: Sequence[Trade],
    now: datetime,
    point_value_for: Callable[[str], Decimal],
    instrument_type_for: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> list[FeeAttribution]:
    """Distribute account-level cash flow ops по trades.

    Args:
        fee_ops: операции в категориях VARMARGIN / ATTRIBUTABLE_FEE / TAX /
            INCOME / INCOME_TAX (другие игнорируются). Не-attributable ops
            (deposits, trades, broker_fee per-trade) НЕ должны передаваться.
        trades: все trades аккаунта (closed + open).
        now: reference timestamp.
        point_value_for: `instrument_uid → Decimal point_value`. Для shares = 1,
            для futures formula (min_price_increment_amount / min_price_increment).
        instrument_type_for: `instrument_uid → str instrument_type` (share/futures/...).
            Нужен для VARMARGIN-only-to-futures фильтра. Если None — fallback
            на старое поведение (attribute varmargin на все active trades —
            создаёт phantom loss на shares; см. acc#4 audit).

    Returns:
        Список FeeAttribution той же длины и в том же порядке что `trades`.
    """
    result = [FeeAttribution() for _ in trades]
    if not fee_ops or not trades:
        return result

    counters = {
        "no_active_trades": 0,
        "zero_weight": 0,
        "unknown_category": 0,
        "varmargin_without_futures": 0,
    }

    for op in fee_ops:
        if op.executed_at is None or op.payment is None:
            continue

        op_type_value = getattr(op.operation_type, "value", op.operation_type)
        category = classify(op_type_value)

        # Только эти категории distribute через attribution.
        # Deposits/trades/broker_fee обрабатываются в другом месте.
        if category not in (
            CashFlowCategory.VARMARGIN,
            CashFlowCategory.ATTRIBUTABLE_FEE,
            CashFlowCategory.TAX,
            CashFlowCategory.INCOME,
            CashFlowCategory.INCOME_TAX,
        ):
            if category == CashFlowCategory.UNKNOWN:
                counters["unknown_category"] += 1
                log.warning(
                    "fee_attribution.unknown_op_type",
                    extra={"op_type": op_type_value, "executed_at": str(op.executed_at)},
                )
            continue

        payment_value = op.payment.to_decimal()
        if payment_value == 0:
            continue

        # Filter active trades в момент op.executed_at.
        op_uid = getattr(op, "instrument_uid", None) or None
        op_figi = getattr(op, "instrument_figi", None) or None

        active_indices: list[int] = []
        for idx, trade in enumerate(trades):
            if not _is_active_at(trade, op.executed_at, now):
                continue
            # Phase 8 (2026-05-17): VARMARGIN для closed futures с
            # вычисленным body (Trade.pnl != 0) уже учтена в Trade.pnl
            # через body=(exit−entry)×qty×pv formula — иначе double-count.
            # Legacy trades с pnl=0 (Phase 6 fallback или pre-sync history
            # без надёжных pv) продолжают получать varmargin attribution
            # — backwards-compatible поведение для acc'ов без Phase 8 recompute.
            if (
                category == CashFlowCategory.VARMARGIN
                and trade.exit_at is not None
                and trade.pnl is not None
                and Decimal(trade.pnl) != 0
            ):
                continue
            # Если у op есть instrument_uid — match по нему (приоритет).
            if op_uid:
                if trade.instrument_uid != op_uid:
                    continue
            elif op_figi:
                if trade.instrument_figi != op_figi:
                    continue
            # VARMARGIN без instrument_uid: restrict to FUTURES trades only.
            # Без этого filter акции получают phantom varmargin loss (acc#4 audit).
            elif category == CashFlowCategory.VARMARGIN and instrument_type_for is not None:
                t_type = instrument_type_for(trade.instrument_uid)
                if (t_type or "").lower() != "futures":
                    continue
            active_indices.append(idx)

        if not active_indices:
            if category == CashFlowCategory.VARMARGIN:
                counters["varmargin_without_futures"] += 1
            else:
                counters["no_active_trades"] += 1
            continue

        # Compute weights for active trades.
        weights = [
            _trade_notional_weight(trades[i], point_value_for)
            for i in active_indices
        ]
        total_weight = sum(weights, Decimal(0))

        if total_weight == 0:
            counters["zero_weight"] += 1
            continue

        # Proportional distribution.
        for idx, weight in zip(active_indices, weights):
            share = payment_value * (weight / total_weight)
            if category == CashFlowCategory.VARMARGIN:
                result[idx].varmargin += share
            elif category == CashFlowCategory.ATTRIBUTABLE_FEE:
                col = _attributable_fee_column(op_type_value)
                if col == "margin_fee":
                    result[idx].margin_fee += share
                elif col == "service_fee":
                    result[idx].service_fee += share
                else:
                    result[idx].other += share
            elif category in (
                CashFlowCategory.TAX,
                CashFlowCategory.INCOME,
                CashFlowCategory.INCOME_TAX,
            ):
                # Tax — отрицательный payment (cash out). Income — положительный.
                # Все идут в `other_fees_attributed` с естественным знаком.
                result[idx].other += share

    # Aggregate orphan summary в Sentry breadcrumb.
    for key, count in counters.items():
        if count > 0:
            log.warning(
                f"fee_attribution.{key}",
                extra={"count": count},
            )

    return result


def apply_attribution_to_trade(trade: Trade, attr: FeeAttribution) -> Trade:
    """Возвращает копию Trade с filled attribution fields + recomputed net_pnl.

    Это helper для unit-тестов. Production-pipeline использует прямое
    assignment в `_stage_attribute_fees` (для идемпотентности — overwrite не add).

    net_pnl recompute formula:
        net_pnl_new = (trade.pnl − |commission|)
                      + varmargin + margin_fee + service_fee + other

    Open trades (exit_at is None, net_pnl is None) получают только attribution
    fields — net_pnl остаётся None.
    """
    if attr.is_zero():
        return trade

    update_fields: dict = {
        "varmargin_attributed": attr.varmargin,
        "margin_fee_attributed": attr.margin_fee,
        "service_fee_attributed": attr.service_fee,
        "other_fees_attributed": attr.other,
    }

    # Recompute net_pnl только для closed trades.
    if trade.exit_at is not None and trade.net_pnl is not None and trade.pnl is not None:
        base = Decimal(trade.pnl) - abs(Decimal(trade.commission_total or 0))
        delta = attr.varmargin + attr.margin_fee + attr.service_fee + attr.other
        update_fields["net_pnl"] = base + delta

    return trade.model_copy(update=update_fields)

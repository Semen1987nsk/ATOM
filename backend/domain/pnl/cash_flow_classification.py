"""Единый справочник классификации cash flow categories для P&L.

Каждый OperationType должен иметь точно ОДНУ запись в CASH_FLOW_MAP.
Тест-инвариант `assert_complete_coverage()` падает если кто-то добавил новый
тип в enum но забыл сюда — защита от регрессии.

Категории нужны для:
1. `tools/reconcile_journal_vs_cash.py` — считает net_deposits = Σ NET_DEPOSIT
2. `routers/real_pnl.py` — то же определение net_deposit для UI
3. `domain/pnl/fee_attribution.py` — какие ops attribute по trades
4. `application/sync/pipeline._stage_attribute_fees` — расширенный fee_types list

История: до 2026-05-17 каждое из этих мест использовало свой hard-coded список,
все три расходились. См. plan `lazy-meandering-bonbon.md`.
"""
from __future__ import annotations

from enum import Enum

from domain.enums import OperationType


class CashFlowCategory(str, Enum):
    """Высокоуровневая семантическая категория cash flow."""

    NET_DEPOSIT = "net_deposit"
    """Внешние пополнения и выводы (через любой канал: input, swift, acquiring, multi).
    Должны исключаться из P&L. Знак: + = пополнение, − = вывод."""

    INTERNAL_TRANSFER = "internal_transfer"
    """Перемещения между счетами одного юзера. НЕ P&L и НЕ deposit
    (зеркальная запись на другом счёте). trans_iis_bs, trans_bs_bs."""

    SECURITY_TRANSFER = "security_transfer"
    """Перевод бумаг в/из счёта без cash impact. input_securities, output_securities.
    Не P&L. Position обновляется отдельно через sync."""

    TRADE = "trade"
    """Купля/продажа ценной бумаги. Обрабатывается FIFO matcher
    → Trade record с body P&L. buy, sell, buy_card, sell_card, buy_margin, sell_margin."""

    VARMARGIN = "varmargin"
    """Daily variation margin для futures. Cash impact = net varmargin.
    Attributes к active trades через fee_attribution. accruing/writing_off."""

    BROKER_COMMISSION = "broker_commission"
    """Per-trade брокерская комиссия. Включена в Trade.commission напрямую
    через FIFO matcher (не через attribution). broker_fee."""

    ATTRIBUTABLE_FEE = "attributable_fee"
    """Account-level fees распределяются по trades пропорционально notional.
    margin_fee, service_fee, track_mfee, track_pfee, success_fee, cash_fee,
    out_fee, out_stamp_duty, output_penalty, advice_fee, overnight, over_com."""

    TAX = "tax"
    """Generic налоги, не привязанные к конкретной операции. Атрибутятся
    как ATTRIBUTABLE_FEE. tax, tax_progressive, benefit_tax,
    benefit_tax_progressive, tax_correction*, tax_repo* (6 типов)."""

    INCOME = "income"
    """Дивиденды, купоны, погашения, экспирации с прибылью. Cash inflow.
    Распределяются как ATTRIBUTABLE_FEE с противоположным знаком.
    dividend, dividend_transfer, div_ext, coupon, bond_repayment*,
    future_expiration, option_expiration, over_income, over_placement."""

    INCOME_TAX = "income_tax"
    """Налоги привязанные к источнику дохода (дивидендный/купонный).
    dividend_tax*, bond_tax*, tax_correction_coupon. Cash outflow,
    атрибутятся к open/closed trades того же инструмента."""

    DELIVERY = "delivery"
    """Физическая поставка futures с базовым активом. Конвертирует futures
    позицию в позицию по базе. delivery_buy, delivery_sell.
    Редкий кейс — обрабатывается как trade пар базы."""

    UNKNOWN = "unknown"
    """Новый OperationType добавленный в API но ещё не классифицированный.
    Прод-логи попадают в Sentry breadcrumb."""


# Полная мапа OperationType.value → CashFlowCategory.
# При добавлении нового OperationType сюда ОБЯЗАТЕЛЬНО добавить запись —
# `assert_complete_coverage()` тест fails иначе.
CASH_FLOW_MAP: dict[str, CashFlowCategory] = {
    # ── Trades ────────────────────────────────────────────────
    OperationType.BUY.value: CashFlowCategory.TRADE,
    OperationType.SELL.value: CashFlowCategory.TRADE,
    OperationType.BUY_CARD.value: CashFlowCategory.TRADE,
    OperationType.SELL_CARD.value: CashFlowCategory.TRADE,
    OperationType.BUY_MARGIN.value: CashFlowCategory.TRADE,
    OperationType.SELL_MARGIN.value: CashFlowCategory.TRADE,

    # ── Income (dividends / coupons / repayments) ────────────
    OperationType.DIVIDEND.value: CashFlowCategory.INCOME,
    OperationType.DIVIDEND_TRANSFER.value: CashFlowCategory.INCOME,
    OperationType.DIV_EXT.value: CashFlowCategory.INCOME,
    OperationType.COUPON.value: CashFlowCategory.INCOME,
    OperationType.BOND_REPAYMENT.value: CashFlowCategory.INCOME,
    OperationType.BOND_REPAYMENT_FULL.value: CashFlowCategory.INCOME,
    OperationType.FUTURE_EXPIRATION.value: CashFlowCategory.INCOME,
    OperationType.OPTION_EXPIRATION.value: CashFlowCategory.INCOME,

    # ── Income taxes (linked to source) ───────────────────────
    OperationType.DIVIDEND_TAX.value: CashFlowCategory.INCOME_TAX,
    OperationType.DIVIDEND_TAX_PROGRESSIVE.value: CashFlowCategory.INCOME_TAX,
    OperationType.BOND_TAX.value: CashFlowCategory.INCOME_TAX,
    OperationType.BOND_TAX_PROGRESSIVE.value: CashFlowCategory.INCOME_TAX,
    OperationType.TAX_CORRECTION_COUPON.value: CashFlowCategory.INCOME_TAX,

    # ── Variation margin ──────────────────────────────────────
    OperationType.ACCRUING_VARMARGIN.value: CashFlowCategory.VARMARGIN,
    OperationType.WRITING_OFF_VARMARGIN.value: CashFlowCategory.VARMARGIN,

    # ── Delivery (физ. поставка futures) ──────────────────────
    OperationType.DELIVERY_BUY.value: CashFlowCategory.DELIVERY,
    OperationType.DELIVERY_SELL.value: CashFlowCategory.DELIVERY,

    # ── Broker commission per-trade ───────────────────────────
    OperationType.BROKER_FEE.value: CashFlowCategory.BROKER_COMMISSION,

    # ── Attributable fees (account-level, по notional split) ──
    OperationType.MARGIN_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.SERVICE_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.TRACK_MFEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.TRACK_PFEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.SUCCESS_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.CASH_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.OUT_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.OUT_STAMP_DUTY.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.OUTPUT_PENALTY.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.ADVICE_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.OVERNIGHT.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.OVER_COM.value: CashFlowCategory.ATTRIBUTABLE_FEE,

    # ── Overnight income (репо placement income) ──────────────
    OperationType.OVER_PLACEMENT.value: CashFlowCategory.INCOME,
    OperationType.OVER_INCOME.value: CashFlowCategory.INCOME,

    # ── Generic taxes (не привязаны к source) ─────────────────
    OperationType.TAX.value: CashFlowCategory.TAX,
    OperationType.TAX_PROGRESSIVE.value: CashFlowCategory.TAX,
    OperationType.BENEFIT_TAX.value: CashFlowCategory.TAX,
    OperationType.BENEFIT_TAX_PROGRESSIVE.value: CashFlowCategory.TAX,
    OperationType.TAX_CORRECTION.value: CashFlowCategory.TAX,
    OperationType.TAX_CORRECTION_PROGRESSIVE.value: CashFlowCategory.TAX,
    OperationType.TAX_REPO.value: CashFlowCategory.TAX,
    OperationType.TAX_REPO_PROGRESSIVE.value: CashFlowCategory.TAX,
    OperationType.TAX_REPO_HOLD.value: CashFlowCategory.TAX,
    OperationType.TAX_REPO_HOLD_PROGRESSIVE.value: CashFlowCategory.TAX,
    OperationType.TAX_REPO_REFUND.value: CashFlowCategory.TAX,
    OperationType.TAX_REPO_REFUND_PROGRESSIVE.value: CashFlowCategory.TAX,

    # ── External cash deposits/withdrawals ────────────────────
    OperationType.INPUT.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.OUTPUT.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.INPUT_SWIFT.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.OUTPUT_SWIFT.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.INPUT_ACQUIRING.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.OUTPUT_ACQUIRING.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.INPUT_MULTI.value: CashFlowCategory.NET_DEPOSIT,
    OperationType.OUT_MULTI.value: CashFlowCategory.NET_DEPOSIT,

    # ── Security transfers (no cash impact) ───────────────────
    OperationType.INPUT_SECURITIES.value: CashFlowCategory.SECURITY_TRANSFER,
    OperationType.OUTPUT_SECURITIES.value: CashFlowCategory.SECURITY_TRANSFER,

    # ── Internal transfers between accounts of same user ──────
    OperationType.TRANS_IIS_BS.value: CashFlowCategory.INTERNAL_TRANSFER,
    OperationType.TRANS_BS_BS.value: CashFlowCategory.INTERNAL_TRANSFER,

    # ── Misc placeholders ─────────────────────────────────────
    OperationType.UNSPECIFIED.value: CashFlowCategory.UNKNOWN,
    OperationType.OTHER_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    OperationType.PRIMARY_ORDER.value: CashFlowCategory.TRADE,
    OperationType.DFA_REDEMPTION.value: CashFlowCategory.INCOME,
    OperationType.OTHER.value: CashFlowCategory.UNKNOWN,
}


def classify(op_type_value: str) -> CashFlowCategory:
    """Возвращает категорию для строкового значения OperationType.

    Для неизвестного типа (новый в API, без записи в CASH_FLOW_MAP) —
    UNKNOWN. Caller'ы обычно логируют в Sentry breadcrumb.
    """
    return CASH_FLOW_MAP.get(op_type_value, CashFlowCategory.UNKNOWN)


def operation_types_in(category: CashFlowCategory) -> set[str]:
    """Возвращает множество OperationType.value входящих в категорию."""
    return {op_type for op_type, cat in CASH_FLOW_MAP.items() if cat == category}


def assert_complete_coverage() -> None:
    """Все значения OperationType enum должны быть в CASH_FLOW_MAP.

    Защита от регрессии: при добавлении нового OperationType в enums.py
    но забывании здесь — этот assertion в test_cash_flow_classification.py
    падает. См. `tests/unit/test_cash_flow_classification.py::test_coverage_invariant`.
    """
    enum_values = {op.value for op in OperationType}
    map_keys = set(CASH_FLOW_MAP.keys())
    missing = enum_values - map_keys
    extra = map_keys - enum_values
    if missing or extra:
        msg = []
        if missing:
            msg.append(f"OperationType values без классификации: {sorted(missing)}")
        if extra:
            msg.append(f"CASH_FLOW_MAP содержит несуществующие OperationType: {sorted(extra)}")
        raise AssertionError("; ".join(msg))


# Категории, для которых attribution делает proportional split по trades.
ATTRIBUTABLE_CATEGORIES: frozenset[CashFlowCategory] = frozenset({
    CashFlowCategory.VARMARGIN,
    CashFlowCategory.ATTRIBUTABLE_FEE,
    CashFlowCategory.TAX,
    CashFlowCategory.INCOME,
    CashFlowCategory.INCOME_TAX,
})

# Категории-cash flows которые ВЛИЯЮТ на total cash balance (для reconcile).
CASH_IMPACTING_CATEGORIES: frozenset[CashFlowCategory] = frozenset({
    CashFlowCategory.NET_DEPOSIT,
    CashFlowCategory.TRADE,
    CashFlowCategory.VARMARGIN,
    CashFlowCategory.BROKER_COMMISSION,
    CashFlowCategory.ATTRIBUTABLE_FEE,
    CashFlowCategory.TAX,
    CashFlowCategory.INCOME,
    CashFlowCategory.INCOME_TAX,
    CashFlowCategory.DELIVERY,
})

# Категории НЕ-cash (paper transfers, internal moves).
NON_CASH_CATEGORIES: frozenset[CashFlowCategory] = frozenset({
    CashFlowCategory.SECURITY_TRANSFER,
    CashFlowCategory.INTERNAL_TRANSFER,
})

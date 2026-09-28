"""Coverage invariant + smoke tests для CashFlowCategory classification.

Главный тест — `test_coverage_invariant`: ловит ситуацию когда новый
OperationType добавлен в enum но не вписан в CASH_FLOW_MAP.
"""
from __future__ import annotations

import pytest

from domain.enums import OperationType
from domain.pnl.cash_flow_classification import (
    ATTRIBUTABLE_CATEGORIES,
    CASH_FLOW_MAP,
    CASH_IMPACTING_CATEGORIES,
    NON_CASH_CATEGORIES,
    CashFlowCategory,
    assert_complete_coverage,
    classify,
    operation_types_in,
)


def test_coverage_invariant():
    """Каждый OperationType.value должен быть в CASH_FLOW_MAP.

    Если упало — кто-то добавил новый тип в enum, но забыл сюда. Добавь
    запись в `domain/pnl/cash_flow_classification.py::CASH_FLOW_MAP`.
    """
    assert_complete_coverage()


def test_no_extra_keys():
    """CASH_FLOW_MAP не должен содержать ключей которых нет в enum."""
    enum_values = {op.value for op in OperationType}
    extra = set(CASH_FLOW_MAP.keys()) - enum_values
    assert extra == set(), f"CASH_FLOW_MAP содержит лишние ключи: {extra}"


@pytest.mark.parametrize(
    "op_type,expected_category",
    [
        (OperationType.INPUT, CashFlowCategory.NET_DEPOSIT),
        (OperationType.OUTPUT, CashFlowCategory.NET_DEPOSIT),
        (OperationType.INPUT_SWIFT, CashFlowCategory.NET_DEPOSIT),
        (OperationType.OUTPUT_SWIFT, CashFlowCategory.NET_DEPOSIT),
        (OperationType.INPUT_ACQUIRING, CashFlowCategory.NET_DEPOSIT),
        (OperationType.OUTPUT_ACQUIRING, CashFlowCategory.NET_DEPOSIT),
        (OperationType.INPUT_MULTI, CashFlowCategory.NET_DEPOSIT),
        (OperationType.OUT_MULTI, CashFlowCategory.NET_DEPOSIT),
        (OperationType.BUY, CashFlowCategory.TRADE),
        (OperationType.SELL, CashFlowCategory.TRADE),
        (OperationType.ACCRUING_VARMARGIN, CashFlowCategory.VARMARGIN),
        (OperationType.WRITING_OFF_VARMARGIN, CashFlowCategory.VARMARGIN),
        (OperationType.BROKER_FEE, CashFlowCategory.BROKER_COMMISSION),
        (OperationType.MARGIN_FEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.SERVICE_FEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.TRACK_MFEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.TRACK_PFEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.SUCCESS_FEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.OVERNIGHT, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.TAX, CashFlowCategory.TAX),
        (OperationType.TAX_PROGRESSIVE, CashFlowCategory.TAX),
        (OperationType.TAX_REPO, CashFlowCategory.TAX),
        (OperationType.DIVIDEND, CashFlowCategory.INCOME),
        (OperationType.COUPON, CashFlowCategory.INCOME),
        (OperationType.OPTION_EXPIRATION, CashFlowCategory.INCOME),
        (OperationType.FUTURE_EXPIRATION, CashFlowCategory.INCOME),
        (OperationType.DIVIDEND_TAX, CashFlowCategory.INCOME_TAX),
        (OperationType.BOND_TAX, CashFlowCategory.INCOME_TAX),
        (OperationType.INPUT_SECURITIES, CashFlowCategory.SECURITY_TRANSFER),
        (OperationType.OUTPUT_SECURITIES, CashFlowCategory.SECURITY_TRANSFER),
        (OperationType.TRANS_IIS_BS, CashFlowCategory.INTERNAL_TRANSFER),
        (OperationType.TRANS_BS_BS, CashFlowCategory.INTERNAL_TRANSFER),
        (OperationType.DELIVERY_BUY, CashFlowCategory.DELIVERY),
        (OperationType.DELIVERY_SELL, CashFlowCategory.DELIVERY),
        (OperationType.OTHER_FEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.OTHER, CashFlowCategory.UNKNOWN),
        (OperationType.DFA_REDEMPTION, CashFlowCategory.INCOME),
        (OperationType.PRIMARY_ORDER, CashFlowCategory.TRADE),
    ],
)
def test_classify_canonical(op_type: OperationType, expected_category: CashFlowCategory):
    """Smoke check: основные типы попадают в ожидаемые категории."""
    assert classify(op_type.value) == expected_category


def test_classify_unknown_returns_unknown_category():
    """Несуществующее значение → UNKNOWN (без exception)."""
    assert classify("future_api_addition_2030") == CashFlowCategory.UNKNOWN


def test_net_deposit_set_includes_all_external_channels():
    """NET_DEPOSIT должен включать все каналы внешних cash flows.

    Это явный sanity-check на B1/B2 bug из плана.
    """
    deposit_types = operation_types_in(CashFlowCategory.NET_DEPOSIT)
    expected = {
        "input", "output",
        "input_swift", "output_swift",
        "input_acquiring", "output_acquiring",
        "inp_multi", "out_multi",
    }
    assert deposit_types == expected, (
        f"NET_DEPOSIT не покрывает все каналы:\n"
        f"  в наборе: {deposit_types}\n"
        f"  ожидалось: {expected}\n"
        f"  упущены: {expected - deposit_types}"
    )


def test_no_overlap_between_categories():
    """Каждый OperationType.value в ровно одной категории."""
    counts: dict[str, int] = {}
    for op_type in CASH_FLOW_MAP:
        counts[op_type] = counts.get(op_type, 0) + 1
    duplicates = {k for k, v in counts.items() if v > 1}
    assert duplicates == set(), f"OperationType в нескольких категориях: {duplicates}"


def test_attributable_categories_disjoint_from_non_cash():
    """ATTRIBUTABLE категории не должны быть NON_CASH (взаимоисключающие)."""
    assert ATTRIBUTABLE_CATEGORIES.isdisjoint(NON_CASH_CATEGORIES)


def test_cash_impacting_covers_attributable():
    """Все ATTRIBUTABLE категории должны быть CASH_IMPACTING."""
    assert ATTRIBUTABLE_CATEGORIES.issubset(CASH_IMPACTING_CATEGORIES)


def test_trade_is_cash_impacting_but_not_attributable():
    """TRADE даёт cash flow (BUY=cash out, SELL=cash in) но обрабатывается
    FIFO matcher'ом напрямую, не через attribution split."""
    assert CashFlowCategory.TRADE in CASH_IMPACTING_CATEGORIES
    assert CashFlowCategory.TRADE not in ATTRIBUTABLE_CATEGORIES


def test_security_transfer_is_non_cash():
    """input_securities / output_securities — paper transfers, no cash impact."""
    assert CashFlowCategory.SECURITY_TRANSFER in NON_CASH_CATEGORIES
    assert CashFlowCategory.SECURITY_TRANSFER not in CASH_IMPACTING_CATEGORIES


def test_internal_transfer_is_non_cash():
    """trans_iis_bs / trans_bs_bs — внутренний между счетами, зеркальная запись."""
    assert CashFlowCategory.INTERNAL_TRANSFER in NON_CASH_CATEGORIES
    assert CashFlowCategory.INTERNAL_TRANSFER not in CASH_IMPACTING_CATEGORIES


def test_all_12_tax_variants_present():
    """Все 12 tax типов должны быть в TAX категории."""
    tax_set = operation_types_in(CashFlowCategory.TAX)
    expected_tax = {
        "tax", "tax_progressive",
        "benefit_tax", "benefit_tax_progressive",
        "tax_correction", "tax_correction_progressive",
        "tax_repo", "tax_repo_progressive",
        "tax_repo_hold", "tax_repo_hold_progressive",
        "tax_repo_refund", "tax_repo_refund_progressive",
    }
    assert tax_set == expected_tax, (
        f"TAX категория не покрывает все 12 tax вариантов.\n"
        f"  в наборе: {tax_set}\n"
        f"  упущены: {expected_tax - tax_set}"
    )

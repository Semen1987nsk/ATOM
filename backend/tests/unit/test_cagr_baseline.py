"""MATH-07: canonical CAGR baseline через net_deposits.

Spec cash-anchored: baseline = Σ NET_DEPOSIT operations, НЕ user-provided
`account.initial_balance`. Helper переиспользуется в /stats/, /stats/advanced,
/stats/benchmark — иначе три карточки показывают три разных CAGR.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from analytics._common_baseline import compute_cagr_baseline


class _Flow:
    """Минимальная двойка для эмуляции CashFlowORM / domain CashFlow."""

    def __init__(self, category, amount):
        self.category = category
        self.amount = amount


def test_cagr_baseline_sums_net_deposits():
    flows = [
        _Flow("NET_DEPOSIT", Decimal("100000")),
        _Flow("NET_DEPOSIT", Decimal("50000")),
        _Flow("NET_DEPOSIT", Decimal("-20000")),  # withdrawal — учитываем со знаком
        _Flow("TRADE", Decimal("5000")),  # не deposit
        _Flow("COMMISSION", Decimal("-100")),  # не deposit
    ]
    assert compute_cagr_baseline(flows) == Decimal("130000")


def test_cagr_baseline_empty():
    assert compute_cagr_baseline([]) == Decimal("0")


def test_cagr_baseline_works_with_dicts():
    flows = [
        {"category": "NET_DEPOSIT", "amount": "100000"},
        {"category": "TRADE", "amount": "5000"},
    ]
    assert compute_cagr_baseline(flows) == Decimal("100000")


def test_cagr_baseline_handles_enum_category():
    """CashFlowCategory enum имеет .value='net_deposit' — str(enum) даёт
    'CashFlowCategory.NET_DEPOSIT', что содержит NET_DEPOSIT. Должно работать."""

    class _FakeEnum:
        def __str__(self) -> str:
            return "CashFlowCategory.NET_DEPOSIT"

    flows = [_Flow(_FakeEnum(), Decimal("1000"))]
    assert compute_cagr_baseline(flows) == Decimal("1000")


def test_cagr_baseline_handles_lowercase_string():
    """Сериализованная категория 'net_deposit' (нижний регистр) тоже считается."""
    flows = [
        _Flow("net_deposit", Decimal("100")),
        _Flow("net_deposit", Decimal("-30")),
    ]
    assert compute_cagr_baseline(flows) == Decimal("70")


def test_cagr_baseline_ignores_missing_amount():
    """None amount не должен ломать сумму."""
    flows = [
        _Flow("NET_DEPOSIT", None),
        _Flow("NET_DEPOSIT", Decimal("100")),
    ]
    assert compute_cagr_baseline(flows) == Decimal("100")


def test_cagr_baseline_returns_decimal_not_float():
    """Тип результата — Decimal, чтобы не было float drift для крупных балансов."""
    flows = [_Flow("NET_DEPOSIT", Decimal("100"))]
    result = compute_cagr_baseline(flows)
    assert isinstance(result, Decimal)


def test_cagr_baseline_zero_when_only_other_categories():
    """Если в потоке нет ни одного NET_DEPOSIT — baseline=0."""
    flows = [
        _Flow("TRADE", Decimal("1000")),
        _Flow("COMMISSION", Decimal("-10")),
        _Flow("VARMARGIN", Decimal("50")),
    ]
    assert compute_cagr_baseline(flows) == Decimal("0")

"""Phase 6.4 (2026-05-18): unit tests для journal-style headline.

Headline = realized_closed + unrealized_position_based (per-trade view, matches
Дневник сделок). cash_truth_pnl surface'ится отдельным полем для broker
reconciliation badge'а.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.pnl.dashboard_pnl import compute_pnl_headline


# Snapshot acc#4 на 2026-05-18: 333 closed trades, 11 open futures.
ACC4_INPUTS = dict(
    realized_closed=Decimal("-174421.80"),
    realized_closed_gross=Decimal("-69131.85"),
    unrealized_position_based=Decimal("-73492.76"),
    last_portfolio_value=Decimal("59448.22"),
    net_deposits=Decimal("308035.79"),
    broker_commission_raw=Decimal("-56773.90"),
    attributable_fee_raw=Decimal("-51160.00"),
    tax_raw=Decimal("-156.00"),
    income_tax_raw=Decimal("0"),
)


def test_headline_equals_realized_plus_unrealized():
    """Phase 6.4 main invariant: headline = closed + open unrealized."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected = Decimal("-174421.80") + Decimal("-73492.76")  # -247914.56
    assert abs(result["total_pnl_with_unrealized"] - expected) < Decimal("0.01")


def test_gross_headline_equals_realized_gross_plus_unrealized():
    """Gross variant — same formula с realized_gross (без commission в closed)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected_gross = Decimal("-69131.85") + Decimal("-73492.76")  # -142624.61
    assert abs(result["total_pnl_with_unrealized_gross"] - expected_gross) < Decimal("0.01")


def test_cash_truth_pnl_surfaced_separately():
    """cash_truth_pnl = portfolio − deposits, для health badge / reconciliation."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected = Decimal("59448.22") - Decimal("308035.79")  # -248587.57
    assert abs(result["cash_truth_pnl"] - expected) < Decimal("0.01")


def test_natural_residual_is_cash_truth_minus_headline():
    """residual = cash_truth − headline (info-only). Должен быть мал на здоровом
    аккаунте — orphan dividends / post-clearing varmargin не покрытые per-trade.
    Для acc#4: cash_truth -248587 минус headline -247914 = -673 RUB."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected_residual = Decimal("-248587.57") - Decimal("-247914.56")
    assert abs(result["natural_residual"] - expected_residual) < Decimal("0.01")
    assert abs(result["natural_residual"]) < Decimal("1000")


def test_total_costs_is_sum_of_cost_categories():
    """total_costs = broker + attr_fee + tax + income_tax (signed negative)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected = Decimal("-56773.90") + Decimal("-51160") + Decimal("-156") + Decimal("0")
    assert abs(result["total_costs"] - expected) < Decimal("0.01")
    assert result["total_costs"] < 0


def test_zero_balance_account_returns_zeros():
    """Empty account: все суммы 0 → всё 0."""
    result = compute_pnl_headline(
        realized_closed=Decimal("0"),
        realized_closed_gross=Decimal("0"),
        unrealized_position_based=Decimal("0"),
        last_portfolio_value=Decimal("0"),
        net_deposits=Decimal("0"),
        broker_commission_raw=Decimal("0"),
        attributable_fee_raw=Decimal("0"),
        tax_raw=Decimal("0"),
        income_tax_raw=Decimal("0"),
    )
    assert result["total_pnl_with_unrealized"] == Decimal("0")
    assert result["total_pnl_with_unrealized_gross"] == Decimal("0")
    assert result["cash_truth_pnl"] == Decimal("0")
    assert result["total_costs"] == Decimal("0")
    assert result["natural_residual"] == Decimal("0")


def test_deposit_only_account_has_zero_pnl_and_zero_residual():
    """Депозит без сделок: portfolio = deposits → cash_truth=0, headline=0."""
    result = compute_pnl_headline(
        realized_closed=Decimal("0"),
        realized_closed_gross=Decimal("0"),
        unrealized_position_based=Decimal("0"),
        last_portfolio_value=Decimal("100000"),
        net_deposits=Decimal("100000"),
        broker_commission_raw=Decimal("0"),
        attributable_fee_raw=Decimal("0"),
        tax_raw=Decimal("0"),
        income_tax_raw=Decimal("0"),
    )
    assert result["total_pnl_with_unrealized"] == Decimal("0")
    assert result["cash_truth_pnl"] == Decimal("0")
    assert result["natural_residual"] == Decimal("0")


def test_profitable_account_with_dividends_orphan():
    """Аккаунт с прибылью + дивиденд после закрытия позиции.
    Дивиденд +500 не учтён в realized (закрытая trade не получала div),
    но он в portfolio. Поэтому: headline=8000+3000=11000, cash_truth=11500,
    natural_residual=+500 (это orphan dividend)."""
    result = compute_pnl_headline(
        realized_closed=Decimal("8000"),
        realized_closed_gross=Decimal("10000"),
        unrealized_position_based=Decimal("3000"),
        last_portfolio_value=Decimal("111500"),
        net_deposits=Decimal("100000"),
        broker_commission_raw=Decimal("-2000"),
        attributable_fee_raw=Decimal("0"),
        tax_raw=Decimal("0"),
        income_tax_raw=Decimal("-150"),
    )
    assert result["total_pnl_with_unrealized"] == Decimal("11000")
    assert result["cash_truth_pnl"] == Decimal("11500")
    assert result["natural_residual"] == Decimal("500")
    assert result["total_costs"] == Decimal("-2150")


def test_headline_cash_equals_cash_truth():
    result = compute_pnl_headline(**ACC4_INPUTS)
    assert result["headline_cash"] == result["cash_truth_pnl"]


def test_clearing_adjustment_closes_identity():
    """realized + unrealized + clearing_adjustment == headline_cash (to the kopeck)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    lhs = (ACC4_INPUTS["realized_closed"]
           + ACC4_INPUTS["unrealized_position_based"]
           + result["clearing_adjustment"])
    assert abs(lhs - result["headline_cash"]) < Decimal("0.01")


def test_clearing_adjustment_equals_natural_residual():
    result = compute_pnl_headline(**ACC4_INPUTS)
    assert result["clearing_adjustment"] == result["natural_residual"]

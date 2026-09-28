"""Dashboard P&L headline — journal-style (Phase 6.4).

Phase 6.4 (2026-05-18): headline = `realized_closed + unrealized_position_based`
matches per-trade view in Дневник сделок. cash_truth_pnl surfaces broker
reality separately for the PnLHealthBadge / reconciliation card.

History:
- Phase 7 (2026-05-17): `realized + unrealized + orphan_adjustments` — double-
  counted varmargin для open futures → 2% overshoot vs broker.
- Phase 6.3 (2026-05-18 AM): anchored headline = cash_truth — matched broker
  but diverged from journal page by natural_residual (~0.2%).
- Phase 6.4 (this): journal-style headline + broker delta as separate signal
  (best practice — Tradervue, TraderSync, TradeZella, IBKR).

См. `tests/unit/test_dashboard_pnl_headline.py` для invariants.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict


class DashboardHeadline(TypedDict):
    total_pnl_with_unrealized: Decimal
    total_pnl_with_unrealized_gross: Decimal
    cash_truth_pnl: Decimal
    total_costs: Decimal
    natural_residual: Decimal
    headline_cash: Decimal
    clearing_adjustment: Decimal


def compute_pnl_headline(
    *,
    realized_closed: Decimal,
    realized_closed_gross: Decimal,
    unrealized_position_based: Decimal,
    last_portfolio_value: Decimal,
    net_deposits: Decimal,
    broker_commission_raw: Decimal,
    attributable_fee_raw: Decimal,
    tax_raw: Decimal,
    income_tax_raw: Decimal,
) -> DashboardHeadline:
    total_pnl_with_unrealized = realized_closed + unrealized_position_based
    total_pnl_with_unrealized_gross = realized_closed_gross + unrealized_position_based

    cash_truth_pnl = last_portfolio_value - net_deposits
    natural_residual = cash_truth_pnl - total_pnl_with_unrealized

    total_costs = (
        broker_commission_raw
        + attributable_fee_raw
        + tax_raw
        + income_tax_raw
    )

    # Cash-anchored headline: main number = real money (portfolio - deposits).
    headline_cash = cash_truth_pnl
    # clearing_adjustment = named natural_residual: futures variation margin the
    # API does not attribute to specific trades (ADR-0008). Identity:
    # realized + unrealized + clearing_adjustment == headline_cash.
    clearing_adjustment = natural_residual

    return {
        "total_pnl_with_unrealized": total_pnl_with_unrealized,
        "total_pnl_with_unrealized_gross": total_pnl_with_unrealized_gross,
        "cash_truth_pnl": cash_truth_pnl,
        "total_costs": total_costs,
        "natural_residual": natural_residual,
        "headline_cash": headline_cash,
        "clearing_adjustment": clearing_adjustment,
    }

"""MATH-06: Sharpe/Sortino возвращают per_trade + annualized структуру."""
import math
import pytest
from analytics.risk import calculate_sharpe_sortino


def test_sharpe_sortino_returns_dict_structure():
    pnls = [100.0, -50.0, 200.0, -30.0, 150.0, -80.0, 120.0]
    result = calculate_sharpe_sortino(pnls, trades_per_year=252)

    assert isinstance(result["sharpe"], dict)
    assert "per_trade" in result["sharpe"]
    assert "annualized" in result["sharpe"]
    assert result["sharpe"]["trades_per_year"] == 252


def test_sharpe_annualized_equals_per_trade_times_sqrt_n():
    pnls = [100.0, -50.0, 200.0, -30.0, 150.0, -80.0, 120.0]
    result = calculate_sharpe_sortino(pnls, trades_per_year=252)

    per_trade = result["sharpe"]["per_trade"]
    annualized = result["sharpe"]["annualized"]
    assert annualized == pytest.approx(per_trade * math.sqrt(252), rel=0.01)


def test_sortino_same_structure():
    pnls = [100.0, -50.0, 200.0, -30.0, 150.0, -80.0, 120.0]
    result = calculate_sharpe_sortino(pnls, trades_per_year=252)
    assert isinstance(result["sortino"], dict)
    assert "per_trade" in result["sortino"]
    assert "annualized" in result["sortino"]


def test_sharpe_no_annualization_when_trades_per_year_none():
    """Без trades_per_year — annualized=None, остальное как раньше."""
    pnls = [100.0, -50.0, 200.0, -30.0]
    result = calculate_sharpe_sortino(pnls)  # default trades_per_year=None
    assert result["sharpe"]["per_trade"] is not None
    assert result["sharpe"]["annualized"] is None
    assert result["sharpe"]["trades_per_year"] is None

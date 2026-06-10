"""MATH-04: Vince classic gambler's ruin RoR."""
import pytest
from analytics.risk import calculate_risk_of_ruin


def test_ror_zero_edge_returns_100_pct():
    """Edge=0 (50/50 без payoff) → ruin почти гарантирован."""
    result = calculate_risk_of_ruin(win_rate=0.5, payoff_ratio=1.0, risk_per_trade=0.02)
    # edge=0, ratio=1, 1^N=1 → 100%
    assert result["ror_20pct"] == pytest.approx(100.0, abs=0.1)


def test_ror_positive_edge_vince_exact():
    """win_rate=0.6, payoff=1, risk=2% → edge=0.2; N_20pct=10
    → RoR_20% = (0.8/1.2)^10 × 100"""
    result = calculate_risk_of_ruin(win_rate=0.6, payoff_ratio=1.0, risk_per_trade=0.02)
    expected = ((1 - 0.2) / (1 + 0.2)) ** 10 * 100
    assert result["ror_20pct"] == pytest.approx(expected, rel=0.01)


def test_ror_negative_edge_returns_100():
    """Negative edge → ruin гарантирован."""
    result = calculate_risk_of_ruin(win_rate=0.4, payoff_ratio=1.0, risk_per_trade=0.02)
    assert result["ror_20pct"] == pytest.approx(100.0, abs=0.1)


def test_ror_risk_per_trade_scales_correctly():
    """Меньший risk_per_trade → больше capital_units → меньше RoR."""
    r1 = calculate_risk_of_ruin(win_rate=0.6, payoff_ratio=1.0, risk_per_trade=0.01)
    r2 = calculate_risk_of_ruin(win_rate=0.6, payoff_ratio=1.0, risk_per_trade=0.02)
    assert r1["ror_20pct"] < r2["ror_20pct"]


def test_ror_invalid_inputs_return_none():
    """win_rate=0 / 1 / negative payoff → None."""
    assert calculate_risk_of_ruin(win_rate=0.0, payoff_ratio=1.0)["ror_20pct"] is None
    assert calculate_risk_of_ruin(win_rate=1.0, payoff_ratio=1.0)["ror_20pct"] is None
    assert calculate_risk_of_ruin(win_rate=0.5, payoff_ratio=-1.0)["ror_20pct"] is None

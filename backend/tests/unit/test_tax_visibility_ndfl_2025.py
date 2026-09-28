from datetime import datetime

from analytics.advanced import calculate_tax_visibility


def test_ndfl_threshold_is_2_4m():
    year = datetime.utcnow().year
    trades = [{"pnl": 3_000_000, "exit_at": datetime(year, 6, 1)}]
    r = calculate_tax_visibility(trades)
    # 2_400_000*0.13 + 600_000*0.15 = 312_000 + 90_000 = 402_000
    assert r["estimated_tax"] == 402_000.0
    assert r["tax_rate_applied"] == 0.15


def test_ndfl_below_threshold_flat_13():
    year = datetime.utcnow().year
    trades = [{"pnl": 1_000_000, "exit_at": datetime(year, 6, 1)}]
    r = calculate_tax_visibility(trades)
    assert r["estimated_tax"] == 130_000.0
    assert r["tax_rate_applied"] == 0.13

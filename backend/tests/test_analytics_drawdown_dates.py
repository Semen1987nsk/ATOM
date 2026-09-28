"""Тесты для peak_date/trough_date в calculate_drawdown_stats."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.risk import calculate_drawdown_stats


def test_returns_peak_and_trough_dates_when_dates_provided():
    base = datetime(2026, 1, 1)
    pnls  = [+100, +200, -50, -300, -200, +50]
    dates = [base + timedelta(days=i*10) for i in range(6)]
    # initial=1000, balance: 1100, 1300, 1250, 950, 750, 800
    # peak=1300 (idx=1), trough=750 (idx=4, dd_abs=550)
    result = calculate_drawdown_stats(pnls, initial_balance=1000, dates=dates)

    assert result["peak_date"]   == dates[1].isoformat()
    assert result["trough_date"] == dates[4].isoformat()
    assert result["dd_duration_days"] == 30


def test_dates_optional_backwards_compatible():
    result = calculate_drawdown_stats([+100, -200, +50], initial_balance=1000)
    assert result["peak_date"] is None
    assert result["trough_date"] is None
    assert result["dd_duration_days"] is None
    assert "max_drawdown_pct" in result
    assert "max_drawdown_abs" in result

"""S3-11: profit_factor и r_expectancy берутся из calculate_advanced_stats."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


def test_win_loss_has_no_profit_factor():
    # Характеризуем корень: источник, из которого читали, не содержит ключа.
    wl = analytics.calculate_win_loss_stats([100.0, -50.0, 200.0])
    assert "profit_factor" not in wl


def test_advanced_stats_has_both_keys():
    adv = analytics.calculate_advanced_stats([100.0, -50.0, 200.0], [10.0, 10.0, 10.0])
    assert "profit_factor" in adv
    assert "r_expectancy" in adv
    assert adv["profit_factor"] is not None

"""S3-12: heatmap/daily_pnl/time_patterns бакетируют по МСК, не UTC."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.advanced import calculate_hour_dow_heatmap, calculate_daily_pnl  # noqa: E402
from analytics.distributions import analyze_time_patterns  # noqa: E402


def test_heatmap_hour_shifted_to_msk():
    # 07:00 UTC == 10:00 МСК (открытие основной сессии MOEX).
    rows = [{"entry_at": datetime(2026, 3, 2, 7, 0), "pnl": 100.0}]  # Пн
    m = calculate_hour_dow_heatmap(rows)
    assert m[0][10]["count"] == 1   # МСК-час 10
    assert m[0][7]["count"] == 0    # не UTC-час 7


def test_daily_pnl_late_session_stays_same_msk_day():
    # 22:30 UTC 1 марта == 01:30 МСК 2 марта — должно попасть на 2026-03-02.
    rows = [{"entry_at": datetime(2026, 3, 1, 22, 30), "pnl": 50.0}]
    out = calculate_daily_pnl(rows)
    assert out[0]["date"] == "2026-03-02"


def test_time_patterns_hour_msk():
    trades = [SimpleNamespace(pnl=100.0, net_pnl=100.0,
                              entry_at=datetime(2026, 3, 2, 7, 0))]
    tp = analyze_time_patterns(trades)
    hours = {h["hour"] for h in tp["hour_stats"]} if isinstance(tp, dict) and tp.get("hour_stats") else set()
    assert "10:00" in hours

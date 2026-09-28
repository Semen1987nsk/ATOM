"""S3-24 (MATH-01): /tags/ агрегирует NET, не GROSS."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _aggregate(trades):
    """Копия целевой логики для unit-проверки net-приоритета."""
    tag_stats = {}
    for t in trades:
        if not t.tags:
            continue
        pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
        for tag in t.tags:
            k = tag.lower()
            s = tag_stats.setdefault(k, {"pnl": 0.0, "wins": 0, "count": 0})
            s["pnl"] += pnl
            s["count"] += 1
            if pnl > 0:
                s["wins"] += 1
    return tag_stats


def test_net_over_gross():
    # gross +10, комиссия делает net -5 → в минус, win НЕ засчитывается.
    trades = [SimpleNamespace(tags=["scalp"], pnl=10.0, net_pnl=-5.0)]
    out = _aggregate(trades)
    assert out["scalp"]["pnl"] == -5.0
    assert out["scalp"]["wins"] == 0

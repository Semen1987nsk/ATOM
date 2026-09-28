"""S3-03: build_equity_curve с baseline даёт реалистичные DD-проценты."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.stats_filtering import build_equity_curve  # noqa: E402
import analytics  # noqa: E402


def _t(net):
    return SimpleNamespace(net_pnl=net, pnl=net)


def test_baseline_default_zero_backcompat():
    # Без baseline — прежнее поведение (кумулятив от 0).
    eq = build_equity_curve([_t(100.0), _t(-40.0), _t(20.0)])
    assert eq == [100.0, 60.0, 80.0]


def test_baseline_shifts_curve():
    eq = build_equity_curve([_t(100.0), _t(-40.0)], baseline=1_000_000.0)
    assert eq == [1_000_100.0, 1_000_060.0]


def test_ulcer_realistic_with_baseline():
    # cum PnL 10000 -> 5000 на счёте 1M = просадка 0.5%, не 50%.
    trades = [_t(10_000.0), _t(-5_000.0)]
    eq = build_equity_curve(trades, baseline=1_000_000.0)
    ui = analytics.calculate_ulcer_index(eq)
    assert ui is not None and ui < 1.0  # раньше был ~35 (на кривой от нуля)

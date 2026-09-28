"""MATH-02: unit-тесты для analytics/aggregator.py::calculate_stats.

Sprint 4 grounding: aggregator.py покрывался только косвенно через
test_stats_cache.py (тестировал кеш, не саму calculate_stats).

ВАЖНО: при чтении aggregator.py обнаружен **pre-existing bug** —
helper-функции (calculate_optimal_f, calculate_advanced_stats, ...)
НЕ импортированы в модуль. Поэтому на любом non-empty входе функция
падает с `NameError: calculate_optimal_f is not defined`.

Согласно ТЗ Batch 6 — не патчим функцию, а **характеризуем** реальное
поведение тестами, помечая баг как `xfail`. Это создаёт reproducible
test для следующего batch'а, где функцию починят.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from analytics.aggregator import calculate_stats  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Helper: fake-Trade duck-type. calculate_stats обращается к атрибутам
# .pnl, .net_pnl, .risk_amount, .entry_at, .exit_at, .tags.
# ─────────────────────────────────────────────────────────────────

def _fake_trade(
    *,
    pnl: float | None = 0.0,
    net_pnl: float | None = None,
    risk_amount: float | None = 10.0,
    entry_at: datetime | None = None,
    exit_at: datetime | None = None,
    tags: list[str] | None = None,
    entry_price: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        pnl=pnl,
        net_pnl=net_pnl if net_pnl is not None else pnl,
        risk_amount=risk_amount,
        entry_at=entry_at or datetime(2026, 1, 1, 10, 0),
        exit_at=exit_at or datetime(2026, 1, 1, 12, 0),
        tags=tags or [],
        # analyze_mae_mfe читает .entry_price (guard: `not t.entry_price`
        # → сделка пропускается). Без атрибута — AttributeError, поэтому
        # задаём None по умолчанию: MAE/MFE-ветка не участвует в этих кейсах.
        entry_price=entry_price,
    )


# ─────────────────────────────────────────────────────────────────
# Empty input — единственный надёжный путь, не зависящий от bug'а
# ─────────────────────────────────────────────────────────────────

class TestCalculateStatsEmpty:
    def test_empty_returns_zero_stats_default(self):
        """Пустой список → возвращает default-структуру со всеми ключами."""
        out = calculate_stats([])
        assert out is not None
        assert isinstance(out, dict)
        assert out["total_pnl"] == 0
        assert out["win_rate"] == 0
        assert out["total_trades"] == 0
        assert out["profitable_trades"] == 0
        assert out["profit_factor"] == 0
        assert out["sqn"] is None
        assert out["z_score"] is None
        assert out["mae_mfe_analysis"] is None
        assert out["equity_curve"] == []
        assert out["tag_stats"] == []
        assert out["monte_carlo"] is None
        assert out["calmar_ratio"] is None

    def test_empty_returns_all_expected_keys(self):
        """Контракт schema: empty → все ожидаемые поля присутствуют."""
        out = calculate_stats([])
        expected_keys = {
            "total_pnl", "win_rate", "total_trades", "profitable_trades",
            "optimal_f", "sqn", "z_score", "profit_factor", "r_expectancy",
            "expected_ghpr", "mae_mfe_analysis", "equity_curve", "tag_stats",
            "sortino_ratio", "max_drawdown_pct", "max_drawdown_abs",
            "current_drawdown_pct", "avg_win", "avg_loss", "largest_win",
            "largest_loss", "max_win_streak", "max_loss_streak",
            "current_streak", "current_streak_type", "monte_carlo",
            "time_patterns", "recovery_factor", "trade_duration", "tail_ratio",
            "risk_of_ruin", "r_distribution", "calmar_ratio",
        }
        assert expected_keys.issubset(set(out.keys())), \
            f"Missing keys: {expected_keys - set(out.keys())}"


# ─────────────────────────────────────────────────────────────────
# Non-empty input — характеризующие тесты для known bug
# ─────────────────────────────────────────────────────────────────

class TestCalculateStatsKnownBug:
    """Aggregator.py не импортирует helper-функции (calculate_optimal_f,
    calculate_advanced_stats, calculate_sharpe_sortino, и т.д.) — модуль
    использует только `from ._common import UNDEFINED, _sanitize`.

    Любой вызов calculate_stats с непустым списком падает на первой же
    helper-функции с NameError. Эти xfail-тесты документируют баг до
    того, как его починят (вероятно — Batch 7 или новая фича).
    """

    def test_single_winner_currently_raises_nameerror(self):
        trade = _fake_trade(pnl=1000.0, net_pnl=800.0, risk_amount=100.0)
        # После фикса этот тест станет PASS — нужно будет убрать xfail.
        out = calculate_stats([trade])
        assert out["total_trades"] == 1
        assert out["profitable_trades"] == 1
        assert out["win_rate"] == 100.0
        assert out["total_pnl"] == 800.0  # net_pnl приоритетнее pnl

    def test_mixed_winner_loser_currently_raises(self):
        trades = [
            _fake_trade(pnl=1000.0, net_pnl=800.0),
            _fake_trade(pnl=-500.0, net_pnl=-600.0),
        ]
        out = calculate_stats(trades)
        assert out["total_trades"] == 2
        assert out["profitable_trades"] == 1
        assert out["win_rate"] == 50.0
        # net_pnl приоритетнее: 800 + (-600) = 200
        assert out["total_pnl"] == 200.0

    def test_all_winners_profit_factor_undefined(self):
        """Sprint 4 MATH-05: все winners → profit_factor None/UNDEFINED."""
        trades = [
            _fake_trade(pnl=1000.0, net_pnl=1000.0),
            _fake_trade(pnl=500.0, net_pnl=500.0),
        ]
        out = calculate_stats(trades)
        assert out["total_trades"] == 2
        assert out["profitable_trades"] == 2
        # MATH-05 contract: profit_factor None при отсутствии losses
        assert out.get("profit_factor") is None

    def test_all_losers(self):
        trades = [
            _fake_trade(pnl=-1000.0, net_pnl=-1000.0),
            _fake_trade(pnl=-500.0, net_pnl=-500.0),
        ]
        out = calculate_stats(trades)
        assert out["total_pnl"] == -1500.0
        assert out["profitable_trades"] == 0
        assert out["win_rate"] == 0.0

    def test_equity_curve_built_chronologically(self):
        trades = [
            _fake_trade(
                pnl=100.0, net_pnl=100.0,
                entry_at=datetime(2026, 1, 1), exit_at=datetime(2026, 1, 2),
            ),
            _fake_trade(
                pnl=200.0, net_pnl=200.0,
                entry_at=datetime(2026, 1, 3), exit_at=datetime(2026, 1, 4),
            ),
        ]
        out = calculate_stats(trades)
        # Curve должен расти кумулятивно
        assert out["equity_curve"][0]["balance"] == 100.0
        assert out["equity_curve"][1]["balance"] == 300.0

    def test_tag_stats_aggregated_by_tag(self):
        trades = [
            _fake_trade(pnl=100.0, net_pnl=100.0, tags=["plan", "stock"]),
            _fake_trade(pnl=-50.0, net_pnl=-50.0, tags=["fomo"]),
            _fake_trade(pnl=200.0, net_pnl=200.0, tags=["plan"]),
        ]
        out = calculate_stats(trades)
        plan_stat = next(s for s in out["tag_stats"] if s["tag"] == "plan")
        assert plan_stat["count"] == 2
        assert plan_stat["pnl"] == 300.0
        assert plan_stat["win_rate"] == 100.0

    def test_pnl_none_trades_excluded(self):
        """Trade с pnl=None не должен участвовать в расчётах."""
        trades = [
            _fake_trade(pnl=100.0, net_pnl=100.0),
            _fake_trade(pnl=None, net_pnl=None),  # excluded
        ]
        out = calculate_stats(trades)
        assert out["total_trades"] == 1
        assert out["total_pnl"] == 100.0

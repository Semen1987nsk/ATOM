"""
Tests for analytics.advanced и analytics.benchmark.

Покрывают:
- Корректность расчёта Ulcer / K-Ratio / MAR / Omega / Sterling.
- Edge cases: пустые ряды, all-zeros, монотонная кривая (нулевая просадка).
- build_benchmark_response: synthetic vs real cohort, перцентили,
  lower_is_better metrics.
"""
from __future__ import annotations

import os
import sys
import math

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import advanced as adv  # noqa: E402
from analytics import benchmark as bm  # noqa: E402


# ──────────────────────────────────────────────────────────────────
#  Equity-curve metrics
# ──────────────────────────────────────────────────────────────────


class TestUlcerIndex:
    def test_monotonic_growth_zero_ulcer(self):
        # Без просадок — UI ≈ 0
        assert adv.calculate_ulcer_index([100, 110, 120, 130, 140]) == 0.0

    def test_known_drawdown(self):
        # Просадка 100→90 (−10%) и быстрое восстановление
        ui = adv.calculate_ulcer_index([100, 90, 100, 100])
        assert ui is not None
        # Ожидаем ~5: sqrt((10^2 + 0 + 0)/4) ≈ 5.0
        assert 4.5 <= ui <= 5.5

    def test_empty_returns_undefined(self):
        assert adv.calculate_ulcer_index([]) is None

    def test_single_point_returns_undefined(self):
        assert adv.calculate_ulcer_index([100]) is None


class TestKRatio:
    def test_too_few_points(self):
        assert adv.calculate_k_ratio([100, 110, 120]) is None

    def test_smooth_growth_high_k(self):
        # Идеально линейный рост → K высокий
        eq = [100 * (1 + 0.01) ** i for i in range(50)]
        k = adv.calculate_k_ratio(eq)
        assert k is not None
        assert k > 0.5

    def test_handles_negative_values(self):
        # Отрицательные значения сдвигаются — функция не падает
        eq = [-50, -10, 5, 30, 50, 80, 100, 120, 130, 150]
        k = adv.calculate_k_ratio(eq)
        assert k is not None


class TestMARRatio:
    def test_normal_case(self):
        # CAGR 30% / Max DD 10% → MAR = 3.0
        assert adv.calculate_mar_ratio(30.0, 10.0) == 3.0

    def test_zero_drawdown_returns_none(self):
        # division by zero → None (не Inf)
        assert adv.calculate_mar_ratio(20.0, 0.0) is None

    def test_none_inputs(self):
        assert adv.calculate_mar_ratio(None, 5.0) is None
        assert adv.calculate_mar_ratio(20.0, None) is None


class TestOmegaRatio:
    def test_only_gains_returns_none(self):
        # PF=∞ — math undefined → None (не магическое число)
        assert adv.calculate_omega_ratio([0.05, 0.03, 0.02]) is None

    def test_only_losses_returns_zero(self):
        # Все убытки → omega = 0 (нет gains)
        result = adv.calculate_omega_ratio([-0.02, -0.05])
        assert result == 0.0

    def test_balanced_returns_finite(self):
        # 2 gains по 0.05 + 1 loss 0.05 → omega = 0.10/0.05 = 2.0
        result = adv.calculate_omega_ratio([0.05, 0.05, -0.05])
        assert result == 2.0


class TestSterlingRatio:
    def test_normal_case(self):
        # Sterling = Annual / (avg(top3 DD) + 10%)
        # avg([25, 20, 15]) = 20, denom = 20 + 10 = 30, sterling = 30/30 = 1.0
        sr = adv.calculate_sterling_ratio(30.0, [25.0, 20.0, 15.0])
        assert sr == 1.0

    def test_low_drawdowns_defined(self):
        # avg DD < 10% → denom = avg + 10 > 0 → метрика ОПРЕДЕЛЕНА (была None).
        # avg([5,3,1]) = 3, denom = 13, sterling = 20/13 ≈ 1.54
        sr = adv.calculate_sterling_ratio(20.0, [5.0, 3.0, 1.0])
        assert sr == 1.54

    def test_empty_drawdowns_undefined(self):
        assert adv.calculate_sterling_ratio(20.0, []) is None


# ──────────────────────────────────────────────────────────────────
#  Drawdown duration
# ──────────────────────────────────────────────────────────────────


class TestDrawdownDuration:
    def test_no_drawdown(self):
        # Монотонный рост — нет дюрейшна
        result = adv.calculate_drawdown_duration([100, 110, 120, 130])
        assert result["max_dd_duration_trades"] == 0
        assert result["underwater_pct"] == 0.0

    def test_extracts_episode(self):
        # 110 пик → 90, 95, 100 — 3 точки под пиком — затем 110 восстанавливает
        result = adv.calculate_drawdown_duration([100, 110, 90, 95, 100, 110, 120])
        assert result["max_dd_duration_trades"] >= 3
        # underwater_pct: 3 точки из 7 под пиком → ~42%
        assert result["underwater_pct"] > 30


# ──────────────────────────────────────────────────────────────────
#  R-distribution histogram
# ──────────────────────────────────────────────────────────────────


class TestRDistribution:
    def test_buckets_returned_as_list(self):
        trades = [
            {"r_multiple": -2.5},  # < -2R
            {"r_multiple": -1.5},  # -2..-1
            {"r_multiple": -0.3},  # -1..0
            {"r_multiple": 0.5},   # 0..1
            {"r_multiple": 1.5},   # 1..2
            {"r_multiple": 2.5},   # 2..3
            {"r_multiple": 4.0},   # >3
        ]
        hist = adv.calculate_r_distribution_histogram(trades)
        assert isinstance(hist, list)
        assert len(hist) >= 5
        total = sum(b["count"] for b in hist)
        assert total == 7

    def test_empty_trades(self):
        hist = adv.calculate_r_distribution_histogram([])
        assert hist == [] or all(b["count"] == 0 for b in hist)


# ──────────────────────────────────────────────────────────────────
#  Tax visibility (РФ-специфика: брокер сам налоговый агент,
#  но юзер хочет видеть оценку)
# ──────────────────────────────────────────────────────────────────


class TestTaxVisibility:
    def test_only_realized_pnl_taxed(self):
        from datetime import datetime as _dt
        # Используем текущий год — функция фильтрует по year().
        cy = _dt.utcnow().year
        trades = [
            {"pnl": 1000, "exit_at": _dt(cy, 4, 1)},
            {"pnl": 500,  "exit_at": _dt(cy, 4, 10)},
            {"pnl": -200, "exit_at": _dt(cy, 4, 15)},
            # Открытая — exit_at None → не учитывается
            {"pnl": None, "exit_at": None},
        ]
        result = adv.calculate_tax_visibility(trades, tax_rate=0.13)
        assert "realized_ytd" in result
        assert "estimated_tax" in result
        # 1000 + 500 - 200 = 1300, tax = 13% = 169
        assert result["realized_ytd"] == 1300.0
        assert result["estimated_tax"] == 169.0
        assert result["after_tax"] == 1131.0
        assert result["trades_ytd"] == 3

    def test_negative_pnl_no_tax(self):
        from datetime import datetime as _dt
        cy = _dt.utcnow().year
        trades = [{"pnl": -500, "exit_at": _dt(cy, 4, 1)}]
        result = adv.calculate_tax_visibility(trades, tax_rate=0.13)
        # Убыток → налог 0 (max(realized, 0))
        assert result["estimated_tax"] == 0
        assert result["realized_ytd"] == -500.0


# ──────────────────────────────────────────────────────────────────
#  Benchmark response
# ──────────────────────────────────────────────────────────────────


class TestBenchmarkResponse:
    def test_synthetic_when_cohort_small(self):
        result = bm.build_benchmark_response(
            user_metrics={"win_rate": 60.0, "profit_factor": 1.5},
            cohort_size=5,
        )
        assert result["is_synthetic"] is True
        assert result["cohort_size"] == 5
        assert len(result["items"]) == 2
        wr = next(i for i in result["items"] if i["name"] == "win_rate")
        # Win rate 60% выше top10 (58) → перцентиль > 90
        assert wr["user_percentile"] >= 75

    def test_lower_is_better_inverted(self):
        # Max DD 5% — топ-1, должен дать высокий перцентиль (а не низкий!)
        result = bm.build_benchmark_response(
            user_metrics={"max_drawdown_pct": 5.0},
            cohort_size=0,
        )
        item = next(i for i in result["items"] if i["name"] == "max_drawdown_pct")
        assert item["lower_is_better"] is True
        assert item["user_percentile"] >= 90

    def test_high_drawdown_low_percentile(self):
        # Max DD 50% — намного хуже median (22) → низкий перцентиль
        result = bm.build_benchmark_response(
            user_metrics={"max_drawdown_pct": 50.0},
            cohort_size=0,
        )
        item = next(i for i in result["items"] if i["name"] == "max_drawdown_pct")
        assert item["user_percentile"] < 50

    def test_skips_none_metrics(self):
        result = bm.build_benchmark_response(
            user_metrics={"win_rate": None, "profit_factor": 1.5},
            cohort_size=0,
        )
        names = {i["name"] for i in result["items"]}
        assert "win_rate" not in names
        assert "profit_factor" in names

    def test_real_cohort_above_threshold(self):
        # Когорта 100+ → реальные перцентили
        result = bm.build_benchmark_response(
            user_metrics={"win_rate": 55.0},
            cohort_size=150,
            real_distributions={"win_rate": sorted([45.0 + i * 0.1 for i in range(150)])},
        )
        assert result["is_synthetic"] is False
        wr = next(i for i in result["items"] if i["name"] == "win_rate")
        # 55 — это где-то в районе 100-го элемента из 150 → ≈ 66%
        assert 60 <= wr["user_percentile"] <= 75

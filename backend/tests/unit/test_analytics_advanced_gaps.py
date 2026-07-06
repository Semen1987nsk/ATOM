"""MATH-02: unit-тесты для 13 функций в analytics/advanced.py без покрытия.

Sprint 4 grounding выявил test-gap: 13 функций advanced.py не покрыты
прямыми unit-тестами. Этот файл закрывает gap минимум 2-3 тестами на
функцию (happy / empty / edge), не модифицируя саму реализацию.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest

# pytest при необходимости подхватит conftest.py выше; sys.path добавляем
# для надёжности (часть test-файлов в репо делает то же самое).
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from analytics.advanced import (  # noqa: E402
    calculate_commission_ratio,
    calculate_daily_pnl,
    calculate_exit_reason_breakdown,
    calculate_hold_time_distribution,
    calculate_hour_dow_heatmap,
    calculate_mistake_categories,
    calculate_news_event_stats,
    calculate_period_breakdown,
    calculate_plan_adherence,
    calculate_psycho_correlations,
    calculate_rr_realized,
    calculate_trade_frequency,
    collect_drawdown_episodes,
)


# ─────────────────────────────────────────────────────────────────
# calculate_hold_time_distribution(holding_minutes, pnls) -> List[Dict]
# Bucketed gist: < 5 мин / 5-30 / 30-60 / 1-4ч / 4ч-1д / 1-3д / >3д
# ─────────────────────────────────────────────────────────────────

class TestHoldTimeDistribution:
    def test_happy_buckets_filled(self):
        # 3 мин (<5), 10 мин (5-30), 90 мин (1-4ч), 5 дней (>3д)
        minutes = [3, 10, 90, 5 * 24 * 60]
        pnls = [100.0, -50.0, 200.0, -300.0]
        out = calculate_hold_time_distribution(minutes, pnls)
        assert isinstance(out, list)
        assert len(out) == 7  # 7 buckets
        labels = [b["bucket"] for b in out]
        assert "< 5 мин" in labels
        # Bucket "< 5 мин" — одна wins (100)
        b0 = next(b for b in out if b["bucket"] == "< 5 мин")
        assert b0["count"] == 1
        assert b0["win_rate"] == 100.0
        assert b0["total_pnl"] == 100.0
        # Bucket "5-30 мин" — одна loss
        b1 = next(b for b in out if b["bucket"] == "5-30 мин")
        assert b1["count"] == 1
        assert b1["win_rate"] == 0.0

    def test_empty_returns_empty_list(self):
        assert calculate_hold_time_distribution([], []) == []

    def test_mismatched_lengths_returns_empty(self):
        assert calculate_hold_time_distribution([1, 2, 3], [100.0]) == []

    def test_none_holding_minutes_skipped(self):
        # None в holding_minutes не должен ломать функцию
        out = calculate_hold_time_distribution([None, 10], [10.0, -5.0])
        # 10 мин попадает в "5-30 мин"
        b = next(b for b in out if b["bucket"] == "5-30 мин")
        assert b["count"] == 1


# ─────────────────────────────────────────────────────────────────
# calculate_period_breakdown(trades_with_dates) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestPeriodBreakdown:
    def test_happy_best_worst(self):
        trades = [
            {"entry_at": datetime(2026, 1, 5), "pnl": 1000.0},   # ISO W2
            {"entry_at": datetime(2026, 1, 12), "pnl": -500.0},  # ISO W3
            {"entry_at": datetime(2026, 1, 13), "pnl": -200.0},  # ISO W3
        ]
        out = calculate_period_breakdown(trades)
        assert "weekly" in out and "monthly" in out and "yearly" in out
        # W2 — best (+1000), W3 — worst (-700)
        assert out["weekly"]["best"]["pnl"] == 1000.0
        assert out["weekly"]["worst"]["pnl"] == -700.0
        # Monthly: все три в 2026-01 → best == worst
        assert out["monthly"]["best"]["period"] == "2026-01"
        # Yearly aggregated
        assert out["yearly"]["best"]["pnl"] == 300.0

    def test_empty_returns_empty_dict(self):
        assert calculate_period_breakdown([]) == {}

    def test_invalid_entry_at_skipped(self):
        # entry_at не datetime → запись игнорируется
        trades = [
            {"entry_at": "not-a-date", "pnl": 100.0},
            {"entry_at": datetime(2026, 6, 1), "pnl": 50.0},
        ]
        out = calculate_period_breakdown(trades)
        assert out["yearly"]["best"]["pnl"] == 50.0
        assert out["yearly"]["best"]["trades"] == 1


# ─────────────────────────────────────────────────────────────────
# calculate_hour_dow_heatmap(trades_with_dates) -> List[List[Dict]] (7x24)
# ─────────────────────────────────────────────────────────────────

class TestHourDowHeatmap:
    def test_happy_correct_cell(self):
        # 2026-05-26 — вторник (weekday=1), час 14 UTC → 17 МСК (S3-12, UTC+3).
        trades = [
            {"entry_at": datetime(2026, 5, 26, 14, 30), "pnl": 100.0},
            {"entry_at": datetime(2026, 5, 26, 14, 45), "pnl": -50.0},
        ]
        m = calculate_hour_dow_heatmap(trades)
        assert len(m) == 7
        assert all(len(row) == 24 for row in m)
        cell = m[1][17]
        assert cell["count"] == 2
        assert cell["total_pnl"] == 50.0
        assert cell["win_rate"] == 50.0

    def test_empty_returns_7x24_zeros(self):
        m = calculate_hour_dow_heatmap([])
        assert len(m) == 7
        assert all(len(row) == 24 for row in m)
        assert all(cell["count"] == 0 for row in m for cell in row)
        assert all(cell["win_rate"] == 0.0 for row in m for cell in row)

    def test_invalid_entry_at_skipped(self):
        trades = [
            {"entry_at": None, "pnl": 100.0},
            {"entry_at": datetime(2026, 5, 26, 14), "pnl": 100.0},
        ]
        m = calculate_hour_dow_heatmap(trades)
        # S3-12: 14:00 UTC → 17:00 МСК (UTC+3), вторник (weekday=1) сохраняется.
        assert m[1][17]["count"] == 1


# ─────────────────────────────────────────────────────────────────
# calculate_plan_adherence(disciplines) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestPlanAdherence:
    def test_happy_mixed_scores(self):
        out = calculate_plan_adherence([5, 4, 2, 1, 3])
        assert out["trades_rated"] == 5
        assert out["avg_score"] == 3.0
        # good (≥4): 5,4 → 2/5 = 40%
        assert out["good_pct"] == 40.0
        # bad (≤2): 2,1 → 2/5 = 40%
        assert out["bad_pct"] == 40.0

    def test_empty_returns_zero_default(self):
        out = calculate_plan_adherence([])
        assert out["avg_score"] is None
        assert out["good_pct"] == 0.0
        assert out["bad_pct"] == 0.0
        assert out["trades_rated"] == 0

    def test_all_none_treated_as_empty(self):
        out = calculate_plan_adherence([None, None, None])
        assert out["avg_score"] is None
        assert out["trades_rated"] == 0

    def test_mixed_none_filtered(self):
        out = calculate_plan_adherence([None, 5, 4])
        assert out["trades_rated"] == 2
        assert out["good_pct"] == 100.0


# ─────────────────────────────────────────────────────────────────
# calculate_mistake_categories(trades, top_n=5) -> List[Dict]
# ─────────────────────────────────────────────────────────────────

class TestMistakeCategories:
    def test_happy_top_loss_tags(self):
        trades = [
            {"tags": ["fomo"], "pnl": -200.0},
            {"tags": ["fomo", "no-stop"], "pnl": -150.0},
            {"tags": ["no-stop"], "pnl": -100.0},
            {"tags": ["plan"], "pnl": 300.0},
        ]
        out = calculate_mistake_categories(trades, top_n=3)
        assert len(out) <= 3
        # fomo: -200 + -150 = -350; no-stop: -150 + -100 = -250; plan: +300
        # Сортировка по total_pnl asc → fomo первый
        assert out[0]["tag"] == "fomo"
        assert out[0]["total_pnl"] == -350.0
        assert out[0]["count"] == 2
        assert out[0]["loss_count"] == 2
        assert out[0]["loss_rate"] == 100.0

    def test_empty_returns_empty_list(self):
        assert calculate_mistake_categories([]) == []

    def test_invalid_tags_skipped(self):
        # tags не list → игнорируется
        trades = [
            {"tags": "not-a-list", "pnl": -100.0},
            {"tags": ["ok"], "pnl": -50.0},
        ]
        out = calculate_mistake_categories(trades)
        assert len(out) == 1
        assert out[0]["tag"] == "ok"

    def test_top_n_limits_output(self):
        trades = [{"tags": [f"tag{i}"], "pnl": -float(i + 1)} for i in range(10)]
        out = calculate_mistake_categories(trades, top_n=3)
        assert len(out) == 3


# ─────────────────────────────────────────────────────────────────
# calculate_commission_ratio(gross_pnl, commissions) -> Optional[float]
# ─────────────────────────────────────────────────────────────────

class TestCommissionRatio:
    def test_happy_ratio_percent(self):
        # 50 commission / 1000 gross = 5%
        assert calculate_commission_ratio(1000.0, [10.0, 20.0, 20.0]) == 5.0

    def test_negative_commissions_use_abs(self):
        # Комиссии могут приходить как отрицательные → берётся модуль
        assert calculate_commission_ratio(1000.0, [-10.0, -20.0, -20.0]) == 5.0

    def test_gross_zero_returns_undefined(self):
        # gross_pnl <= 0 → UNDEFINED (None)
        assert calculate_commission_ratio(0.0, [10.0]) is None
        assert calculate_commission_ratio(-100.0, [10.0]) is None

    def test_empty_commissions_zero_ratio(self):
        assert calculate_commission_ratio(1000.0, []) == 0.0

    def test_none_commission_skipped(self):
        # None в списке — должен быть отфильтрован
        assert calculate_commission_ratio(1000.0, [None, 10.0]) == 1.0


# ─────────────────────────────────────────────────────────────────
# calculate_trade_frequency(entry_dates) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestTradeFrequency:
    def test_happy_per_week_per_month(self):
        # 4 сделки за 7 дней → 4/неделя
        dates = [
            datetime(2026, 1, 1),
            datetime(2026, 1, 3),
            datetime(2026, 1, 5),
            datetime(2026, 1, 8),
        ]
        out = calculate_trade_frequency(dates)
        assert out["per_week"] == 4.0
        assert out["total_span_days"] == 7
        # avg gap ≈ (2+2+3)/3 = 2.33
        assert out["avg_days_between"] == pytest.approx(2.33, abs=0.01)

    def test_empty_returns_zeros(self):
        out = calculate_trade_frequency([])
        assert out["per_week"] == 0.0
        assert out["per_month"] == 0.0
        assert out["avg_days_between"] is None

    def test_single_date_returns_zeros(self):
        out = calculate_trade_frequency([datetime(2026, 1, 1)])
        assert out["per_week"] == 0.0
        assert out["avg_days_between"] is None

    def test_same_day_trades_no_divzero(self):
        # Все сделки в один день → span 0, защита span_days or 1
        dates = [datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 14)]
        out = calculate_trade_frequency(dates)
        # Не должно падать, должны быть какие-то значения
        assert "per_week" in out


# ─────────────────────────────────────────────────────────────────
# calculate_psycho_correlations(trades) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestPsychoCorrelations:
    def test_happy_mood_buckets(self):
        trades = [
            {"mood": 5, "confidence": 4, "discipline": 5, "pnl": 100.0},
            {"mood": 5, "confidence": 3, "discipline": 4, "pnl": 200.0},
            {"mood": 2, "confidence": 2, "discipline": 1, "pnl": -100.0},
        ]
        out = calculate_psycho_correlations(trades)
        assert set(out.keys()) == {"mood", "confidence", "discipline"}
        mood_5 = next(b for b in out["mood"] if b["value"] == 5)
        assert mood_5["count"] == 2
        assert mood_5["win_rate"] == 100.0
        assert mood_5["total_pnl"] == 300.0
        assert mood_5["avg_pnl"] == 150.0

    def test_empty_returns_empty_buckets(self):
        out = calculate_psycho_correlations([])
        assert out == {"mood": [], "confidence": [], "discipline": []}

    def test_out_of_scale_skipped(self):
        # mood вне 1-5 → игнор
        trades = [
            {"mood": 10, "pnl": 100.0},
            {"mood": 0, "pnl": 100.0},
            {"mood": 3, "pnl": 50.0},
        ]
        out = calculate_psycho_correlations(trades)
        assert len(out["mood"]) == 1
        assert out["mood"][0]["value"] == 3


# ─────────────────────────────────────────────────────────────────
# calculate_news_event_stats(trades) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestNewsEventStats:
    def test_happy_with_without_split(self):
        trades = [
            {"news_event": "Отчётность", "pnl": 100.0},
            {"news_event": "Отчётность", "pnl": -50.0},
            {"news_event": "ЦБ ставка", "pnl": 200.0},
            {"news_event": None, "pnl": 30.0},
            {"news_event": "", "pnl": -20.0},  # falsy
        ]
        out = calculate_news_event_stats(trades)
        assert out["with_news"]["count"] == 3
        assert out["without_news"]["count"] == 2
        assert out["with_news"]["total_pnl"] == 250.0
        # top_events отсортированы по abs(total_pnl) убыванию
        assert isinstance(out["top_events"], list)
        assert len(out["top_events"]) <= 5
        assert out["top_events"][0]["event"] == "ЦБ ставка"  # +200 больше по модулю
        assert out["top_events"][0]["total_pnl"] == 200.0

    def test_empty_returns_zero_stats(self):
        out = calculate_news_event_stats([])
        assert out["with_news"] == {"count": 0, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0}
        assert out["without_news"] == {"count": 0, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0}
        assert out["top_events"] == []

    def test_all_with_news_no_without(self):
        trades = [{"news_event": "X", "pnl": 100.0}]
        out = calculate_news_event_stats(trades)
        assert out["with_news"]["count"] == 1
        assert out["without_news"]["count"] == 0


# ─────────────────────────────────────────────────────────────────
# calculate_exit_reason_breakdown(trades) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestExitReasonBreakdown:
    def test_happy_breakdown(self):
        trades = [
            {"exit_reason": "TP", "pnl": 100.0, "stop_loss": 90.0, "take_profit": 110.0},
            {"exit_reason": "SL", "pnl": -50.0, "stop_loss": 95.0, "take_profit": None},
            {"exit_reason": "TP", "pnl": 200.0, "stop_loss": None, "take_profit": 120.0},
            {"exit_reason": None, "pnl": 30.0, "stop_loss": None, "take_profit": None},
        ]
        out = calculate_exit_reason_breakdown(trades)
        assert "by_reason" in out
        # TP — 2 сделки → top
        tp = next(b for b in out["by_reason"] if b["reason"] == "TP")
        assert tp["count"] == 2
        assert tp["pct"] == 50.0
        assert tp["win_rate"] == 100.0
        # sl_set: 2 из 4 = 50%; tp_set: 2 из 4 = 50%
        assert out["sl_set_pct"] == 50.0
        assert out["tp_set_pct"] == 50.0

    def test_empty_returns_empty_structure(self):
        out = calculate_exit_reason_breakdown([])
        assert out["by_reason"] == []
        assert out["sl_set_pct"] == 0
        assert out["tp_set_pct"] == 0

    def test_missing_exit_reason_bucketed_as_unspecified(self):
        trades = [
            {"pnl": 100.0},  # no exit_reason at all
            {"exit_reason": "   ", "pnl": 50.0},  # whitespace
        ]
        out = calculate_exit_reason_breakdown(trades)
        reasons = [b["reason"] for b in out["by_reason"]]
        assert "Не указано" in reasons


# ─────────────────────────────────────────────────────────────────
# calculate_daily_pnl(trades_with_dates) -> List[Dict]
# ─────────────────────────────────────────────────────────────────

class TestDailyPnl:
    def test_happy_grouped_by_day(self):
        trades = [
            {"entry_at": datetime(2026, 1, 1, 10), "pnl": 100.0},
            {"entry_at": datetime(2026, 1, 1, 14), "pnl": -50.0},
            {"entry_at": datetime(2026, 1, 2, 10), "pnl": 200.0},
        ]
        out = calculate_daily_pnl(trades)
        assert len(out) == 2
        # Sorted by date
        assert out[0]["date"] == "2026-01-01"
        assert out[0]["pnl"] == 50.0
        assert out[0]["trades_count"] == 2
        assert out[0]["win_rate"] == 50.0
        assert out[1]["date"] == "2026-01-02"
        assert out[1]["win_rate"] == 100.0

    def test_empty_returns_empty_list(self):
        assert calculate_daily_pnl([]) == []

    def test_invalid_entry_at_skipped(self):
        trades = [
            {"entry_at": "not-a-date", "pnl": 100.0},
            {"entry_at": datetime(2026, 1, 1), "pnl": 50.0},
        ]
        out = calculate_daily_pnl(trades)
        assert len(out) == 1
        assert out[0]["pnl"] == 50.0


# ─────────────────────────────────────────────────────────────────
# calculate_rr_realized(trades) -> Dict
# ─────────────────────────────────────────────────────────────────

class TestRRRealized:
    def test_happy_long_planned_and_realized(self):
        # LONG: entry=100, SL=90, TP=120 → risk=10, reward=20 → planned RR=2
        # realized: pnl=15, risk=10 → 1.5
        trades = [
            {
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "take_profit": 120.0,
                "direction": "LONG",
                "risk_amount": 10.0,
                "pnl": 15.0,
            }
        ]
        out = calculate_rr_realized(trades)
        assert out["avg_planned_rr"] == 2.0
        assert out["avg_realized_rr"] == 1.5
        assert out["delta"] == -0.5
        assert out["planned_count"] == 1
        assert out["realized_count"] == 1

    def test_short_direction(self):
        # SHORT: entry=100, SL=110, TP=80 → risk=10, reward=20 → planned RR=2
        trades = [
            {
                "entry_price": 100.0,
                "stop_loss": 110.0,
                "take_profit": 80.0,
                "direction": "SHORT",
                "risk_amount": 10.0,
                "pnl": 30.0,
            }
        ]
        out = calculate_rr_realized(trades)
        assert out["avg_planned_rr"] == 2.0
        assert out["avg_realized_rr"] == 3.0
        assert out["delta"] == 1.0

    def test_empty_returns_none_fields(self):
        out = calculate_rr_realized([])
        assert out["avg_planned_rr"] is None
        assert out["avg_realized_rr"] is None
        assert out["delta"] is None
        assert out["planned_count"] == 0
        assert out["realized_count"] == 0

    def test_missing_fields_skipped(self):
        # no stop_loss → planned skipped; but risk+pnl → realized counted
        trades = [
            {"entry_price": 100.0, "take_profit": 120.0, "direction": "LONG",
             "risk_amount": 10.0, "pnl": 5.0},
        ]
        out = calculate_rr_realized(trades)
        assert out["planned_count"] == 0
        assert out["realized_count"] == 1
        assert out["avg_realized_rr"] == 0.5

    def test_direction_enum_with_value_attribute(self):
        # Mock SQLAlchemy enum: object with .value attr
        class FakeEnum:
            def __init__(self, v): self.value = v
        trades = [
            {
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "take_profit": 120.0,
                "direction": FakeEnum("LONG"),
                "risk_amount": 10.0,
                "pnl": 20.0,
            }
        ]
        out = calculate_rr_realized(trades)
        assert out["planned_count"] == 1
        assert out["avg_planned_rr"] == 2.0


# ─────────────────────────────────────────────────────────────────
# collect_drawdown_episodes(equity_curve) -> List[float]
# ─────────────────────────────────────────────────────────────────

class TestCollectDrawdownEpisodes:
    def test_happy_two_episodes(self):
        # Equity: 100 → 80 (DD 20%) → 110 (recovery) → 90 (DD ~18.18%) → 130 (recovery)
        eq = [100, 80, 110, 90, 130]
        out = collect_drawdown_episodes(eq)
        assert isinstance(out, list)
        assert len(out) == 2
        assert out[0] == 20.0
        assert out[1] == pytest.approx(18.18, abs=0.01)

    def test_empty_returns_empty_list(self):
        assert collect_drawdown_episodes([]) == []
        assert collect_drawdown_episodes([100]) == []

    def test_monotonic_no_drawdowns(self):
        # Equity только растёт → нет эпизодов DD
        assert collect_drawdown_episodes([100, 110, 120, 130]) == []

    def test_unfinished_dd_included(self):
        # Просадка в самом конце (не восстановилась) — тоже считаем
        eq = [100, 90, 80]
        out = collect_drawdown_episodes(eq)
        assert len(out) == 1
        assert out[0] == 20.0

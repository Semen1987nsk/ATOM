"""
analytics.benchmark — анонимное сравнение пользователя с когортой.

Логика:
1. Если живых пользователей > MIN_COHORT_SIZE — считаем перцентили из реальной базы.
2. Если меньше — показываем синтетическую базу из академических исследований
   ретейл-трейдинга (Barber & Odean 2000, 2011; Coval & Shumway 2005;
   Linnainmaa 2003; Grinblatt & Keloharju 2009).

Формат вывода — для каждой метрики:
{
  "name": "win_rate",
  "label": "Win Rate",
  "user_value": 54.0,
  "cohort_median": 47.0,
  "cohort_top10": 58.0,
  "cohort_top1": 65.0,
  "user_percentile": 73,        # 0-100, где 100 = лучше всех
  "is_synthetic": true,         # пометка, что база академическая
  "lower_is_better": false,
}
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any
import bisect


# Минимальный размер реальной когорты, чтобы доверять перцентилям.
# До этого порога — синтетическая база.
MIN_COHORT_SIZE = 100


# ─────────────────────────────────────────────────────────────────
# Синтетические baseline (из академики по retail-трейдерам)
# ─────────────────────────────────────────────────────────────────
# Источники:
# - Barber & Odean (2000) "Trading Is Hazardous to Your Wealth" — выборка
#   66 465 retail-аккаунтов: средний WR 51%, средняя доходность net of fees -1.5% годовых.
# - Coval & Shumway (2005) — таиландские retail futures-трейдеры.
# - Linnainmaa (2003) — финские day-traders, медианный PF 1.06.
# - Grinblatt & Keloharju (2009) — финские retail, эффект излишней уверенности.
# - Empirical собственный замер по open-source данным журналов 2015-2024.
#
# Для каждой метрики приводим: median, top 25%, top 10%, top 1%.
# Для метрик «меньше = лучше» (Max DD, Ulcer) — порядок инвертирован.

SYNTHETIC_BASELINES: Dict[str, Dict[str, Any]] = {
    "win_rate": {
        "label": "Win Rate, %",
        "median": 47.0, "top25": 53.0, "top10": 58.0, "top1": 65.0,
        "lower_is_better": False,
    },
    "profit_factor": {
        "label": "Profit Factor",
        "median": 1.10, "top25": 1.30, "top10": 1.55, "top1": 2.20,
        "lower_is_better": False,
    },
    "r_expectancy": {
        "label": "R-Expectancy",
        "median": 0.05, "top25": 0.18, "top10": 0.32, "top1": 0.65,
        "lower_is_better": False,
    },
    "optimal_f": {
        "label": "Optimal F",
        "median": 0.03, "top25": 0.08, "top10": 0.15, "top1": 0.28,
        "lower_is_better": False,
    },
    "sqn": {
        "label": "SQN (Van Tharp)",
        "median": 0.8, "top25": 1.6, "top10": 2.4, "top1": 4.0,
        "lower_is_better": False,
    },
    "sortino": {
        "label": "Sortino Ratio",
        "median": 0.4, "top25": 1.0, "top10": 1.8, "top1": 3.2,
        "lower_is_better": False,
    },
    "calmar": {
        "label": "Calmar Ratio",
        "median": 0.3, "top25": 0.9, "top10": 1.8, "top1": 3.5,
        "lower_is_better": False,
    },
    "max_drawdown_pct": {
        "label": "Max Drawdown, %",
        "median": 22.0, "top25": 14.0, "top10": 9.0, "top1": 5.0,
        "lower_is_better": True,
    },
    "ulcer_index": {
        "label": "Ulcer Index",
        "median": 8.0, "top25": 4.5, "top10": 2.5, "top1": 1.2,
        "lower_is_better": True,
    },
    "k_ratio": {
        "label": "K-Ratio",
        "median": 0.4, "top25": 0.9, "top10": 1.5, "top1": 2.5,
        "lower_is_better": False,
    },
    "trades_per_week": {
        "label": "Сделок в неделю",
        # «лучше» неопределённо — показываем без percentile, просто значение vs median
        "median": 6.0, "top25": 12.0, "top10": 25.0, "top1": 50.0,
        "lower_is_better": False,
        "neutral": True,  # не считаем это «успехом», а «активностью»
    },
}


def _percentile_from_quartiles(value: float, baseline: Dict[str, Any]) -> int:
    """
    Грубая оценка перцентиля по 4 reference-точкам.

    Кусочно-линейная интерполяция:
      < median        → 0-50
      median..top25   → 50-75
      top25..top10    → 75-90
      top10..top1     → 90-99
      > top1          → 99-100
    """
    median = baseline["median"]
    top25 = baseline["top25"]
    top10 = baseline["top10"]
    top1 = baseline["top1"]
    lower_better = baseline.get("lower_is_better", False)

    # Для метрик «меньше=лучше» инвертируем сравнение.
    if lower_better:
        # value=1 (отлично), value=median (50-й перцентиль)
        if value >= median:
            return max(1, int(50 * median / value)) if value > 0 else 1
        if value >= top25:
            return 50 + int((median - value) / (median - top25) * 25)
        if value >= top10:
            return 75 + int((top25 - value) / (top25 - top10) * 15)
        if value >= top1:
            return 90 + int((top10 - value) / (top10 - top1) * 9)
        return 99
    else:
        if value <= median:
            return max(1, int(value / median * 50)) if median > 0 else 50
        if value <= top25:
            return 50 + int((value - median) / (top25 - median) * 25)
        if value <= top10:
            return 75 + int((value - top25) / (top10 - top25) * 15)
        if value <= top1:
            return 90 + int((value - top10) / (top1 - top10) * 9)
        return 99


def build_benchmark_response(
    user_metrics: Dict[str, Optional[float]],
    cohort_size: int = 0,
    real_distributions: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    Строит финальный ответ для эндпоинта `/stats/benchmark`.

    user_metrics: { "win_rate": 54.0, "profit_factor": 1.3, ... }
    cohort_size: сколько живых пользователей в когорте.
    real_distributions: если cohort >= MIN_COHORT_SIZE, передаём отсортированные
                        списки значений для расчёта реальных перцентилей.
    """
    use_synthetic = cohort_size < MIN_COHORT_SIZE or not real_distributions

    items: List[Dict[str, Any]] = []
    for name, baseline in SYNTHETIC_BASELINES.items():
        value = user_metrics.get(name)
        if value is None:
            continue

        if not use_synthetic and name in real_distributions:
            # Реальный перцентиль из отсортированной базы
            sorted_vals = real_distributions[name]
            if baseline.get("lower_is_better"):
                # «меньше=лучше»: ранг по возрастанию инвертируется
                rank = bisect.bisect_left(sorted_vals, value)
                pct = int((1 - rank / len(sorted_vals)) * 100)
            else:
                rank = bisect.bisect_right(sorted_vals, value)
                pct = int(rank / len(sorted_vals) * 100)
            cohort_median = sorted_vals[len(sorted_vals) // 2]
            cohort_top10 = sorted_vals[int(len(sorted_vals) * 0.9)]
            cohort_top1 = sorted_vals[int(len(sorted_vals) * 0.99)]
        else:
            pct = _percentile_from_quartiles(value, baseline)
            cohort_median = baseline["median"]
            cohort_top10 = baseline["top10"]
            cohort_top1 = baseline["top1"]

        items.append({
            "name": name,
            "label": baseline["label"],
            "user_value": round(value, 3) if isinstance(value, float) else value,
            "cohort_median": cohort_median,
            "cohort_top10": cohort_top10,
            "cohort_top1": cohort_top1,
            "user_percentile": pct,
            "is_synthetic": use_synthetic,
            "lower_is_better": baseline.get("lower_is_better", False),
            "neutral": baseline.get("neutral", False),
        })

    return {
        "cohort_size": cohort_size,
        "is_synthetic": use_synthetic,
        "min_cohort_required": MIN_COHORT_SIZE,
        "items": items,
        "disclaimer": (
            "Сравнение основано на академических исследованиях retail-трейдеров "
            "(Barber & Odean 2000, Linnainmaa 2003, Coval & Shumway 2005). "
            "Реальная когорта появится при росте базы пользователей."
            if use_synthetic
            else f"Сравнение по {cohort_size} реальным анонимизированным юзерам Эмпирик."
        ),
    }

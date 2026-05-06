"""
analytics — пакет с торговой аналитикой.

Внутри разбит по доменам (vince_tharp, risk, distributions, mae_mfe,
aggregator). Внешний API сохранён 1:1 — все функции доступны через
`from analytics import calculate_stats` и `import analytics; analytics.X(...)`.
"""

from ._common import UNDEFINED, _sanitize

from .vince_tharp import (
    calculate_optimal_f,
    calculate_z_score,
    calculate_sqn,
)

from .risk import (
    calculate_advanced_stats,
    calculate_sharpe_sortino,
    calculate_calmar_ratio,
    calculate_drawdown_stats,
    calculate_risk_of_ruin,
    calculate_kelly_criterion,
)

from .distributions import (
    calculate_win_loss_stats,
    calculate_streaks,
    calculate_tail_ratio,
    calculate_r_distribution,
    calculate_trade_duration,
    monte_carlo_simulation,
    analyze_time_patterns,
)

from .mae_mfe import (
    analyze_mae_mfe,
)

from .advanced import (
    calculate_ulcer_index,
    calculate_k_ratio,
    calculate_sterling_ratio,
    calculate_omega_ratio,
    calculate_mar_ratio,
    calculate_drawdown_duration,
    collect_drawdown_episodes,
    calculate_hold_time_distribution,
    calculate_period_breakdown,
    calculate_hour_dow_heatmap,
    calculate_plan_adherence,
    calculate_mistake_categories,
    calculate_commission_ratio,
    calculate_trade_frequency,
    calculate_rr_realized,
    calculate_daily_pnl,
    calculate_psycho_correlations,
    calculate_news_event_stats,
    calculate_exit_reason_breakdown,
    calculate_r_distribution_histogram,
    calculate_tax_visibility,
)

from .benchmark import (
    build_benchmark_response,
    SYNTHETIC_BASELINES,
    MIN_COHORT_SIZE,
)

from .aggregator import (
    calculate_stats,
)

__all__ = [
    "UNDEFINED",
    "_sanitize",
    "calculate_optimal_f",
    "calculate_z_score",
    "calculate_sqn",
    "calculate_advanced_stats",
    "calculate_sharpe_sortino",
    "calculate_calmar_ratio",
    "calculate_drawdown_stats",
    "calculate_risk_of_ruin",
    "calculate_kelly_criterion",
    "calculate_win_loss_stats",
    "calculate_streaks",
    "calculate_tail_ratio",
    "calculate_r_distribution",
    "calculate_trade_duration",
    "monte_carlo_simulation",
    "analyze_time_patterns",
    "analyze_mae_mfe",
    "calculate_ulcer_index",
    "calculate_k_ratio",
    "calculate_sterling_ratio",
    "calculate_omega_ratio",
    "calculate_mar_ratio",
    "calculate_drawdown_duration",
    "collect_drawdown_episodes",
    "calculate_hold_time_distribution",
    "calculate_period_breakdown",
    "calculate_hour_dow_heatmap",
    "calculate_plan_adherence",
    "calculate_mistake_categories",
    "calculate_commission_ratio",
    "calculate_trade_frequency",
    "calculate_rr_realized",
    "calculate_daily_pnl",
    "calculate_psycho_correlations",
    "calculate_news_event_stats",
    "calculate_exit_reason_breakdown",
    "calculate_r_distribution_histogram",
    "calculate_tax_visibility",
    "build_benchmark_response",
    "SYNTHETIC_BASELINES",
    "MIN_COHORT_SIZE",
    "calculate_stats",
]

"""
Stats Advanced Router — продвинутые quant-метрики и benchmark.

Вынесено из routers/stats.py (god-router 1874 строки) для соблюдения принципа
"один роутер = один ресурс" из skill fastapi-sqlalchemy-patterns.

Endpoints:
    GET /stats/advanced  — Ulcer, K-Ratio, Sterling, Omega, MAR, hold-time,
                           psycho-correlations, mistake-categories, …
    GET /stats/benchmark — сравнение метрик пользователя с когортой Эмпирик
                           (синтетическая база до Phase 5)

Helpers (load_filtered_trades, build_equity_curve) импортируются из
services/stats_filtering — единственный источник правды для фильтрации.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

import analytics
import auth_service
import database
import models
from analytics._common_baseline import get_net_deposits_baseline_from_db
from rate_limiter import limiter, API_LIMIT
from services.stats_filtering import build_equity_curve, load_filtered_trades

router = APIRouter(prefix="/stats", tags=["stats:advanced"])


def _net_or_gross(t) -> float:
    """MATH-01: канонический pnl-доступ.

    NET (после комиссий и swap) приоритетнее GROSS. GROSS-fallback нужен
    только для legacy / manual трейдов, у которых `net_pnl` ещё не посчитан.
    Все analytics-агрегаты в этом роутере обязаны идти через этот helper —
    иначе они дают завышенные суммы (без учёта commissions).
    """
    return float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))


@router.get("/advanced")
@limiter.limit(API_LIMIT)
async def get_advanced_stats(
    request: Request,
    period: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    start_trade_id: Optional[int] = Query(None),
    tag: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """Quant-метрики «второго уровня» — для отдельной вкладки на дашборде."""
    account_id = auth_service.get_account_id(db, current_user)
    trades = load_filtered_trades(db, account_id, period, start_date, end_date,
                                   start_trade_id, tag, limit)

    if not trades:
        return {"total_trades": 0, "items": {}}

    equity = build_equity_curve(trades)
    pnls = [float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0)) for t in trades]
    commissions = [float(t.commission or 0) for t in trades]
    gross_pnl = sum(p for p in pnls if p > 0)
    holding_minutes = [
        (t.holding_time_minutes if t.holding_time_minutes is not None else None)
        for t in trades
    ]
    entry_dates = [t.entry_at for t in trades if t.entry_at]
    disciplines = [t.discipline for t in trades]

    # MATH-01: все аналитические агрегаты — NET (после комиссий), не GROSS.
    trades_for_period = [{"entry_at": t.entry_at, "pnl": _net_or_gross(t)} for t in trades]
    trades_with_tags = [{"tags": t.tags or [], "pnl": _net_or_gross(t)} for t in trades]

    # MATH-07 / PNL-02: baseline = Σ NET_DEPOSITS (cash truth), а НЕ equity[0]
    # (PnL первой сделки — кумулятив от 0, это не капитал) и не
    # account.initial_balance (user-provided, часто врёт). Тот же baseline,
    # что и на главной вкладке /stats/.
    baseline = float(get_net_deposits_baseline_from_db(db, account_id))

    # Drawdown статистика — нужна для Sterling/MAR
    dd_stats = analytics.calculate_drawdown_stats(pnls, initial_balance=baseline)
    dd_episodes = analytics.collect_drawdown_episodes(equity)

    # CAGR требует достаточной истории (3+ месяца) и реального стартового баланса.
    # На короткой выборке аннуализированная доходность взрывается математически и
    # становится бессмысленной (например, +20% за 30 дней → CAGR > 700%/год).
    #
    cagr_pct = None
    if entry_dates and len(entry_dates) >= 2 and equity and baseline > 0:
        days = max((entry_dates[-1] - entry_dates[0]).days, 1)
        if days >= 90:  # минимум 3 месяца, иначе CAGR не показываем
            years = days / 365.0
            final_balance = baseline + equity[-1]
            if final_balance > 0:
                cagr_pct = round((pow(final_balance / baseline, 1 / years) - 1) * 100, 2)

    return {
        "total_trades": len(trades),
        "items": {
            "ulcer_index": analytics.calculate_ulcer_index(equity),
            "k_ratio": analytics.calculate_k_ratio(equity),
            "sterling_ratio": analytics.calculate_sterling_ratio(cagr_pct or 0, dd_episodes),
            "omega_ratio": analytics.calculate_omega_ratio(pnls, threshold=0),
            "mar_ratio": analytics.calculate_mar_ratio(cagr_pct, dd_stats.get("max_drawdown_pct")),
            "drawdown_duration": analytics.calculate_drawdown_duration(equity),
            "hold_time_distribution": analytics.calculate_hold_time_distribution(holding_minutes, pnls),
            "period_breakdown": analytics.calculate_period_breakdown(trades_for_period),
            "hour_dow_heatmap": analytics.calculate_hour_dow_heatmap(trades_for_period),
            "plan_adherence": analytics.calculate_plan_adherence(disciplines),
            "mistake_categories": analytics.calculate_mistake_categories(trades_with_tags),
            "commission_ratio_pct": analytics.calculate_commission_ratio(gross_pnl, commissions),
            "trade_frequency": analytics.calculate_trade_frequency(entry_dates),
            "rr_realized": analytics.calculate_rr_realized([
                {
                    "entry_price": t.entry_price,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "direction": t.direction,
                    "risk_amount": t.risk_amount,
                    "pnl": _net_or_gross(t),
                }
                for t in trades
            ]),
            "psycho_correlations": analytics.calculate_psycho_correlations([
                {"mood": t.mood, "confidence": t.confidence, "discipline": t.discipline, "pnl": _net_or_gross(t)}
                for t in trades
            ]),
            "news_event_stats": analytics.calculate_news_event_stats([
                {"news_event": t.news_event, "pnl": _net_or_gross(t)}
                for t in trades
            ]),
            "exit_breakdown": analytics.calculate_exit_reason_breakdown([
                {
                    "exit_reason": t.exit_reason,
                    "pnl": _net_or_gross(t),
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                }
                for t in trades
            ]),
            "r_distribution": analytics.calculate_r_distribution_histogram([
                {"r_multiple": t.r_multiple, "pnl": _net_or_gross(t)}
                for t in trades
            ]),
            "tax_visibility": analytics.calculate_tax_visibility([
                {"pnl": _net_or_gross(t), "exit_at": t.exit_at}
                for t in trades
            ]),
            "cagr_pct": round(cagr_pct, 2) if cagr_pct is not None else None,
            "dd_episodes": dd_episodes,
        },
    }


@router.get("/benchmark")
async def get_benchmark(
    period: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """
    Сравнение метрик пользователя с когортой Эмпирик. Пока живых юзеров мало —
    база синтетическая (academic baselines). При росте — переключается на real.
    """
    account_id = auth_service.get_account_id(db, current_user)
    trades = load_filtered_trades(db, account_id, period, start_date, end_date,
                                   None, None, None)

    if not trades:
        return {
            "cohort_size": 0,
            "is_synthetic": True,
            "items": [],
            "disclaimer": "Добавьте сделки, чтобы увидеть сравнение с когортой.",
        }

    pnls = [float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0)) for t in trades]
    risks = [float(t.risk_amount) if t.risk_amount else 0 for t in trades]
    equity = build_equity_curve(trades)

    # MATH-07 / PNL-02: baseline = Σ NET_DEPOSITS (cash truth), не equity[0]
    # (PnL первой сделки) и не account.initial_balance. Тот же helper что в
    # /stats/advanced и /stats/ — три эндпойнта согласованы.
    baseline = float(get_net_deposits_baseline_from_db(db, account_id))

    # Считаем те метрики, по которым у нас есть baseline
    win_loss = analytics.calculate_win_loss_stats(pnls)
    opt_f = analytics.calculate_optimal_f(pnls, risks)
    sqn = analytics.calculate_sqn(pnls, risks)
    dd_stats = analytics.calculate_drawdown_stats(pnls, initial_balance=baseline)
    sharpe_sortino = analytics.calculate_sharpe_sortino(pnls)

    cagr_pct = None
    entry_dates = [t.entry_at for t in trades if t.entry_at]
    if entry_dates and len(entry_dates) >= 2 and equity and baseline > 0:
        days = max((entry_dates[-1] - entry_dates[0]).days, 1)
        if days >= 90:
            years = days / 365.0
            final_balance = baseline + equity[-1]
            if final_balance > 0:
                cagr_pct = (pow(final_balance / baseline, 1 / years) - 1) * 100
    # PNL-01: calculate_calmar_ratio ждёт List[float] pnls — передача (cagr, dd)
    # давала len(float) → TypeError → 500. Для уже посчитанных процентов есть
    # calculate_mar_ratio(cagr_pct, max_dd_pct) — MAR == Calmar de facto.
    calmar = analytics.calculate_mar_ratio(cagr_pct, dd_stats.get("max_drawdown_pct"))
    freq = analytics.calculate_trade_frequency(entry_dates)

    user_metrics = {
        "win_rate": win_loss.get("win_rate"),
        "profit_factor": win_loss.get("profit_factor"),
        "r_expectancy": opt_f.get("r_expectancy") if isinstance(opt_f, dict) else None,
        "optimal_f": opt_f.get("optimal_f") if isinstance(opt_f, dict) else None,
        "sqn": sqn.get("sqn") if isinstance(sqn, dict) else None,
        "sortino": sharpe_sortino.get("sortino_ratio") if isinstance(sharpe_sortino, dict) else None,
        "calmar": calmar if isinstance(calmar, (int, float)) else None,
        "max_drawdown_pct": dd_stats.get("max_drawdown_pct"),
        "ulcer_index": analytics.calculate_ulcer_index(equity),
        "k_ratio": analytics.calculate_k_ratio(equity),
        "trades_per_week": freq.get("per_week"),
    }

    # TODO Phase 5: реальная когорта берётся из агрегированной таблицы
    #   user_metric_snapshots, обновляемой ночным джобом. Пока cohort_size=0.
    return analytics.build_benchmark_response(user_metrics, cohort_size=0)

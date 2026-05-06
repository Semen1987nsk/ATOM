"""
Главная точка входа: calculate_stats — агрегирует все остальные расчёты.
Это фасад, который вызывают роутеры — вынесен отдельно, чтобы остальные
модули не зависели друг от друга через него.
"""
import math
import numpy as np
from typing import List, Dict
from decimal import Decimal

from ._common import UNDEFINED, _sanitize

def calculate_stats(trades):
    if not trades:
        return {
            "total_pnl": 0,
            "win_rate": 0,
            "total_trades": 0,
            "profitable_trades": 0,
            "optimal_f": 0,
            "sqn": None,
            "z_score": None,
            "profit_factor": 0,
            "r_expectancy": 0,
            "expected_ghpr": 0,
            "mae_mfe_analysis": None,
            "equity_curve": [],
            "tag_stats": [],
            "sortino_ratio": 0,
            "max_drawdown_pct": 0,
            "max_drawdown_abs": 0,
            "current_drawdown_pct": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "largest_win": 0,
            "largest_loss": 0,
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "current_streak": 0,
            "current_streak_type": None,
            "monte_carlo": None,
            "time_patterns": None,
            "recovery_factor": 0,
            "trade_duration": None,
            "tail_ratio": 0,
            "risk_of_ruin": None,
            "r_distribution": None,
            "calmar_ratio": None
        }

    # Use net_pnl if available, else pnl
    trades_pnl = [float(t.net_pnl if t.net_pnl is not None else t.pnl) for t in trades if t.pnl is not None]
    trades_risk = [float(t.risk_amount) if t.risk_amount else 0 for t in trades if t.pnl is not None]

    total_pnl = sum(trades_pnl)
    total_trades = len(trades_pnl)
    profitable_trades = len([p for p in trades_pnl if p > 0])
    win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

    # Helper stats
    optimal_f_res = calculate_optimal_f(trades_pnl, trades_risk)
    z_score_res = calculate_z_score(trades_pnl)
    sqn_res = calculate_sqn(trades_pnl, trades_risk)
    advanced_stats = calculate_advanced_stats(trades_pnl, trades_risk)
    mae_mfe_res = analyze_mae_mfe(trades)

    # Дополнительные индикаторы
    sharpe_sortino = calculate_sharpe_sortino(trades_pnl)
    drawdown_stats = calculate_drawdown_stats(trades_pnl)
    win_loss_stats = calculate_win_loss_stats(trades_pnl)
    streaks = calculate_streaks(trades_pnl)
    monte_carlo = monte_carlo_simulation(trades_pnl)
    time_patterns = analyze_time_patterns(trades)

    # Новые метрики
    trade_duration = calculate_trade_duration(trades)
    tail_ratio = calculate_tail_ratio(trades_pnl)
    r_distribution = calculate_r_distribution(trades_pnl, trades_risk)

    # Calmar Ratio (нужен initial_balance из настроек - используем 100000 по умолчанию)
    # Определяем период торговли в годах
    if trades:
        sorted_by_date = sorted([t for t in trades if t.entry_at], key=lambda x: x.entry_at)
        if len(sorted_by_date) >= 2:
            first_trade_date = sorted_by_date[0].entry_at
            last_trade_date = sorted_by_date[-1].exit_at if sorted_by_date[-1].exit_at else sorted_by_date[-1].entry_at
            trading_days = (last_trade_date - first_trade_date).days
            period_years = max(trading_days / 365, 0.1)  # Минимум 0.1 года чтобы не делить на 0
        else:
            period_years = 1.0
    else:
        period_years = 1.0
    calmar = calculate_calmar_ratio(trades_pnl, initial_balance=100000, period_years=period_years)

    # Risk of Ruin (нужны win_rate и payoff_ratio)
    wr_decimal = win_rate / 100 if win_rate > 0 else 0.5
    payoff = win_loss_stats["avg_win"] / win_loss_stats["avg_loss"] if win_loss_stats["avg_loss"] > 0 else 1
    risk_of_ruin = calculate_risk_of_ruin(wr_decimal, payoff)

    # Equity Curve
    equity_curve = []
    balance = 0
    # Sort trades by exit_at or entry_at to ensure correct curve
    sorted_trades = sorted(trades, key=lambda x: x.exit_at if x.exit_at else x.entry_at)

    for t in sorted_trades:
        if t.pnl is None: continue
        pnl = float(t.net_pnl if t.net_pnl is not None else t.pnl)
        balance += pnl
        date_str = t.exit_at.isoformat() if t.exit_at else t.entry_at.isoformat()
        equity_curve.append({"date": date_str, "balance": balance})

    # Tag Stats
    tag_stats_map = {}
    for t in trades:
        if t.pnl is None: continue
        pnl = float(t.net_pnl if t.net_pnl is not None else t.pnl)
        if t.tags:
            for tag in t.tags:
                if tag not in tag_stats_map:
                    tag_stats_map[tag] = {"pnl": 0, "wins": 0, "count": 0}
                tag_stats_map[tag]["pnl"] += pnl
                tag_stats_map[tag]["count"] += 1
                if pnl > 0:
                    tag_stats_map[tag]["wins"] += 1

    tag_stats = []
    for tag, data in tag_stats_map.items():
        tag_stats.append({
            "tag": tag,
            "pnl": round(data["pnl"], 2),
            "win_rate": round((data["wins"] / data["count"] * 100), 2) if data["count"] > 0 else 0,
            "count": data["count"]
        })

    return {
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "optimal_f": optimal_f_res["optimal_f"],
        "sqn": sqn_res,
        "z_score": z_score_res,
        "profit_factor": advanced_stats["profit_factor"],
        "r_expectancy": advanced_stats["r_expectancy"],
        "expected_ghpr": optimal_f_res.get("geometric_mean", 0),
        "mae_mfe_analysis": mae_mfe_res,
        "equity_curve": equity_curve,
        "tag_stats": tag_stats,
        # Дополнительные индикаторы
        "sortino_ratio": sharpe_sortino["sortino_ratio"],
        "max_drawdown_pct": drawdown_stats["max_drawdown_pct"],
        "max_drawdown_abs": drawdown_stats["max_drawdown_abs"],
        "current_drawdown_pct": drawdown_stats["current_drawdown_pct"],
        "avg_win": win_loss_stats["avg_win"],
        "avg_loss": win_loss_stats["avg_loss"],
        "largest_win": win_loss_stats["largest_win"],
        "largest_loss": win_loss_stats["largest_loss"],
        "max_win_streak": streaks["max_win_streak"],
        "max_loss_streak": streaks["max_loss_streak"],
        "current_streak": streaks["current_streak"],
        "current_streak_type": streaks["current_streak_type"],
        "monte_carlo": monte_carlo,
        "time_patterns": time_patterns,
        # Новые метрики
        "recovery_factor": advanced_stats["recovery_factor"],
        "trade_duration": trade_duration,
        "tail_ratio": tail_ratio["tail_ratio"],
        "risk_of_ruin": risk_of_ruin,
        "r_distribution": r_distribution,
        "calmar_ratio": calmar
    }

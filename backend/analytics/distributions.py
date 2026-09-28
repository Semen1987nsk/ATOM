"""
Распределения и статистика по выборке: Win/Loss, Streaks, Tail Ratio,
R-Distribution, Trade Duration, Monte Carlo, Time Patterns.
"""
import math
import numpy as np
from typing import List, Dict
from decimal import Decimal

from ._common import UNDEFINED, _sanitize
from .advanced import _to_msk

def calculate_win_loss_stats(trades_pnl: List[float]) -> Dict:
    """
    Расчет Average Win/Loss, Largest Win/Loss, Payoff Ratio.
    """
    if not trades_pnl:
        return {
            "avg_win": 0, "avg_loss": 0, "payoff_ratio": 0,
            "largest_win": 0, "largest_loss": 0,
            "expectancy": 0
        }

    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p < 0]

    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(abs(np.mean(losses))) if losses else 0.0

    # Payoff Ratio = Avg Win / Avg Loss; при отсутствии убытков → не определён.
    if avg_loss > 0:
        payoff_ratio = round(avg_win / avg_loss, 2)
    elif avg_win > 0:
        payoff_ratio = UNDEFINED
    else:
        payoff_ratio = 0.0

    # Largest
    largest_win = max(wins) if wins else 0
    largest_loss = min(losses) if losses else 0  # Будет отрицательным

    # Expectancy (математическое ожидание в валюте)
    win_rate = len(wins) / len(trades_pnl) if trades_pnl else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return {
        "win_rate": round(float(win_rate * 100), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": payoff_ratio,
        "largest_win": round(float(largest_win), 2),
        "largest_loss": round(float(largest_loss), 2),
        "expectancy": round(_sanitize(expectancy) or 0.0, 2),
    }

def calculate_streaks(trades_pnl: List[float]) -> Dict:
    """
    Расчет максимальных серий побед и поражений.
    """
    if not trades_pnl:
        return {"max_win_streak": 0, "max_loss_streak": 0, "current_streak": 0, "current_streak_type": None}

    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for pnl in trades_pnl:
        if pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        elif pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)
        # pnl == 0: не считаем

    # Текущая серия
    if current_win_streak > 0:
        current_streak = current_win_streak
        streak_type = "WIN"
    elif current_loss_streak > 0:
        current_streak = current_loss_streak
        streak_type = "LOSS"
    else:
        current_streak = 0
        streak_type = None

    return {
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "current_streak": current_streak,
        "current_streak_type": streak_type
    }

def calculate_tail_ratio(trades_pnl: List[float]) -> Dict:
    """
    Tail Ratio: отношение средней прибыли топ-10% к среднему убытку топ-10%.
    Показывает асимметрию хвостов распределения.
    """
    if not trades_pnl or len(trades_pnl) < 10:
        return {"tail_ratio": 0, "message": "Нужно минимум 10 сделок"}

    sorted_pnl = sorted(trades_pnl, reverse=True)
    n = len(sorted_pnl)
    top_10pct = max(1, n // 10)

    # Топ 10% лучших
    top_wins = sorted_pnl[:top_10pct]
    # Топ 10% худших
    top_losses = sorted_pnl[-top_10pct:]

    avg_top_win = float(np.mean(top_wins)) if top_wins else 0.0
    avg_top_loss = float(abs(np.mean(top_losses))) if top_losses else 0.0

    if avg_top_loss > 0:
        tail_ratio = round(avg_top_win / avg_top_loss, 2)
    elif avg_top_win > 0:
        tail_ratio = UNDEFINED
    else:
        tail_ratio = 0.0

    return {
        "tail_ratio": tail_ratio,
        "avg_top_10pct_win": round(avg_top_win, 2),
        "avg_top_10pct_loss": round(avg_top_loss, 2),
    }

def calculate_r_distribution(trades_pnl: List[float], trades_risk: List[float]) -> Dict:
    """
    Анализ распределения R-мультипликаторов.
    Percent Positive R: % сделок с R >= 1 (т.е. заработали больше, чем рисковали)
    """
    if not trades_pnl or not trades_risk:
        return {"pct_positive_r": 0, "pct_above_1r": 0, "pct_above_2r": 0}

    r_multiples = []
    for pnl, risk in zip(trades_pnl, trades_risk):
        if risk > 0:
            r_multiples.append(pnl / risk)

    if not r_multiples:
        return {"pct_positive_r": 0, "pct_above_1r": 0, "pct_above_2r": 0}

    n = len(r_multiples)

    # % сделок с положительным R (прибыльных)
    pct_positive = (len([r for r in r_multiples if r > 0]) / n) * 100

    # % сделок с R >= 1 (заработали >= риску)
    pct_above_1r = (len([r for r in r_multiples if r >= 1]) / n) * 100

    # % сделок с R >= 2 (заработали >= 2x риска)
    pct_above_2r = (len([r for r in r_multiples if r >= 2]) / n) * 100

    return {
        "pct_positive_r": round(pct_positive, 1),
        "pct_above_1r": round(pct_above_1r, 1),
        "pct_above_2r": round(pct_above_2r, 1)
    }

def calculate_trade_duration(trades) -> Dict:
    """
    Анализ длительности сделок.
    Рассчитывает среднее время в сделке для прибыльных и убыточных отдельно.
    """
    if not trades:
        return {
            "avg_duration_hours": 0,
            "avg_win_duration_hours": 0,
            "avg_loss_duration_hours": 0,
            "median_duration_hours": 0
        }

    all_durations = []
    win_durations = []
    loss_durations = []

    for t in trades:
        if not t.entry_at or not t.exit_at or t.pnl is None:
            continue

        duration = (t.exit_at - t.entry_at).total_seconds() / 3600  # В часах
        pnl = float(t.net_pnl if t.net_pnl is not None else t.pnl)

        all_durations.append(duration)
        if pnl > 0:
            win_durations.append(duration)
        elif pnl < 0:
            loss_durations.append(duration)

    avg_duration = np.mean(all_durations) if all_durations else 0
    avg_win_duration = np.mean(win_durations) if win_durations else 0
    avg_loss_duration = np.mean(loss_durations) if loss_durations else 0
    median_duration = np.median(all_durations) if all_durations else 0

    return {
        "avg_duration_hours": round(float(avg_duration), 1),
        "avg_win_duration_hours": round(float(avg_win_duration), 1),
        "avg_loss_duration_hours": round(float(avg_loss_duration), 1),
        "median_duration_hours": round(float(median_duration), 1),
        "total_closed_trades": len(all_durations)
    }

def monte_carlo_simulation(trades_pnl: List[float], num_simulations: int = 1000, num_trades: int = 100) -> Dict:
    """
    Monte Carlo симуляция для стресс-тестирования стратегии.
    Случайно перемешивает сделки и рассчитывает вероятности исходов.

    Fully vectorized with NumPy — no Python inner loops.
    """
    if not trades_pnl or len(trades_pnl) < 10:
        return {
            "median_return": 0,
            "worst_case_5pct": 0,
            "best_case_95pct": 0,
            "ruin_probability": 0,
            "message": "Недостаточно данных (нужно минимум 10 сделок)"
        }

    pnl_arr = np.array(trades_pnl, dtype=np.float64)
    sample_size = min(num_trades, len(trades_pnl))

    # (num_simulations x sample_size) matrix of random PnL samples
    samples = np.random.choice(pnl_arr, size=(num_simulations, sample_size), replace=True)

    # Cumulative balance curves: (num_simulations x sample_size)
    cum_balance = np.cumsum(samples, axis=1)

    # Final balances: (num_simulations,)
    final_balances = cum_balance[:, -1]

    # Running peak and drawdowns — vectorized
    running_peak = np.maximum.accumulate(cum_balance, axis=1)
    drawdowns = running_peak - cum_balance  # (num_simulations x sample_size)
    max_drawdowns = np.max(drawdowns, axis=1)  # (num_simulations,)

    # Статистика
    median_return = np.median(final_balances)
    worst_case_5pct = np.percentile(final_balances, 5)
    best_case_95pct = np.percentile(final_balances, 95)

    # Вероятность разорения (баланс уходит в минус более чем на 50% от пика)
    initial_capital = abs(np.mean(pnl_arr)) * 50  # Примерная оценка капитала
    ruin_count = int(np.sum(max_drawdowns > initial_capital * 0.5))
    ruin_probability = (ruin_count / num_simulations) * 100

    return {
        "median_return": round(float(median_return), 2),
        "worst_case_5pct": round(float(worst_case_5pct), 2),
        "best_case_95pct": round(float(best_case_95pct), 2),
        "avg_max_drawdown": round(float(np.mean(max_drawdowns)), 2),
        "ruin_probability": round(float(ruin_probability), 2),
        "simulations_run": num_simulations
    }

def analyze_time_patterns(trades) -> Dict:
    """
    Анализ паттернов по времени: лучшие/худшие дни недели, часы, месяцы.
    """
    if not trades:
        return {"day_stats": [], "hour_stats": [], "month_stats": []}

    from collections import defaultdict

    day_pnl = defaultdict(list)
    hour_pnl = defaultdict(list)
    month_pnl = defaultdict(list)

    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

    for t in trades:
        if t.pnl is None or not t.entry_at:
            continue

        pnl = float(t.net_pnl if t.net_pnl is not None else t.pnl)
        entry_time = _to_msk(t.entry_at)

        day_pnl[entry_time.weekday()].append(pnl)
        hour_pnl[entry_time.hour].append(pnl)
        month_pnl[entry_time.month].append(pnl)

    # Агрегация по дням
    day_stats = []
    for day_idx in range(7):
        pnls = day_pnl[day_idx]
        if pnls:
            day_stats.append({
                "day": day_names[day_idx],
                "total_pnl": round(sum(pnls), 2),
                "trades": len(pnls),
                "win_rate": round(len([p for p in pnls if p > 0]) / len(pnls) * 100, 1)
            })

    # Агрегация по часам
    hour_stats = []
    for hour in sorted(hour_pnl.keys()):
        pnls = hour_pnl[hour]
        hour_stats.append({
            "hour": f"{hour:02d}:00",
            "total_pnl": round(sum(pnls), 2),
            "trades": len(pnls),
            "win_rate": round(len([p for p in pnls if p > 0]) / len(pnls) * 100, 1)
        })

    # Агрегация по месяцам
    month_stats = []
    for month in sorted(month_pnl.keys()):
        pnls = month_pnl[month]
        month_stats.append({
            "month": month_names[month - 1],
            "total_pnl": round(sum(pnls), 2),
            "trades": len(pnls),
            "win_rate": round(len([p for p in pnls if p > 0]) / len(pnls) * 100, 1)
        })

    # Лучший/худший день
    best_day = max(day_stats, key=lambda x: x["total_pnl"]) if day_stats else None
    worst_day = min(day_stats, key=lambda x: x["total_pnl"]) if day_stats else None

    return {
        "day_stats": day_stats,
        "hour_stats": hour_stats,
        "month_stats": month_stats,
        "best_day": best_day,
        "worst_day": worst_day
    }

"""
Метрики риска и доходности: PF, Sharpe, Sortino, Calmar, Drawdown,
Risk of Ruin, Kelly. Вынесено из монолитного analytics.py.
"""
import math
from datetime import datetime
import numpy as np
from typing import List, Dict, Optional
from decimal import Decimal

from ._common import UNDEFINED, _sanitize

def calculate_advanced_stats(trades_pnl: List[float], trades_risk: List[float]) -> Dict:
    """
    Расчет дополнительных метрик: Profit Factor, R-Expectancy, Recovery Factor.
    """
    if not trades_pnl:
        return {
            "profit_factor": 0,
            "r_expectancy": 0,
            "recovery_factor": 0
        }

    # 1. Profit Factor — суммы считаем в Decimal, чтобы избежать накопления ошибок.
    gross_profit_d = sum((Decimal(str(p)) for p in trades_pnl if p > 0), Decimal(0))
    gross_loss_d = -sum((Decimal(str(p)) for p in trades_pnl if p < 0), Decimal(0))
    gross_profit = float(gross_profit_d)
    gross_loss = float(gross_loss_d)

    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        # Все сделки прибыльные → метрика неопределена, не «99.99 из воздуха».
        profit_factor = UNDEFINED
    else:
        profit_factor = 0.0

    # 2. R-Expectancy
    # If risk data available, use R-multiples
    # Otherwise, use average loss as "risk unit"
    r_multiples = []
    has_risk_data = any(r > 0 for r in trades_risk)

    if has_risk_data:
        for pnl, risk in zip(trades_pnl, trades_risk):
            if risk > 0:
                r_multiples.append(pnl / risk)
    else:
        # Fallback: use average loss as risk unit
        avg_loss = abs(gross_loss / len([p for p in trades_pnl if p < 0])) if gross_loss > 0 else 1
        for pnl in trades_pnl:
            r_multiples.append(pnl / avg_loss)

    r_expectancy = round(float(np.mean(r_multiples)), 2) if r_multiples else 0

    # 3. Recovery Factor
    running_balance = 0
    max_drawdown = 0
    peak = 0

    for pnl in trades_pnl:
        running_balance += pnl
        if running_balance > peak:
            peak = running_balance
        drawdown = peak - running_balance
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    net_profit = float(sum(Decimal(str(p)) for p in trades_pnl))
    if max_drawdown > 0:
        recovery_factor = round(net_profit / max_drawdown, 2)
    elif net_profit > 0:
        recovery_factor = UNDEFINED  # нет просадок — метрика не определена
    else:
        recovery_factor = 0.0

    return {
        "profit_factor": profit_factor,
        "r_expectancy": r_expectancy,
        "recovery_factor": recovery_factor,
        "max_drawdown": round(max_drawdown, 2)
    }

def calculate_sharpe_sortino(trades_pnl: List[float], risk_free_rate: float = 0.0) -> Dict:
    """
    Расчет Sharpe Ratio и Sortino Ratio.
    Sharpe = (Mean Return - Rf) / StdDev(Returns)
    Sortino = (Mean Return - Rf) / Downside Deviation
    """
    if not trades_pnl or len(trades_pnl) < 2:
        return {"sharpe_ratio": 0, "sortino_ratio": 0, "message": "Недостаточно данных"}

    returns = np.array(trades_pnl, dtype=np.float64)
    mean_return = float(np.mean(returns))
    std_dev = float(np.std(returns, ddof=1))

    # Sharpe Ratio
    sharpe = (mean_return - risk_free_rate) / std_dev if std_dev > 0 else 0.0

    # Sortino Ratio = (Mean Return - Rf) / Downside Deviation
    # Используем стандартную downside deviation по всем периодам:
    # sqrt(mean(min(0, r - target)^2))
    downside_diff = np.minimum(returns - risk_free_rate, 0.0)
    downside_dev = float(np.sqrt(np.mean(np.square(downside_diff))))
    if downside_dev > 0:
        sortino = (mean_return - risk_free_rate) / downside_dev
    elif mean_return - risk_free_rate > 0:
        # Все сделки выше risk-free → downside = 0, Sortino математически бесконечен.
        sortino = UNDEFINED
    else:
        sortino = 0.0

    return {
        "sharpe_ratio": round(_sanitize(sharpe) or 0.0, 2),
        "sortino_ratio": round(_sanitize(sortino), 2) if sortino is not None else None,
    }

def calculate_calmar_ratio(trades_pnl: List[float], initial_balance: float = 100000, period_years: float = 1.0) -> Dict:
    """
    Расчет Calmar Ratio (CAGR / Max Drawdown).

    Calmar Ratio показывает соотношение годовой доходности к максимальной просадке.
    Чем выше значение — тем лучше система управляет рисками.

    Интерпретация:
    - < 0.5: Плохо — высокие просадки относительно доходности
    - 0.5-1.0: Удовлетворительно — есть куда улучшать
    - 1.0-2.0: Хорошо — приемлемый баланс риск/доходность
    - 2.0-3.0: Отлично — качественное управление рисками
    - > 3.0: Исключительно — уровень топ хедж-фондов
    """
    if not trades_pnl or len(trades_pnl) < 5:
        return {
            "calmar_ratio": 0,
            "cagr_pct": 0,
            "max_drawdown_pct": 0,
            "rating": "Недостаточно данных",
            "message": "Нужно минимум 5 сделок"
        }
    if initial_balance <= 0:
        return {
            "calmar_ratio": 0,
            "cagr_pct": 0,
            "max_drawdown_pct": 0,
            "rating": "Недостаточно данных",
            "message": "Нужен положительный стартовый баланс"
        }

    # 1. Рассчитываем итоговую доходность
    total_pnl = sum(trades_pnl)
    total_return = total_pnl / initial_balance  # Доходность в долях

    # 2. CAGR (Compound Annual Growth Rate)
    # Если торгуем меньше года, экстраполируем
    if period_years > 0:
        # Формула: (1 + total_return)^(1/years) - 1
        if total_return > -1:  # Чтобы не было отрицательного основания
            cagr = ((1 + total_return) ** (1 / period_years)) - 1
        else:
            cagr = -1  # Полная потеря
    else:
        cagr = total_return

    cagr_pct = cagr * 100

    # 3. Рассчитываем максимальную просадку
    balance = initial_balance
    peak = initial_balance
    max_dd_pct = 0

    for pnl in trades_pnl:
        balance += pnl
        if balance > peak:
            peak = balance

        if peak > 0:
            dd_pct = (peak - balance) / peak * 100
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    # 4. Calmar Ratio = CAGR% / Max Drawdown%
    calmar_undefined = False
    if max_dd_pct > 0:
        calmar = abs(cagr_pct) / max_dd_pct
        if cagr_pct < 0:
            calmar = -calmar  # Отрицательный Calmar для убыточных систем
    elif cagr_pct > 0:
        # Нет просадок → метрика математически не определена.
        # Возвращаем None, чтобы фронт показал «—», а не магическое 99.99.
        calmar = None
        calmar_undefined = True
    else:
        calmar = 0.0

    # 5. Интерпретация
    if calmar_undefined:
        rating = "Без просадок (метрика не определена)"
    elif calmar < 0:
        rating = "Убыточная система"
    elif calmar < 0.5:
        rating = "Плохо"
    elif calmar < 1.0:
        rating = "Удовлетворительно"
    elif calmar < 2.0:
        rating = "Хорошо"
    elif calmar < 3.0:
        rating = "Отлично"
    else:
        rating = "Исключительно"

    return {
        "calmar_ratio": None if calmar is None else round(_sanitize(calmar) or 0.0, 2),
        "cagr_pct": round(_sanitize(cagr_pct) or 0.0, 2),
        "max_drawdown_pct": round(_sanitize(max_dd_pct) or 0.0, 2),
        "rating": rating
    }

def calculate_drawdown_stats(
    trades_pnl: List[float],
    initial_balance: float = 0,
    dates: Optional[List[datetime]] = None,
) -> Dict:
    """
    Расчет статистики просадок.

    dates: опционально — даты соответствующие trades_pnl (тот же порядок и длина).
    Если переданы, в результате будут поля peak_date / trough_date / dd_duration_days.
    """
    if not trades_pnl:
        return {
            "max_drawdown_pct": 0, "max_drawdown_abs": 0, "current_drawdown_pct": 0,
            "peak_balance": initial_balance,
            "peak_date": None, "trough_date": None, "dd_duration_days": None,
        }

    balance = initial_balance
    peak = initial_balance
    cur_peak_idx = None  # индекс trade'а где достигнут текущий peak
    peak_idx = None      # peak соответствующий max просадке
    trough_idx = None    # дно max просадки
    max_dd_abs = 0
    max_dd_pct = 0

    for i, pnl in enumerate(trades_pnl):
        balance += pnl
        if balance > peak:
            peak = balance
            cur_peak_idx = i

        dd_abs = peak - balance
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0

        if dd_abs > max_dd_abs:
            max_dd_abs = dd_abs
            max_dd_pct = dd_pct
            peak_idx = cur_peak_idx
            trough_idx = i

    # Текущая просадка
    current_dd_abs = peak - balance
    current_dd_pct = (current_dd_abs / peak * 100) if peak > 0 else 0

    peak_date_iso = None
    trough_date_iso = None
    dd_duration_days = None
    if dates is not None and len(dates) == len(trades_pnl):
        if peak_idx is not None and peak_idx < len(dates):
            peak_date_iso = dates[peak_idx].isoformat()
        if trough_idx is not None and trough_idx < len(dates):
            trough_date_iso = dates[trough_idx].isoformat()
        if peak_idx is not None and trough_idx is not None:
            dd_duration_days = (dates[trough_idx] - dates[peak_idx]).days

    return {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_abs": round(max_dd_abs, 2),
        "current_drawdown_pct": round(current_dd_pct, 2),
        "peak_balance": round(peak, 2),
        "peak_date": peak_date_iso,
        "trough_date": trough_date_iso,
        "dd_duration_days": dd_duration_days,
    }

def calculate_risk_of_ruin(win_rate: float, payoff_ratio: float, risk_per_trade: float = 0.02) -> Dict:
    """
    Расчет Risk of Ruin — вероятность потерять определённый % капитала.
    Формула: RoR = ((1 - Edge) / (1 + Edge)) ^ Capital_Units
    где Edge = (Win_Rate * Payoff_Ratio) - (1 - Win_Rate)
    """
    if win_rate <= 0 or win_rate >= 1 or payoff_ratio <= 0:
        return {
            "ror_20pct": 0,
            "ror_50pct": 0,
            "message": "Недостаточно данных"
        }

    # Edge = Expected value per unit risked
    edge = (win_rate * payoff_ratio) - (1 - win_rate)

    if edge <= 0:
        # Отрицательное мат. ожидание — разорение неизбежно
        return {
            "ror_20pct": 100.0,
            "ror_50pct": 100.0,
            "message": "Отрицательное мат. ожидание! Разорение неизбежно."
        }

    # Формула Risk of Ruin
    # RoR = ((1 - p) / p) ^ n, где p = win_rate, n = capital units
    # Но с учётом payoff:
    # RoR = ((q/p) * (1/payoff))^n где q = 1 - win_rate

    q = 1 - win_rate

    # Упрощённая формула с учётом edge
    # edge = win_rate * payoff - (1 - win_rate)
    # p_effective = 0.5 + edge/2 (нормированная вероятность)
    p_effective = 0.5 + edge / 2
    p_effective = max(0.01, min(0.99, p_effective))  # Ограничиваем

    if p_effective <= 0.5:
        return {
            "ror_20pct": 100.0,
            "ror_50pct": 100.0,
            "risk_of_ruin_pct": 100.0,
            "message": "Высокий риск разорения"
        }

    # Capital units для разных уровней просадки
    units_20pct = 0.20 / risk_per_trade  # Сколько ставок в 20% капитала
    units_50pct = 0.50 / risk_per_trade

    ratio = (1 - p_effective) / p_effective
    ror_20 = min(100.0, (ratio ** units_20pct) * 100)
    ror_50 = min(100.0, (ratio ** units_50pct) * 100)

    return {
        "ror_20pct": round(ror_20, 2),
        "ror_50pct": round(ror_50, 2),
        "risk_of_ruin_pct": round(ror_50, 2),  # Для совместимости
        "edge": round(edge, 4),
        "message": "OK" if ror_50 < 5 else "Внимание: высокий риск"
    }

def calculate_kelly_criterion(trades_pnl: List[float]) -> Dict:
    """
    Расчет Kelly Criterion.
    Kelly % = W - (1-W)/R
    где W = win rate, R = payoff ratio (avg win / avg loss)
    """
    if not trades_pnl or len(trades_pnl) < 5:
        return {"kelly_pct": 0, "half_kelly": 0, "message": "Недостаточно данных (нужно минимум 5 сделок)"}

    wins = [p for p in trades_pnl if p > 0]
    losses = [p for p in trades_pnl if p < 0]

    if not wins or not losses:
        return {"kelly_pct": 0, "half_kelly": 0, "message": "Нужны и прибыльные, и убыточные сделки"}

    win_rate = len(wins) / len(trades_pnl)
    avg_win = float(np.mean(wins))
    avg_loss = float(abs(np.mean(losses)))

    if avg_loss == 0:
        # Невозможно по структуре (ветка выше требует и wins, и losses), но оставим явный guard.
        return {"kelly_pct": None, "half_kelly": None, "message": "Нет убытков — Kelly не определён"}

    payoff_ratio = avg_win / avg_loss

    # Kelly Formula: K = W - (1-W)/R
    kelly = win_rate - ((1 - win_rate) / payoff_ratio)
    # Отрицательный Kelly валиден — означает «не торгуй». Не клипуем, чтобы не врать пользователю.
    kelly_pct = kelly * 100
    half_kelly = kelly_pct / 2

    return {
        "kelly_pct": round(_sanitize(kelly_pct) or 0.0, 2),
        "half_kelly": round(_sanitize(half_kelly) or 0.0, 2),
        "message": "Рекомендуется Half-Kelly для снижения риска" if kelly_pct > 0
                   else "Отрицательный Kelly — система убыточна, рисковать нельзя",
    }

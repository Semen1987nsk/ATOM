import numpy as np
from typing import List, Dict
from decimal import Decimal

def calculate_optimal_f(trades_pnl: List[float], trades_risk: List[float]) -> Dict:
    """
    Расчет Optimal f по Ральфу Винсу.
    Возвращает ОБА метода расчёта:
    - pnl_method: на основе реальных PnL (всегда доступен)
    - r_method: на основе R-множителей (если есть риски)
    """
    if not trades_pnl or len(trades_pnl) < 2:
        return {
            "optimal_f": 0,
            "pnl_method": None,
            "r_method": None,
            "message": "Недостаточно данных (нужно минимум 2 сделки)",
            "is_valid": False,
            "trades_with_risk": 0,
            "trades_without_risk": len(trades_pnl) if trades_pnl else 0
        }

    pnl_arr = np.array(trades_pnl)
    
    # Проверяем profit factor
    wins_sum = pnl_arr[pnl_arr > 0].sum() if len(pnl_arr[pnl_arr > 0]) > 0 else 0
    losses_sum = abs(pnl_arr[pnl_arr < 0].sum()) if len(pnl_arr[pnl_arr < 0]) > 0 else 0.01
    profit_factor = wins_sum / losses_sum if losses_sum > 0 else 0
    
    if profit_factor < 1.0:
        return {
            "optimal_f": 0,
            "pnl_method": None,
            "r_method": None,
            "message": f"⚠️ Система убыточна (PF={profit_factor:.2f}). Optimal f не применим.",
            "is_valid": False,
            "trades_with_risk": 0,
            "trades_without_risk": len(trades_pnl)
        }
    
    # Считаем сделки с риском и без
    valid_risks = [(pnl, r) for pnl, r in zip(trades_pnl, trades_risk) if r and r > 0]
    trades_with_risk = len(valid_risks)
    trades_without_risk = len(trades_pnl) - trades_with_risk
    
    result = {
        "is_valid": True,
        "trades_with_risk": trades_with_risk,
        "trades_without_risk": trades_without_risk,
        "total_trades": len(trades_pnl)
    }
    
    # ========== МЕТОД 1: PnL (всегда считаем) ==========
    worst_loss = np.min(pnl_arr)
    
    if worst_loss >= 0:
        # Все сделки прибыльные
        result["pnl_method"] = {
            "optimal_f": 0.5,
            "f_10": 5.0,
            "f_4": 12.5,
            "f_2": 25.0,
            "message": "Нет убытков — риск может быть высоким"
        }
    else:
        def get_twr_pnl(f):
            hpr = 1 + f * (pnl_arr / abs(worst_loss))
            if np.any(hpr <= 0):
                return 0.0
            return np.prod(hpr)
        
        f_values = np.linspace(0.01, 0.99, 99)
        twr_values = [get_twr_pnl(f) for f in f_values]
        best_idx = np.argmax(twr_values)
        opt_f_pnl = f_values[best_idx]
        
        result["pnl_method"] = {
            "optimal_f": round(float(opt_f_pnl), 2),
            "f_10": round(float(opt_f_pnl * 10), 2),
            "f_4": round(float(opt_f_pnl * 25), 2),
            "f_2": round(float(opt_f_pnl * 50), 2),
            "worst_loss": round(float(worst_loss), 2),
            "description": "По реальным PnL (без учёта стоп-лоссов)"
        }
    
    # ========== МЕТОД 2: R-множители (если есть риски) ==========
    if trades_with_risk >= 2:
        pnl_with_risk = np.array([p[0] for p in valid_risks])
        risk_arr = np.array([p[1] for p in valid_risks])
        r_multiples = pnl_with_risk / risk_arr
        worst_r = np.min(r_multiples)
        
        if worst_r >= 0:
            result["r_method"] = {
                "optimal_f": 0.5,
                "f_10": 5.0,
                "f_4": 12.5,
                "f_2": 25.0,
                "message": "Нет убытков по R — риск может быть высоким",
                "trades_used": trades_with_risk
            }
        else:
            def get_twr_r(f):
                hpr = 1 + f * (r_multiples / (-worst_r))
                if np.any(hpr <= 0):
                    return 0.0
                return np.prod(hpr)
            
            f_values = np.linspace(0.01, 0.99, 99)
            twr_values = [get_twr_r(f) for f in f_values]
            best_idx = np.argmax(twr_values)
            opt_f_r = f_values[best_idx]
            
            result["r_method"] = {
                "optimal_f": round(float(opt_f_r), 2),
                "f_10": round(float(opt_f_r * 10), 2),
                "f_4": round(float(opt_f_r * 25), 2),
                "f_2": round(float(opt_f_r * 50), 2),
                "worst_r": round(float(worst_r), 2),
                "trades_used": trades_with_risk,
                "description": "По R-множителям (с учётом стоп-лоссов)"
            }
    else:
        result["r_method"] = None
    
    # Основное значение - берём PnL метод как базовый (более консервативный при смешанных данных)
    if result["pnl_method"]:
        result["optimal_f"] = result["pnl_method"]["optimal_f"]
        result["recommended_risk_pct"] = result["pnl_method"]["f_4"]
        result["ultra_conservative_risk_pct"] = result["pnl_method"]["f_10"]
        result["moderate_risk_pct"] = result["pnl_method"]["f_2"]
        result["aggressive_risk_pct"] = result["pnl_method"]["optimal_f"] * 100
    
    # Calculate Geometric Mean (GHPR) using optimal f
    # GHPR = (TWR)^(1/n) where TWR is calculated at optimal f
    opt_f = result.get("optimal_f", 0)
    if opt_f > 0 and worst_loss < 0:
        hpr_values = 1 + opt_f * (pnl_arr / abs(worst_loss))
        if np.all(hpr_values > 0):
            twr = np.prod(hpr_values)
            ghpr = twr ** (1 / len(pnl_arr))
            result["geometric_mean"] = round(float(ghpr), 4)
        else:
            result["geometric_mean"] = 0
    else:
        result["geometric_mean"] = 0
    
    return result

def calculate_z_score(trades_pnl: List[float]) -> Dict:
    """
    Расчет Z-Score (Serial Correlation) для проверки зависимости сделок.
    """
    if not trades_pnl or len(trades_pnl) < 30:
        return {
            "z_score": 0,
            "verdict": "Недостаточно данных (нужно > 30)",
            "confidence": "Low"
        }

    # 1. Определяем последовательность выигрышей (W) и проигрышей (L)
    # 0 - убыток, 1 - прибыль
    sequence = [1 if pnl > 0 else 0 for pnl in trades_pnl if pnl != 0]
    
    n = len(sequence)
    if n < 2:
        return {"z_score": 0, "verdict": "Мало сделок", "confidence": "None"}

    wins = sequence.count(1)
    losses = sequence.count(0)

    # 2. Считаем количество серий (Runs)
    # Серия - это последовательность одинаковых результатов (например, +++ или --)
    runs = 1
    for i in range(1, n):
        if sequence[i] != sequence[i-1]:
            runs += 1

    # 3. Расчет ожидаемого количества серий (Expected Runs)
    # E(R) = 2*W*L / N + 1
    expected_runs = (2 * wins * losses) / n + 1

    # 4. Расчет стандартного отклонения серий
    # StdDev = sqrt( (2*W*L * (2*W*L - N)) / (N^2 * (N-1)) )
    numerator = 2 * wins * losses * (2 * wins * losses - n)
    denominator = (n ** 2) * (n - 1)
    
    if denominator == 0 or numerator < 0:
        # Если numerator < 0, значит слишком мало данных для статистической значимости
        return {"z_score": 0, "verdict": "Недостаточно разнообразия в данных", "confidence": "Low", "description": "Нужно больше разных результатов"}
        
    std_dev = np.sqrt(numerator / denominator)
    
    if std_dev == 0:
        return {"z_score": 0, "verdict": "Недостаточно вариации", "confidence": "Low", "description": "Стандартное отклонение равно 0"}

    # 5. Z-Score
    # Z = (Runs - Expected Runs) / StdDev
    # Используем поправку на непрерывность (0.5)
    if runs > expected_runs:
        z = (runs - expected_runs - 0.5) / std_dev
    else:
        z = (runs - expected_runs + 0.5) / std_dev

    z = float(z)
    
    # Интерпретация
    if z > 1.96:
        verdict = "Отрицательная зависимость (Пила)" # Много смен знака -> Z положительный? 
        # Стоп. В формуле (R - E) / sigma:
        # Если R (фактических серий) БОЛЬШЕ E (ожидаемых), значит знаки меняются ЧАСТО -> Пила. Z > 0.
        # Если R МЕНЬШЕ E, значит знаки меняются РЕДКО -> Тренды (Streaks). Z < 0.
        verdict = "Пила (Чередование)"
        desc = "Прибыль часто сменяется убытком. Optimal f работает хуже."
    elif z < -1.96:
        verdict = "Положительная зависимость (Серии)"
        desc = "Прибыли идут сериями, убытки тоже. Опасно для мартингейла."
    else:
        verdict = "Случайное распределение"
        desc = "Сделки независимы. Optimal f работает корректно."

    return {
        "z_score": round(z, 2),
        "verdict": verdict,
        "description": desc,
        "runs": runs,
        "expected_runs": round(expected_runs, 1)
    }

def calculate_sqn(trades_pnl: List[float], trades_risk: List[float]) -> Dict:
    """
    Расчет SQN (System Quality Number) по Ван Тарпу.
    SQN = (Expectancy / StdDev) * sqrt(N)
    
    Если указаны риски - используем R-multiples.
    Если нет - используем сами PnL.
    """
    if not trades_pnl or len(trades_pnl) < 2:
        return {"sqn": 0, "rating": "Недостаточно данных"}

    # Проверяем есть ли риски
    valid_risks = [r for r in trades_risk if r and r > 0]
    use_r_multiples = len(valid_risks) >= len(trades_pnl) * 0.5  # Минимум 50% сделок с риском
    
    if use_r_multiples:
        # Расчет R-multiples
        r_multiples = []
        for pnl, risk in zip(trades_pnl, trades_risk):
            if risk and risk > 0:
                r_multiples.append(pnl / risk)
        values = np.array(r_multiples)
        method = "r_multiples"
    else:
        # Используем сами PnL
        values = np.array(trades_pnl)
        method = "pnl"
    
    if len(values) < 2:
        return {"sqn": 0, "rating": "Недостаточно данных"}
    
    avg_val = np.mean(values)
    std_dev = np.std(values, ddof=1)  # Стандартное отклонение выборки
    
    if std_dev == 0:
        return {"sqn": 0, "rating": "Стабильно (StdDev=0)"}
        
    n = len(values)
    # Van Tharp рекомендует ограничивать N до 100 для стабильности SQN
    effective_n = min(n, 100)
    sqn = (avg_val / std_dev) * np.sqrt(effective_n)
    
    # Шкала Ван Тарпа
    if sqn < 1.6: rating = "Poor (Слабая)"
    elif sqn < 2.0: rating = "Average (Средняя)"
    elif sqn < 2.5: rating = "Good (Хорошая)"
    elif sqn < 3.0: rating = "Excellent (Отличная)"
    elif sqn < 5.0: rating = "Superb (Превосходная)"
    elif sqn < 7.0: rating = "Holy Grail (Грааль)"
    else: rating = "Holy Grail++"
    
    return {"sqn": round(float(sqn), 2), "rating": rating, "method": method}

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

    # 1. Profit Factor
    gross_profit = sum(p for p in trades_pnl if p > 0)
    gross_loss = abs(sum(p for p in trades_pnl if p < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss != 0 else 99.99

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
            
    net_profit = sum(trades_pnl)
    recovery_factor = round(net_profit / max_drawdown, 2) if max_drawdown > 0 else (99.99 if net_profit > 0 else 0)

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
    
    returns = np.array(trades_pnl)
    mean_return = np.mean(returns)
    std_dev = np.std(returns, ddof=1)
    
    # Sharpe Ratio
    sharpe = (mean_return - risk_free_rate) / std_dev if std_dev > 0 else 0
    
    # Sortino Ratio (только downside deviation)
    negative_returns = returns[returns < 0]
    if len(negative_returns) > 1:
        downside_dev = np.std(negative_returns, ddof=1)
        sortino = (mean_return - risk_free_rate) / downside_dev if downside_dev > 0 else 0
    elif len(negative_returns) == 1:
        # Одна убыточная сделка — используем её как downside dev
        downside_dev = abs(negative_returns[0])
        sortino = (mean_return - risk_free_rate) / downside_dev if downside_dev > 0 else 0
    else:
        sortino = 99.99  # Нет убыточных сделок
    
    return {
        "sharpe_ratio": round(float(sharpe), 2),
        "sortino_ratio": round(float(sortino), 2)
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
    if max_dd_pct > 0:
        calmar = abs(cagr_pct) / max_dd_pct
        if cagr_pct < 0:
            calmar = -calmar  # Отрицательный Calmar для убыточных систем
        # Cap at 100 to avoid misleading huge values when drawdown is tiny
        if calmar > 100:
            calmar = 99.99
    else:
        calmar = 99.99 if cagr_pct > 0 else 0  # Нет просадок
    
    # 5. Интерпретация
    if calmar < 0:
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
        "calmar_ratio": round(float(calmar), 2),
        "cagr_pct": round(float(cagr_pct), 2),
        "max_drawdown_pct": round(float(max_dd_pct), 2),
        "rating": rating
    }


def calculate_drawdown_stats(trades_pnl: List[float], initial_balance: float = 0) -> Dict:
    """
    Расчет статистики просадок.
    """
    if not trades_pnl:
        return {"max_drawdown_pct": 0, "max_drawdown_abs": 0, "current_drawdown_pct": 0}
    
    balance = initial_balance
    peak = initial_balance
    max_dd_abs = 0
    max_dd_pct = 0
    
    for pnl in trades_pnl:
        balance += pnl
        if balance > peak:
            peak = balance
        
        dd_abs = peak - balance
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0
        
        if dd_abs > max_dd_abs:
            max_dd_abs = dd_abs
            max_dd_pct = dd_pct
    
    # Текущая просадка
    current_dd_abs = peak - balance
    current_dd_pct = (current_dd_abs / peak * 100) if peak > 0 else 0
    
    return {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_abs": round(max_dd_abs, 2),
        "current_drawdown_pct": round(current_dd_pct, 2),
        "peak_balance": round(peak, 2)
    }


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
    
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    
    # Payoff Ratio = Avg Win / Avg Loss
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 99.99
    
    # Largest
    largest_win = max(wins) if wins else 0
    largest_loss = min(losses) if losses else 0  # Будет отрицательным
    
    # Expectancy (математическое ожидание в валюте)
    win_rate = len(wins) / len(trades_pnl) if trades_pnl else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    return {
        "win_rate": round(float(win_rate * 100), 2),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "payoff_ratio": round(float(payoff_ratio), 2),
        "largest_win": round(float(largest_win), 2),
        "largest_loss": round(float(largest_loss), 2),
        "expectancy": round(float(expectancy), 2)
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
    
    avg_top_win = np.mean(top_wins) if top_wins else 0
    avg_top_loss = abs(np.mean(top_losses)) if top_losses else 0
    
    tail_ratio = avg_top_win / avg_top_loss if avg_top_loss > 0 else 99.99
    
    return {
        "tail_ratio": round(float(tail_ratio), 2),
        "avg_top_10pct_win": round(float(avg_top_win), 2),
        "avg_top_10pct_loss": round(float(avg_top_loss), 2)
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
    avg_win = np.mean(wins)
    avg_loss = abs(np.mean(losses))
    
    if avg_loss == 0:
        return {"kelly_pct": 100, "half_kelly": 50, "message": "Нет убытков"}
    
    payoff_ratio = avg_win / avg_loss
    
    # Kelly Formula: K = W - (1-W)/R
    kelly = win_rate - ((1 - win_rate) / payoff_ratio)
    kelly_pct = kelly * 100
    
    # Half-Kelly более консервативен
    half_kelly = kelly_pct / 2
    
    return {
        "kelly_pct": round(float(kelly_pct), 2),
        "half_kelly": round(float(half_kelly), 2),
        "message": "Рекомендуется Half-Kelly для снижения риска"
    }


def monte_carlo_simulation(trades_pnl: List[float], num_simulations: int = 1000, num_trades: int = 100) -> Dict:
    """
    Monte Carlo симуляция для стресс-тестирования стратегии.
    Случайно перемешивает сделки и рассчитывает вероятности исходов.
    """
    if not trades_pnl or len(trades_pnl) < 10:
        return {
            "median_return": 0,
            "worst_case_5pct": 0,
            "best_case_95pct": 0,
            "ruin_probability": 0,
            "message": "Недостаточно данных (нужно минимум 10 сделок)"
        }
    
    final_balances = []
    max_drawdowns = []
    
    for _ in range(num_simulations):
        # Случайная выборка сделок с возвратом
        sampled_trades = np.random.choice(trades_pnl, size=min(num_trades, len(trades_pnl)), replace=True)
        
        # Расчет финального баланса
        balance = 0
        peak = 0
        max_dd = 0
        
        for pnl in sampled_trades:
            balance += pnl
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > max_dd:
                max_dd = dd
        
        final_balances.append(balance)
        max_drawdowns.append(max_dd)
    
    final_balances = np.array(final_balances)
    max_drawdowns = np.array(max_drawdowns)
    
    # Статистика
    median_return = np.median(final_balances)
    worst_case_5pct = np.percentile(final_balances, 5)
    best_case_95pct = np.percentile(final_balances, 95)
    
    # Вероятность разорения (баланс уходит в минус более чем на 50% от пика)
    initial_capital = abs(np.mean(trades_pnl)) * 50  # Примерная оценка капитала
    ruin_count = np.sum(max_drawdowns > initial_capital * 0.5)
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
        entry_time = t.entry_at
        
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


def analyze_mae_mfe(trades, mae_method: str = 'weighted_average'):
    """
    Анализирует MAE/MFE для списка сделок.
    Возвращает детальную аналитику и рекомендации.
    
    MAE (Maximum Adverse Excursion) - максимальное движение против позиции в %
    MFE (Maximum Favorable Excursion) - максимальное движение в нашу сторону в %
    
    mae_method:
        - 'weighted_average': от средневзвешенной цены (по умолчанию)
        - 'first_entry': от цены первого входа
    """
    if not trades:
        return {"recommendations": ["Недостаточно данных для анализа"], "trades_analyzed": 0}

    mae_percentages = []  # MAE как % от цены входа
    mfe_percentages = []  # MFE как % от цены входа
    exit_efficiency = []  # Эффективность закрытия: сколько от MFE мы взяли
    edge_ratios = []  # MFE/MAE для каждой сделки
    
    # Данные по выигрышным и проигрышным сделкам
    winners_mae = []
    winners_mfe = []
    winners_efficiency = []
    losers_mae = []
    losers_mfe = []
    losers_efficiency = []
    
    # Данные для распределения
    mae_distribution = []  # (mae_pct, is_winner)
    mfe_distribution = []  # (mfe_pct, is_winner)
    
    # Данные о потерянной прибыли
    profit_left_on_table = []  # В рублях
    
    for t in trades:
        # Нужны закрытые сделки с заполненными MAE/MFE
        if not t.exit_at or not t.entry_price:
            continue
        
        # Определяем базовую цену в зависимости от метода
        if mae_method == 'first_entry' and t.operations:
            # Ищем первый вход в операциях
            entry_ops = [op for op in t.operations if op.get('type') == 'entry']
            if entry_ops:
                entry_price = float(entry_ops[0].get('price', t.entry_price))
            else:
                entry_price = float(t.entry_price)
        else:
            # По умолчанию - средневзвешенная цена
            entry_price = float(t.entry_price)
        
        if entry_price == 0:
            continue
        
        is_long = t.direction.value == 'long'
        pnl = float(t.pnl) if t.pnl else 0
        is_winner = pnl > 0
        qty = float(t.quantity) if t.quantity else 0
        
        mae_pct = 0
        mfe_pct = 0
        
        if t.mae_price:
            mae_price = float(t.mae_price)
            # MAE - насколько цена ушла против нас (в %)
            if is_long:
                mae_pct = (entry_price - mae_price) / entry_price * 100
            else:
                mae_pct = (mae_price - entry_price) / entry_price * 100
            mae_pct = max(0, mae_pct)
            mae_percentages.append(mae_pct)
            mae_distribution.append({"value": round(mae_pct, 2), "winner": is_winner})
            
            if is_winner:
                winners_mae.append(mae_pct)
            else:
                losers_mae.append(mae_pct)
            
        if t.mfe_price:
            mfe_price = float(t.mfe_price)
            # MFE - насколько цена ушла в нашу сторону (в %)
            if is_long:
                mfe_pct = (mfe_price - entry_price) / entry_price * 100
            else:
                mfe_pct = (entry_price - mfe_price) / entry_price * 100
            mfe_pct = max(0, mfe_pct)
            mfe_percentages.append(mfe_pct)
            mfe_distribution.append({"value": round(mfe_pct, 2), "winner": is_winner})
            
            if is_winner:
                winners_mfe.append(mfe_pct)
            else:
                losers_mfe.append(mfe_pct)
            
            # Edge Ratio (MFE/MAE)
            if mae_pct > 0:
                edge = mfe_pct / mae_pct
                edge_ratios.append(edge)
            
            # Эффективность закрытия: сколько от MFE мы реально взяли
            if t.exit_price and mfe_pct > 0:
                exit_price = float(t.exit_price)
                if is_long:
                    actual_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    actual_pct = (entry_price - exit_price) / entry_price * 100
                efficiency = max(0, min(100, actual_pct / mfe_pct * 100))
                exit_efficiency.append(efficiency)
                
                if is_winner:
                    winners_efficiency.append(efficiency)
                else:
                    losers_efficiency.append(efficiency)
                
                # Потерянная прибыль (MFE - actual)
                if qty > 0:
                    max_possible_pnl = (mfe_pct / 100) * entry_price * qty
                    actual_pnl = (actual_pct / 100) * entry_price * qty
                    left = max_possible_pnl - actual_pnl
                    if left > 0:
                        profit_left_on_table.append(left)

    # Статистика
    avg_mae = sum(mae_percentages) / len(mae_percentages) if mae_percentages else 0
    avg_mfe = sum(mfe_percentages) / len(mfe_percentages) if mfe_percentages else 0
    avg_efficiency = sum(exit_efficiency) / len(exit_efficiency) if exit_efficiency else 0
    avg_edge_ratio = sum(edge_ratios) / len(edge_ratios) if edge_ratios else 0
    
    # Percentiles
    def percentile(data, p):
        if not data:
            return 0
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        sorted_data = sorted(data)
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f]) if c != f else sorted_data[f]
    
    mae_percentiles = {
        "p10": round(percentile(mae_percentages, 10), 2),
        "p25": round(percentile(mae_percentages, 25), 2),
        "p50": round(percentile(mae_percentages, 50), 2),
        "p75": round(percentile(mae_percentages, 75), 2),
        "p90": round(percentile(mae_percentages, 90), 2),
        "max": round(max(mae_percentages), 2) if mae_percentages else 0
    }
    
    mfe_percentiles = {
        "p10": round(percentile(mfe_percentages, 10), 2),
        "p25": round(percentile(mfe_percentages, 25), 2),
        "p50": round(percentile(mfe_percentages, 50), 2),
        "p75": round(percentile(mfe_percentages, 75), 2),
        "p90": round(percentile(mfe_percentages, 90), 2),
        "max": round(max(mfe_percentages), 2) if mfe_percentages else 0
    }
    
    # Winners vs Losers comparison
    winners_vs_losers = {
        "winners": {
            "count": len(winners_mae),
            "avg_mae": round(sum(winners_mae) / len(winners_mae), 2) if winners_mae else 0,
            "avg_mfe": round(sum(winners_mfe) / len(winners_mfe), 2) if winners_mfe else 0,
            "avg_efficiency": round(sum(winners_efficiency) / len(winners_efficiency), 1) if winners_efficiency else 0,
        },
        "losers": {
            "count": len(losers_mae),
            "avg_mae": round(sum(losers_mae) / len(losers_mae), 2) if losers_mae else 0,
            "avg_mfe": round(sum(losers_mfe) / len(losers_mfe), 2) if losers_mfe else 0,
            "avg_efficiency": round(sum(losers_efficiency) / len(losers_efficiency), 1) if losers_efficiency else 0,
        }
    }
    
    # Stop Loss optimization
    optimal_stop = mae_percentiles["p75"]  # 75% сделок не пробивали этот уровень
    trades_saved_by_tighter_stop = len([m for m in mae_percentages if m > optimal_stop])
    
    # Entry Quality Score (0-100)
    # Чем меньше MAE, тем лучше входы
    if mae_percentages:
        entry_quality = max(0, min(100, 100 - avg_mae * 20))  # -20 за каждый %
    else:
        entry_quality = 0
    
    # Exit Quality Score (0-100)
    # Основано на эффективности захвата MFE
    exit_quality = avg_efficiency
    
    # Потерянная прибыль
    total_left_on_table = sum(profit_left_on_table) if profit_left_on_table else 0
    avg_left_on_table = total_left_on_table / len(profit_left_on_table) if profit_left_on_table else 0
    
    # Рекомендации
    recommendations = []
    
    if mae_percentages and mfe_percentages:
        # Edge Ratio analysis
        if avg_edge_ratio >= 2:
            recommendations.append({
                "type": "success",
                "icon": "✓",
                "text": f"Отличный Edge Ratio ({avg_edge_ratio:.1f}x). Ваш потенциал прибыли в {avg_edge_ratio:.1f} раза больше риска."
            })
        elif avg_edge_ratio >= 1:
            recommendations.append({
                "type": "warning",
                "icon": "!",
                "text": f"Edge Ratio {avg_edge_ratio:.1f}x — средний. Идеально >2x."
            })
        else:
            recommendations.append({
                "type": "danger",
                "icon": "✕",
                "text": f"Edge Ratio {avg_edge_ratio:.1f}x — низкий. Потенциал прибыли меньше риска."
            })
        
        # Entry quality
        if avg_mae < 1:
            recommendations.append({
                "type": "success",
                "icon": "✓",
                "text": f"Отличные точки входа! Средняя просадка всего {avg_mae:.1f}%."
            })
        elif avg_mae > 3:
            recommendations.append({
                "type": "danger",
                "icon": "✕",
                "text": f"Высокая просадка ({avg_mae:.1f}%). Оптимизируйте точки входа или используйте стоп {optimal_stop:.1f}%."
            })
        
        # Exit efficiency
        if avg_efficiency < 50:
            recommendations.append({
                "type": "warning",
                "icon": "!",
                "text": f"Эффективность выхода {avg_efficiency:.0f}%. Вы закрываетесь слишком рано."
            })
        elif avg_efficiency >= 70:
            recommendations.append({
                "type": "success",
                "icon": "✓",
                "text": f"Хорошая эффективность выхода ({avg_efficiency:.0f}%)."
            })
        
        # Winners vs Losers insight
        if winners_vs_losers["losers"]["avg_mae"] > winners_vs_losers["winners"]["avg_mae"] * 1.5:
            recommendations.append({
                "type": "insight",
                "icon": "💡",
                "text": f"Проигрышные сделки имеют MAE {winners_vs_losers['losers']['avg_mae']:.1f}% vs {winners_vs_losers['winners']['avg_mae']:.1f}% у выигрышных. Рассмотрите более ранний стоп."
            })
        
        # Profit left on table
        if total_left_on_table > 1000:
            recommendations.append({
                "type": "insight",
                "icon": "💰",
                "text": f"Потенциально упущено {total_left_on_table:,.0f} ₽. Средняя упущенная прибыль: {avg_left_on_table:,.0f} ₽/сделку."
            })

    return {
        "avg_mae_pct": round(avg_mae, 2),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_efficiency": round(avg_efficiency, 1),
        "avg_edge_ratio": round(avg_edge_ratio, 2),
        "trades_analyzed": len(mae_percentages),
        
        # Детальная статистика
        "mae_percentiles": mae_percentiles,
        "mfe_percentiles": mfe_percentiles,
        "winners_vs_losers": winners_vs_losers,
        
        # Качество входов/выходов
        "entry_quality_score": round(entry_quality, 0),
        "exit_quality_score": round(exit_quality, 0),
        
        # Оптимизация стопов
        "optimal_stop_pct": round(optimal_stop, 2),
        "trades_above_optimal_stop": trades_saved_by_tighter_stop,
        
        # Упущенная прибыль
        "total_profit_left_on_table": round(total_left_on_table, 0),
        "avg_profit_left_on_table": round(avg_left_on_table, 0),
        
        # Распределения для графиков
        "mae_distribution": mae_distribution[:50],  # Ограничиваем для производительности
        "mfe_distribution": mfe_distribution[:50],
        
        # Рекомендации
        "recommendations": recommendations if recommendations else [{"type": "info", "icon": "ℹ", "text": "Продолжайте торговать для накопления статистики."}]
    }

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

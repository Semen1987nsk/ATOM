"""
Vince/Tharp метрики: Optimal f, Z-Score, SQN.
Вынесено из монолитного analytics.py при разделении пакета.
"""
import math
import numpy as np
from typing import List, Dict
from decimal import Decimal

from ._common import UNDEFINED, _sanitize

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

    pnl_arr = np.array(trades_pnl, dtype=np.float64)

    # Profit Factor по чистым суммам — без магических эпсилонов.
    # При нулевых убытках возвращаем None, а не «фиктивные 99.99».
    wins_sum = float(pnl_arr[pnl_arr > 0].sum())
    losses_sum = float(-pnl_arr[pnl_arr < 0].sum())  # положительная сумма убытков

    if losses_sum > 0:
        profit_factor = wins_sum / losses_sum
    elif wins_sum > 0:
        profit_factor = math.inf  # все сделки прибыльные — PF неопределён
    else:
        profit_factor = 0.0

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

    avg_val = float(np.mean(values))
    std_dev = float(np.std(values, ddof=1))  # Стандартное отклонение выборки (n-1)

    if std_dev == 0:
        return {"sqn": 0, "rating": "Стабильно (StdDev=0)", "method": method, "n": len(values)}

    n = len(values)
    # ВНИМАНИЕ: оригинальная формула Ван Тарпа — sqn = (mean/std) * sqrt(N).
    # Раньше здесь был min(N,100), что искусственно занижало SQN на больших выборках.
    # Возвращаем честный SQN; для сравнения с книжной шкалой добавляем sqn_n100.
    sqrt_n = math.sqrt(n)
    sqn = (avg_val / std_dev) * sqrt_n
    sqn_n100 = (avg_val / std_dev) * math.sqrt(min(n, 100))

    # Шкала Ван Тарпа применяется к sqn_n100 (она и калибровалась на N≤100).
    rating_score = sqn_n100
    if rating_score < 1.6: rating = "Poor (Слабая)"
    elif rating_score < 2.0: rating = "Average (Средняя)"
    elif rating_score < 2.5: rating = "Good (Хорошая)"
    elif rating_score < 3.0: rating = "Excellent (Отличная)"
    elif rating_score < 5.0: rating = "Superb (Превосходная)"
    elif rating_score < 7.0: rating = "Holy Grail (Грааль)"
    else: rating = "Holy Grail++"

    return {
        "sqn": round(_sanitize(sqn) or 0.0, 2),
        "sqn_n100": round(_sanitize(sqn_n100) or 0.0, 2),
        "rating": rating,
        "method": method,
        "n": n,
    }

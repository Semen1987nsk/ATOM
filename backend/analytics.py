import numpy as np
from typing import List, Dict
from decimal import Decimal

def calculate_optimal_f(trades_pnl: List[float], trades_risk: List[float]) -> Dict:
    """
    Расчет Optimal f по Ральфу Винсу.
    trades_pnl: список прибылей/убытков в валюте
    trades_risk: список сумм, которыми рисковали в каждой сделке
    """
    if not trades_pnl or len(trades_pnl) < 2:
        return {"optimal_f": 0, "expected_growth": 0, "message": "Недостаточно данных для расчета (нужно минимум 2 сделки)"}

    # 1. Переводим результаты в R-multiple (результат относительно риска)
    # R = PnL / Risk. Например, заработал $200 при риске $100 -> R = 2.0
    r_multiples = np.array(trades_pnl) / np.array(trades_risk)
    
    # Худший результат (самый большой убыток в R)
    worst_case = np.min(r_multiples)
    if worst_case >= 0:
        # Если убытков нет, математика Винса не работает в классическом виде
        return {"optimal_f": 0.5, "expected_growth": 1.0, "message": "У вас нет убыточных сделок! Риск может быть высоким."}

    # 2. Функция для поиска TWR (Terminal Wealth Relative)
    # TWR = Product(1 + f * (-trade_r / worst_case_r))
    def get_twr(f):
        # Ральф Винс использует нормализацию через худший случай
        hpr = 1 + f * (r_multiples / (-worst_case))
        # Убираем значения <= 0 для логарифма
        hpr = hpr[hpr > 0]
        return np.prod(hpr)

    # 3. Перебор f от 0.01 до 1.0 с шагом 0.01 для поиска максимума
    f_values = np.linspace(0.01, 1.0, 100)
    twr_values = [get_twr(f) for f in f_values]
    
    best_idx = np.argmax(twr_values)
    optimal_f = f_values[best_idx]
    max_twr = twr_values[best_idx]
    
    # Геометрическое среднее (G)
    g = max_twr ** (1 / len(trades_pnl))

    return {
        "optimal_f": round(float(optimal_f), 2),
        "geometric_mean": round(float(g), 4),
        "max_twr": round(float(max_twr), 4),
        "recommended_risk_pct": round(float(optimal_f * 10), 2) # Упрощенная рекомендация
    }

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
    
    if denominator == 0:
        return {"z_score": 0, "verdict": "Ошибка расчета", "confidence": "None"}
        
    std_dev = np.sqrt(numerator / denominator)

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
    Используем R-multiples для расчета.
    """
    if not trades_pnl or len(trades_pnl) < 2:
        return {"sqn": 0, "rating": "Недостаточно данных"}

    # Расчет R-multiples
    r_multiples = []
    for pnl, risk in zip(trades_pnl, trades_risk):
        if risk == 0:
            r_multiples.append(0)
        else:
            r_multiples.append(pnl / risk)
            
    r_array = np.array(r_multiples)
    
    avg_r = np.mean(r_array)
    std_dev_r = np.std(r_array, ddof=1) # Стандартное отклонение выборки
    
    if std_dev_r == 0:
        return {"sqn": 0, "rating": "Стабильно (StdDev=0)"}
        
    n = len(trades_pnl)
    sqn = (avg_r / std_dev_r) * np.sqrt(n)
    
    # Шкала Ван Тарпа
    if sqn < 1.6: rating = "Poor (Слабая)"
    elif sqn < 2.0: rating = "Average (Средняя)"
    elif sqn < 2.5: rating = "Good (Хорошая)"
    elif sqn < 3.0: rating = "Excellent (Отличная)"
    elif sqn < 5.0: rating = "Superb (Превосходная)"
    elif sqn < 7.0: rating = "Holy Grail (Грааль)"
    else: rating = "Holy Grail++"
    
    return {"sqn": round(float(sqn), 2), "rating": rating}

def analyze_mae_mfe(trades):
    """
    Анализирует MAE/MFE для списка сделок.
    Возвращает рекомендации по оптимизации стопов и тейков.
    """
    if not trades:
        return {"recommendations": ["Недостаточно данных для анализа"]}

    mae_ratios = []
    mfe_ratios = []

    for t in trades:
        # Нам нужны закрытые сделки с заполненными MAE/MFE и стоп-лоссом
        if not t.exit_at or not t.stop_loss or not t.entry_price:
            continue
        
        # Расстояние от входа до стопа (риск в пунктах/цене)
        risk_dist = abs(float(t.entry_price) - float(t.stop_loss))
        if risk_dist == 0:
            continue
        
        if t.mae_price:
            # Насколько глубоко цена заходила в минус относительно стопа
            mae_dist = abs(float(t.entry_price) - float(t.mae_price))
            mae_ratios.append(mae_dist / risk_dist)
            
        if t.mfe_price:
            # Насколько далеко цена уходила в плюс относительно риска
            mfe_dist = abs(float(t.entry_price) - float(t.mfe_price))
            mfe_ratios.append(mfe_dist / risk_dist)

    recommendations = []
    
    if mae_ratios:
        avg_mae_ratio = sum(mae_ratios) / len(mae_ratios)
        if avg_mae_ratio < 0.5:
            recommendations.append("Ваши стоп-лоссы слишком широкие. Средний MAE составляет менее 50% от стопа.")
        elif avg_mae_ratio > 0.8:
            recommendations.append("Ваши стоп-лоссы слишком узкие. Цена часто подходит близко к стопу перед разворотом.")

    if mfe_ratios:
        avg_mfe_ratio = sum(mfe_ratios) / len(mfe_ratios)
        # Если цена в среднем уходит в 3 раза дальше риска, а мы закрываем раньше
        if avg_mfe_ratio > 3.0:
            recommendations.append("Вы закрываете сделки слишком рано. Средний MFE значительно превышает ваш риск.")

    return {
        "avg_mae_ratio": round(sum(mae_ratios)/len(mae_ratios), 2) if mae_ratios else 0,
        "avg_mfe_ratio": round(sum(mfe_ratios)/len(mfe_ratios), 2) if mfe_ratios else 0,
        "recommendations": recommendations if recommendations else ["Продолжайте торговать, пока паттерны не выявлены."]
    }

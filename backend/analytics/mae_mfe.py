"""
Maximum Adverse / Favorable Excursion аналитика.
Исторически самый большой блок (>300 строк) — кандидат на дальнейшее
расщепление в Phase 4 (по подметрикам: percentiles, recommendations).
"""
import math
import numpy as np
from typing import List, Dict
from decimal import Decimal

from ._common import UNDEFINED, _sanitize

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
    # Импортируем point_value из pnl_service — для фьючерсов 1 пункт ≠ 1 рубль.
    # Локальный импорт нужен, чтобы избежать цикла на старте приложения.
    try:
        from pnl_service import get_point_value as _get_point_value
    except Exception:  # pragma: no cover - fallback на чистые акции
        def _get_point_value(_symbol):
            return Decimal(1)

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
        pnl = float(t.net_pnl if t.net_pnl is not None else t.pnl or 0)
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

                # Потерянная прибыль (MFE - actual) в валюте сделки.
                # Для фьючерсов нужен point_value: разница цен × qty × pv.
                # Для акций pv = 1 — формула совпадает с прежней.
                #
                # MATH-08: предпочитаем сохранённый Trade.point_value (snapshot
                # на момент закрытия, source = empirical_payment когда cached
                # дрейфует > 5%, см. Phase 9 в models.py:406-412) поверх
                # `_get_point_value(symbol)` — последний возвращает cached
                # значение из Tinkoff metadata, которое для индексных
                # фьючерсов (DAX/Brent/foreign) даёт ×1000-bias.
                if qty > 0:
                    pv = None
                    stored_pv = getattr(t, "point_value", None)
                    if stored_pv is not None:
                        try:
                            pv = float(stored_pv)
                            if pv <= 0:
                                pv = None
                        except (TypeError, ValueError):
                            pv = None
                    if pv is None:
                        try:
                            pv = float(_get_point_value(t.symbol))
                        except Exception:
                            pv = 1.0
                    price_diff_max = entry_price * (mfe_pct / 100.0)
                    price_diff_actual = entry_price * (actual_pct / 100.0)
                    max_possible_pnl = price_diff_max * qty * pv
                    actual_pnl = price_diff_actual * qty * pv
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

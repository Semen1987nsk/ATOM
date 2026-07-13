"""
analytics.advanced — продвинутые quant-метрики.

Эти метрики не нужны новичку, но критически важны для системного трейдера:
Ulcer Index, K-Ratio, Sterling/Omega/MAR ratios, drawdown duration в днях.

Формулы взяты из академических источников:
- Ulcer Index: Peter Martin (1987), https://www.tangotools.com/ui/ui.htm
- K-Ratio: Lars Kestner (1996), Quantitative Trading Strategies
- Sterling Ratio: Deane Sterling Jones (1981)
- Omega Ratio: Keating & Shadwick (2002)
"""
from __future__ import annotations
from typing import List, Dict, Optional, Sequence
from datetime import datetime, timedelta
from collections import defaultdict
import math

import numpy as np
import pytz

from ._common import UNDEFINED, _sanitize


_MSK_TZ = pytz.timezone("Europe/Moscow")


def _to_msk(dt: datetime) -> datetime:
    """naive → трактуем как UTC → в МСК (паттерн market_service._to_msk)."""
    if dt.tzinfo is None:
        return pytz.utc.localize(dt).astimezone(_MSK_TZ)
    return dt.astimezone(_MSK_TZ)


# ─────────────────────────────────────────────────────────────────
# Equity-curve based: Ulcer / K-Ratio / Sterling / Omega / MAR
# ─────────────────────────────────────────────────────────────────

def calculate_ulcer_index(equity_curve: Sequence[float]) -> Optional[float]:
    """
    Ulcer Index — RMS просадок от пика. В отличие от max DD,
    учитывает И глубину, И длительность всех просадок.

    UI = sqrt( mean( (DD%)^2 ) )

    Шкала:
    - UI < 5  → отличная гладкость
    - 5-10    → нормальная
    - > 15    → болезненная стратегия
    """
    if not equity_curve or len(equity_curve) < 2:
        return UNDEFINED

    arr = np.asarray(equity_curve, dtype=float)
    peaks = np.maximum.accumulate(arr)
    # защита от деления на 0 — игнорируем точки, где пик ещё не сформировался
    valid = peaks > 0
    if not valid.any():
        return UNDEFINED

    dd_pct = np.zeros_like(arr)
    dd_pct[valid] = ((peaks[valid] - arr[valid]) / peaks[valid]) * 100.0
    ui = float(np.sqrt(np.mean(dd_pct ** 2)))
    return _sanitize(round(ui, 2))


def calculate_k_ratio(equity_curve: Sequence[float]) -> Optional[float]:
    """
    K-Ratio (Kestner) — линейность equity curve.
    Высокий K = доходность стабильно растёт без рывков.

    K = slope(log_equity) / std_error(slope) × sqrt(N)/N

    Шкала:
    - K > 2     → исключительная гладкость
    - 1 - 2     → хорошо
    - 0.5 - 1   → средне
    - < 0.5     → плохо (доходность от случая)
    """
    if not equity_curve or len(equity_curve) < 10:
        return UNDEFINED

    arr = np.asarray(equity_curve, dtype=float)
    if (arr <= 0).any():
        # log не работает на отрицательных. Сдвигаем в положительную зону.
        shift = abs(arr.min()) + 1.0
        arr = arr + shift

    log_eq = np.log(arr)
    n = len(log_eq)
    x = np.arange(n, dtype=float)

    # МНК-регрессия y = a + b*x
    x_mean = x.mean()
    y_mean = log_eq.mean()
    ss_xx = ((x - x_mean) ** 2).sum()
    if ss_xx == 0:
        return UNDEFINED
    slope = ((x - x_mean) * (log_eq - y_mean)).sum() / ss_xx
    intercept = y_mean - slope * x_mean
    residuals = log_eq - (intercept + slope * x)
    # стандартная ошибка наклона
    if n <= 2:
        return UNDEFINED
    sse = (residuals ** 2).sum()
    se_slope = math.sqrt(sse / (n - 2) / ss_xx) if ss_xx > 0 else 0
    if se_slope == 0:
        return UNDEFINED

    k = (slope / se_slope) * math.sqrt(n) / n
    return _sanitize(round(k, 3))


def calculate_sterling_ratio(annual_return_pct: float, drawdowns_pct: List[float]) -> Optional[float]:
    """
    Sterling Ratio = Annual Return / (avg(top-3 worst DD) + 10%)

    Классическая формула прибавляет 10% (DD хранятся положительными). Буфер
    сглаживает малые просадки, чтобы знаменатель не занижался.
    """
    if not drawdowns_pct or annual_return_pct is None:
        return UNDEFINED

    sorted_dd = sorted(drawdowns_pct, reverse=True)[:3]
    avg_worst_dd = float(np.mean(sorted_dd)) if sorted_dd else 0.0
    denom = avg_worst_dd + 10.0
    if denom <= 0:
        return UNDEFINED
    return _sanitize(round(annual_return_pct / denom, 2))


def calculate_omega_ratio(returns: Sequence[float], threshold: float = 0.0) -> Optional[float]:
    """
    Omega Ratio = sum(returns > threshold) / |sum(returns ≤ threshold)|

    Учитывает ВСЁ распределение, не только среднее и std (как Sharpe).
    threshold обычно = 0 (точка безубытка) или risk-free rate per trade.

    Шкала:
    - Ω > 2 → отлично
    - Ω = 1 → пограничное
    - Ω < 1 → стратегия проигрышная
    """
    if not returns:
        return UNDEFINED

    arr = np.asarray(returns, dtype=float)
    excess = arr - threshold
    gains = excess[excess > 0].sum()
    losses = -excess[excess < 0].sum()
    if losses == 0:
        # Все сделки выше порога — Omega бесконечен. Возвращаем UNDEFINED,
        # фронт нарисует «∞» вместо магического числа.
        return UNDEFINED
    return _sanitize(round(float(gains / losses), 3))


def calculate_mar_ratio(cagr_pct: Optional[float], max_drawdown_pct: Optional[float]) -> Optional[float]:
    """
    MAR Ratio (Managed Account Reports) = CAGR% / |Max DD%|

    Похоже на Calmar, но Calmar обычно считается за 36 мес, MAR — за всю историю.
    У нас всё равно short-history, так что MAR == Calmar de facto, но даём
    отдельную метрику для cross-comparison с hedge fund рейтингами.
    """
    if cagr_pct is None or max_drawdown_pct is None or max_drawdown_pct <= 0:
        return UNDEFINED
    return _sanitize(round(cagr_pct / max_drawdown_pct, 2))


# ─────────────────────────────────────────────────────────────────
# Drawdown duration & recovery
# ─────────────────────────────────────────────────────────────────

def calculate_drawdown_duration(equity_curve: Sequence[float]) -> Dict:
    """
    Возвращает:
    - max_dd_duration_trades: сколько сделок подряд под пиком
    - current_dd_duration_trades: текущая длительность просадки
    - longest_recovery_trades: самое долгое восстановление в прошлом
    - underwater_pct: % всего времени, проведённого в просадке
    """
    if not equity_curve or len(equity_curve) < 2:
        return {
            "max_dd_duration_trades": 0,
            "current_dd_duration_trades": 0,
            "longest_recovery_trades": 0,
            "underwater_pct": 0.0,
        }

    arr = np.asarray(equity_curve, dtype=float)
    peaks = np.maximum.accumulate(arr)
    underwater = arr < peaks  # bool маска

    # Длительность серий «под пиком»
    max_run = 0
    current_run = 0
    longest_recovery = 0
    recovery_run = 0
    for u in underwater:
        if u:
            current_run += 1
            recovery_run += 1
            max_run = max(max_run, current_run)
        else:
            longest_recovery = max(longest_recovery, recovery_run)
            current_run = 0
            recovery_run = 0
    longest_recovery = max(longest_recovery, recovery_run)

    underwater_pct = float(underwater.mean() * 100)

    return {
        "max_dd_duration_trades": int(max_run),
        "current_dd_duration_trades": int(current_run),
        "longest_recovery_trades": int(longest_recovery),
        "underwater_pct": round(underwater_pct, 1),
    }


def collect_drawdown_episodes(equity_curve: Sequence[float]) -> List[float]:
    """
    Возвращает список глубин КАЖДОЙ отдельной просадки в %.
    Используется для Sterling Ratio (требует список DD, а не один max).
    """
    if not equity_curve or len(equity_curve) < 2:
        return []
    arr = np.asarray(equity_curve, dtype=float)
    peaks = np.maximum.accumulate(arr)
    episodes: List[float] = []
    in_dd = False
    deepest = 0.0
    for v, p in zip(arr, peaks):
        if v < p:
            if p > 0:
                dd_pct = (p - v) / p * 100.0
                deepest = max(deepest, dd_pct)
            in_dd = True
        else:
            if in_dd and deepest > 0:
                episodes.append(round(deepest, 2))
            in_dd = False
            deepest = 0.0
    if in_dd and deepest > 0:
        episodes.append(round(deepest, 2))
    return episodes


# ─────────────────────────────────────────────────────────────────
# Behavioral / time analytics
# ─────────────────────────────────────────────────────────────────

HOLD_TIME_BUCKETS = [
    ("< 5 мин", 0, 5),
    ("5-30 мин", 5, 30),
    ("30 мин - 1 ч", 30, 60),
    ("1-4 ч", 60, 240),
    ("4 ч - 1 день", 240, 1440),
    ("1-3 дня", 1440, 4320),
    ("> 3 дней", 4320, float("inf")),
]


def calculate_hold_time_distribution(holding_minutes: List[float], pnls: List[float]) -> List[Dict]:
    """
    Гистограмма по длительности удержания + win-rate в каждом ведре.

    Возвращает список словарей: { bucket, count, win_rate, total_pnl, avg_pnl }
    """
    if not holding_minutes or len(holding_minutes) != len(pnls):
        return []

    out: List[Dict] = []
    for label, lo, hi in HOLD_TIME_BUCKETS:
        idx = [i for i, m in enumerate(holding_minutes) if m is not None and lo <= m < hi]
        if not idx:
            out.append({"bucket": label, "count": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0})
            continue
        bucket_pnls = [pnls[i] for i in idx]
        wins = sum(1 for p in bucket_pnls if p > 0)
        total = sum(bucket_pnls)
        out.append({
            "bucket": label,
            "count": len(idx),
            "win_rate": round(wins / len(idx) * 100, 1),
            "total_pnl": round(total, 2),
            "avg_pnl": round(total / len(idx), 2),
        })
    return out


def calculate_period_breakdown(trades_with_dates: List[Dict]) -> Dict:
    """
    Best/worst неделя, месяц, год.

    Вход: [{ entry_at: datetime, pnl: float }, ...]
    Возвращает: {
      best_week / worst_week: { period, pnl, trades }
      best_month / worst_month: ...
      best_year / worst_year: ...
    }
    """
    if not trades_with_dates:
        return {}

    weekly: Dict[str, Dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
    monthly: Dict[str, Dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
    yearly: Dict[str, Dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0})

    for t in trades_with_dates:
        dt = t.get("entry_at")
        if not isinstance(dt, datetime):
            continue
        dt = _to_msk(dt)  # SSE-1: бакетировать по МСК как heatmap/daily/time_patterns (S3-12)
        pnl = float(t.get("pnl") or 0)
        # ISO week — стандарт
        iso_year, iso_week, _ = dt.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        month_key = f"{dt.year}-{dt.month:02d}"
        year_key = str(dt.year)

        for d, k in ((weekly, week_key), (monthly, month_key), (yearly, year_key)):
            d[k]["pnl"] += pnl
            d[k]["trades"] += 1

    def _best_worst(d: Dict) -> Dict:
        if not d:
            return {}
        best_k = max(d, key=lambda k: d[k]["pnl"])
        worst_k = min(d, key=lambda k: d[k]["pnl"])
        return {
            "best": {"period": best_k, "pnl": round(d[best_k]["pnl"], 2), "trades": d[best_k]["trades"]},
            "worst": {"period": worst_k, "pnl": round(d[worst_k]["pnl"], 2), "trades": d[worst_k]["trades"]},
        }

    return {
        "weekly": _best_worst(weekly),
        "monthly": _best_worst(monthly),
        "yearly": _best_worst(yearly),
    }


def calculate_hour_dow_heatmap(trades_with_dates: List[Dict]) -> List[List[Dict]]:
    """
    Тепловая карта 7×24: PnL и win-rate по дню недели × часу.

    Возвращает матрицу: heatmap[dow][hour] = { count, win_rate, total_pnl }
    dow: 0=ПН ... 6=ВС
    """
    matrix: List[List[Dict]] = [[{"count": 0, "wins": 0, "total_pnl": 0.0} for _ in range(24)] for _ in range(7)]
    for t in trades_with_dates:
        dt = t.get("entry_at")
        if not isinstance(dt, datetime):
            continue
        pnl = float(t.get("pnl") or 0)
        dt = _to_msk(dt)
        cell = matrix[dt.weekday()][dt.hour]
        cell["count"] += 1
        cell["total_pnl"] += pnl
        if pnl > 0:
            cell["wins"] += 1
    # финализация: считаем win_rate
    for row in matrix:
        for cell in row:
            cell["total_pnl"] = round(cell["total_pnl"], 2)
            cell["win_rate"] = round(cell["wins"] / cell["count"] * 100, 1) if cell["count"] else 0.0
            del cell["wins"]
    return matrix


def calculate_plan_adherence(disciplines: List[Optional[int]]) -> Dict:
    """
    Анализ дисциплины — насколько часто следуем плану.

    Поле `discipline` имеет шкалу 1-5 (1=Нарушил, 5=Идеально).
    Возвращаем средний score, % хороших (≥4) и плохих (≤2) сделок.
    """
    valid = [d for d in disciplines if d is not None]
    if not valid:
        return {"avg_score": None, "good_pct": 0.0, "bad_pct": 0.0, "trades_rated": 0}
    avg = sum(valid) / len(valid)
    good = sum(1 for d in valid if d >= 4)
    bad = sum(1 for d in valid if d <= 2)
    return {
        "avg_score": round(avg, 2),
        "good_pct": round(good / len(valid) * 100, 1),
        "bad_pct": round(bad / len(valid) * 100, 1),
        "trades_rated": len(valid),
    }


def calculate_mistake_categories(trades: List[Dict], top_n: int = 5) -> List[Dict]:
    """
    Топ-N тегов с самым отрицательным суммарным PnL (категории ошибок).

    Вход: [{ tags: List[str], pnl: float }, ...]
    """
    bucket: Dict[str, Dict] = defaultdict(lambda: {"total_pnl": 0.0, "count": 0, "losses": 0})
    for t in trades:
        tags = t.get("tags") or []
        if not isinstance(tags, list):
            continue
        pnl = float(t.get("pnl") or 0)
        for tag in tags:
            bucket[tag]["total_pnl"] += pnl
            bucket[tag]["count"] += 1
            if pnl < 0:
                bucket[tag]["losses"] += 1

    items = [
        {
            "tag": tag,
            "total_pnl": round(b["total_pnl"], 2),
            "count": b["count"],
            "loss_count": b["losses"],
            "loss_rate": round(b["losses"] / b["count"] * 100, 1) if b["count"] else 0.0,
        }
        for tag, b in bucket.items()
    ]
    # сортируем по сумме PnL (asc — самые токсичные сверху)
    items.sort(key=lambda x: x["total_pnl"])
    return items[:top_n]


def calculate_commission_ratio(gross_pnl: float, commissions: List[float]) -> Optional[float]:
    """
    Какой % валовой прибыли съедают комиссии.

    Комиссии — это всегда расход, поэтому показываем модуль.
    """
    total_comm = sum(abs(c) for c in commissions if c is not None)
    if gross_pnl <= 0:
        return UNDEFINED
    return _sanitize(round(total_comm / gross_pnl * 100, 1))


def calculate_trade_frequency(entry_dates: List[datetime]) -> Dict:
    """
    Частота торговли: trades/week, trades/month, среднее количество дней между сделками.
    """
    if not entry_dates or len(entry_dates) < 2:
        return {"per_week": 0.0, "per_month": 0.0, "avg_days_between": None}

    sorted_dates = sorted(entry_dates)
    span_days = (sorted_dates[-1] - sorted_dates[0]).days or 1
    n = len(sorted_dates)

    per_week = n / span_days * 7
    per_month = n / span_days * 30

    diffs = [(sorted_dates[i] - sorted_dates[i - 1]).total_seconds() / 86400 for i in range(1, n)]
    avg_gap = sum(diffs) / len(diffs)

    return {
        "per_week": round(per_week, 2),
        "per_month": round(per_month, 2),
        "avg_days_between": round(avg_gap, 2),
        "total_span_days": span_days,
    }


def calculate_psycho_correlations(trades: List[Dict]) -> Dict:
    """
    Корреляция psycho-метрик (mood, confidence, discipline 1-5) с PnL.

    Возвращаем для каждого поля: WR и avg_pnl в разрезе значений шкалы.
    Это даёт инсайт «когда mood=5, win-rate +X%».
    """
    def _agg(field: str) -> List[Dict]:
        buckets: Dict[int, Dict] = defaultdict(lambda: {"wins": 0, "count": 0, "pnl": 0.0})
        for t in trades:
            val = t.get(field)
            if val is None:
                continue
            try:
                key = int(val)
            except (TypeError, ValueError):
                continue
            if not 1 <= key <= 5:
                continue
            pnl = float(t.get("pnl") or 0)
            buckets[key]["count"] += 1
            buckets[key]["pnl"] += pnl
            if pnl > 0:
                buckets[key]["wins"] += 1
        return [
            {
                "value": k,
                "count": v["count"],
                "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0,
                "total_pnl": round(v["pnl"], 2),
                "avg_pnl": round(v["pnl"] / v["count"], 2) if v["count"] else 0,
            }
            for k, v in sorted(buckets.items())
        ]

    return {
        "mood": _agg("mood"),
        "confidence": _agg("confidence"),
        "discipline": _agg("discipline"),
    }


def calculate_news_event_stats(trades: List[Dict]) -> Dict:
    """
    Сделки рядом с новостным событием vs обычные.
    Используется поле `news_event` (например «Отчётность», «ЦБ ставка»).
    """
    with_news = [t for t in trades if t.get("news_event")]
    without_news = [t for t in trades if not t.get("news_event")]

    def _stats(group: List[Dict]) -> Dict:
        if not group:
            return {"count": 0, "win_rate": 0, "avg_pnl": 0, "total_pnl": 0}
        wins = sum(1 for t in group if (t.get("pnl") or 0) > 0)
        total = sum(float(t.get("pnl") or 0) for t in group)
        return {
            "count": len(group),
            "win_rate": round(wins / len(group) * 100, 1),
            "avg_pnl": round(total / len(group), 2),
            "total_pnl": round(total, 2),
        }

    # Топ событий по PnL
    by_event: Dict[str, Dict] = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0.0})
    for t in with_news:
        ev = t["news_event"]
        by_event[ev]["count"] += 1
        by_event[ev]["pnl"] += float(t.get("pnl") or 0)
        if (t.get("pnl") or 0) > 0:
            by_event[ev]["wins"] += 1
    top_events = sorted(
        [
            {
                "event": k,
                "count": v["count"],
                "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0,
                "total_pnl": round(v["pnl"], 2),
            }
            for k, v in by_event.items()
        ],
        key=lambda x: abs(x["total_pnl"]),
        reverse=True,
    )[:5]

    return {
        "with_news": _stats(with_news),
        "without_news": _stats(without_news),
        "top_events": top_events,
    }


def calculate_exit_reason_breakdown(trades: List[Dict]) -> Dict:
    """
    Как закрывал сделки: SL / TP / руками / по таймауту.
    Дополнительно — adherence rate (% сделок с явным SL/TP, и из них сколько достигли).
    """
    by_reason: Dict[str, Dict] = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0.0})
    sl_set, tp_set = 0, 0
    for t in trades:
        reason = (t.get("exit_reason") or "Не указано").strip() or "Не указано"
        by_reason[reason]["count"] += 1
        pnl = float(t.get("pnl") or 0)
        by_reason[reason]["pnl"] += pnl
        if pnl > 0:
            by_reason[reason]["wins"] += 1
        if t.get("stop_loss"):
            sl_set += 1
        if t.get("take_profit"):
            tp_set += 1

    breakdown = sorted(
        [
            {
                "reason": k,
                "count": v["count"],
                "pct": round(v["count"] / len(trades) * 100, 1) if trades else 0,
                "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0,
                "total_pnl": round(v["pnl"], 2),
            }
            for k, v in by_reason.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "by_reason": breakdown,
        "sl_set_pct": round(sl_set / len(trades) * 100, 1) if trades else 0,
        "tp_set_pct": round(tp_set / len(trades) * 100, 1) if trades else 0,
    }


def calculate_r_distribution_histogram(trades: List[Dict]) -> List[Dict]:
    """
    Гистограмма R-мультипликаторов: -3R | -2R | -1R | 0R | +1R | +2R | +3R | +3R+.
    """
    buckets = [
        ("≤ -3R", float("-inf"), -3),
        ("-3R..-2R", -3, -2),
        ("-2R..-1R", -2, -1),
        ("-1R..0", -1, 0),
        ("0..+1R", 0, 1),
        ("+1R..+2R", 1, 2),
        ("+2R..+3R", 2, 3),
        ("≥ +3R", 3, float("inf")),
    ]
    counts = [0] * len(buckets)
    pnls = [0.0] * len(buckets)
    for t in trades:
        r = t.get("r_multiple")
        if r is None:
            continue
        try:
            r_val = float(r)
        except (TypeError, ValueError):
            continue
        for i, (_, lo, hi) in enumerate(buckets):
            if lo <= r_val < hi:
                counts[i] += 1
                pnls[i] += float(t.get("pnl") or 0)
                break
    total = sum(counts)
    return [
        {
            "bucket": label,
            "count": counts[i],
            "pct": round(counts[i] / total * 100, 1) if total else 0,
            "total_pnl": round(pnls[i], 2),
            "is_loss": hi <= 0,
        }
        for i, (label, _, hi) in enumerate(buckets)
    ]


def calculate_tax_visibility(trades: List[Dict], tax_rate: float = 0.13) -> Dict:
    """
    Налоговая прозрачность: брокер сам считает и удерживает, мы просто
    показываем «сколько уйдёт на налог при текущей реализации».

    - YTD realized PnL (сумма закрытых сделок текущего года)
    - Estimated tax (PnL × ставку, только с положительной части)
    - PnL после налога
    """
    current_year = datetime.utcnow().year
    ytd_trades = [
        t for t in trades
        if t.get("exit_at") and isinstance(t["exit_at"], datetime) and t["exit_at"].year == current_year
    ]
    realized = sum(float(t.get("pnl") or 0) for t in ytd_trades)
    # ФЗ-176 (с 01.01.2025): доход от ЦБ облагается 13% до 2.4 млн ₽/год, 15% свыше.
    NDFL_SECURITIES_THRESHOLD_2025 = 2_400_000
    if realized <= NDFL_SECURITIES_THRESHOLD_2025:
        tax = max(realized, 0) * tax_rate
    else:
        tax = NDFL_SECURITIES_THRESHOLD_2025 * tax_rate + (realized - NDFL_SECURITIES_THRESHOLD_2025) * 0.15
    after_tax = realized - tax

    return {
        "year": current_year,
        "realized_ytd": round(realized, 2),
        "trades_ytd": len(ytd_trades),
        "estimated_tax": round(tax, 2),
        "after_tax": round(after_tax, 2),
        "tax_rate_applied": tax_rate if realized <= NDFL_SECURITIES_THRESHOLD_2025 else 0.15,
    }


def calculate_daily_pnl(trades_with_dates: List[Dict]) -> List[Dict]:
    """
    Группировка PnL по дням — для Calendar heatmap.

    Возвращает список {date, pnl, trades_count, win_rate}, отсортированный
    по дате. Используется фронтом для рендера месячных сеток.
    """
    if not trades_with_dates:
        return []

    by_day: Dict[str, Dict] = defaultdict(lambda: {"pnl": 0.0, "wins": 0, "count": 0})
    for t in trades_with_dates:
        dt = t.get("entry_at")
        if not isinstance(dt, datetime):
            continue
        key = _to_msk(dt).strftime("%Y-%m-%d")
        pnl = float(t.get("pnl") or 0)
        by_day[key]["pnl"] += pnl
        by_day[key]["count"] += 1
        if pnl > 0:
            by_day[key]["wins"] += 1

    out = []
    for date in sorted(by_day.keys()):
        d = by_day[date]
        out.append({
            "date": date,
            "pnl": round(d["pnl"], 2),
            "trades_count": d["count"],
            "win_rate": round(d["wins"] / d["count"] * 100, 1) if d["count"] else 0.0,
        })
    return out


def calculate_rr_realized(trades: List[Dict]) -> Dict:
    """
    Risk-Reward planned vs realized.

    Planned RR = (TP - entry) / (entry - SL) для лонга, аналогично для шорта.
    Realized RR = pnl / risk_amount.

    Возвращаем:
    - avg_planned_rr: средний задуманный RR
    - avg_realized_rr: средний фактический R
    - delta: realized − planned (положительная = берёшь больше задуманного)
    - planned_count: сколько сделок имели и SL, и TP
    """
    planned_rrs: List[float] = []
    realized_rrs: List[float] = []

    for t in trades:
        entry = t.get("entry_price")
        sl = t.get("stop_loss")
        tp = t.get("take_profit")
        # direction может быть Enum (SQLAlchemy), .value даёт 'LONG'/'SHORT'.
        raw_dir = t.get("direction")
        if raw_dir is None:
            direction = ""
        elif hasattr(raw_dir, "value"):
            direction = str(raw_dir.value).lower()
        else:
            direction = str(raw_dir).lower()
        risk = t.get("risk_amount")
        pnl = t.get("pnl")

        if entry and sl and tp and direction in ("long", "short"):
            try:
                entry_f, sl_f, tp_f = float(entry), float(sl), float(tp)
                if direction == "long":
                    risk_per_unit = entry_f - sl_f
                    reward_per_unit = tp_f - entry_f
                else:
                    risk_per_unit = sl_f - entry_f
                    reward_per_unit = entry_f - tp_f
                if risk_per_unit > 0 and reward_per_unit > 0:
                    planned_rrs.append(reward_per_unit / risk_per_unit)
            except (TypeError, ValueError):
                pass

        if risk and pnl is not None:
            try:
                r_value = float(risk)
                if r_value > 0:
                    realized_rrs.append(float(pnl) / r_value)
            except (TypeError, ValueError):
                pass

    avg_planned = round(sum(planned_rrs) / len(planned_rrs), 2) if planned_rrs else None
    avg_realized = round(sum(realized_rrs) / len(realized_rrs), 2) if realized_rrs else None
    delta = round(avg_realized - avg_planned, 2) if (avg_planned is not None and avg_realized is not None) else None

    return {
        "avg_planned_rr": avg_planned,
        "avg_realized_rr": avg_realized,
        "delta": delta,
        "planned_count": len(planned_rrs),
        "realized_count": len(realized_rrs),
    }

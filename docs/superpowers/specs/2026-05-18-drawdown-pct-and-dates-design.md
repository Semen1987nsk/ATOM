# Drawdown %% и даты пика/дна — design

**Дата:** 2026-05-18
**Контекст:** dashboard — карточка «Кривая капитала» + «Макс просадка»

## Проблема

Два связанных UX-бага, видимых пользователю на дашборде для broker_user (acc#4):

1. **Шапка карточки «Кривая капитала»** показывает `(-113188.4%)`. Формула берёт `(end - data[0]) / data[0] × 100`. Для broker_user первая точка equity_curve — это PnL первой сделки (≈ 220 ₽), деление на малое число выдаёт сумасшедший процент.

2. **Плитка «Макс просадка»** показывает `−275,522 ₽ / 76.27%`, но **не показывает когда** это было. Пользователь хочет понять период просадки (с какой даты до какой и сколько дней).

## Цель

- Шапка кривой капитала: показать **финансово корректный** % изменения капитала для broker_user (`end / Σ deposits × 100`).
- Плитка «Макс просадка»: добавить **диапазон дат пика и дна** + длительность.
- На самой кривой капитала: визуальный **маркер участка просадки** (ReferenceArea между peak_date и trough_date).

Не меняем: формулу drawdown_pct (она корректна после фикса baseline), Trade.net_pnl, equity_curve данные.

## Архитектура

### Backend

#### `backend/analytics/risk.py: calculate_drawdown_stats`

Расширить сигнатуру:
```python
def calculate_drawdown_stats(
    trades_pnl: List[float],
    initial_balance: float = 0,
    dates: Optional[List[datetime]] = None,  # NEW
) -> Dict:
```

Внутри во время прохода по `trades_pnl` отслеживать:
- `peak_idx` — индекс где было max(balance) на момент peak'а
- `trough_idx` — индекс где было min(balance) ПОСЛЕ peak'а (момент max drawdown)

Если `dates` передан и `len(dates) == len(trades_pnl)`, дополнительно возвращает:
```python
{
    ...existing keys...,
    "peak_date":   dates[peak_idx].isoformat() if peak_idx is not None else None,
    "trough_date": dates[trough_idx].isoformat() if trough_idx is not None else None,
    "dd_duration_days": (dates[trough_idx] - dates[peak_idx]).days if both else None,
}
```

Если `dates` не передан — поля None (backwards-compatible).

#### `backend/routers/stats.py`

При вызове `calculate_drawdown_stats` передавать даты сделок (exit_at, либо entry_at для open):
```python
trade_dates = [
    (t.exit_at or t.entry_at) for t in sorted_trades
    if (t.exit_at or t.entry_at) is not None
]
drawdown_data = analytics.calculate_drawdown_stats(
    pnls_sorted,
    initial_balance=drawdown_baseline,
    dates=trade_dates,
)
```

Surface новые поля в result dict:
```python
"max_drawdown_peak_date":   drawdown_data.get("peak_date"),
"max_drawdown_trough_date": drawdown_data.get("trough_date"),
"max_drawdown_duration_days": drawdown_data.get("dd_duration_days"),
```

### Frontend

#### Плитка «Макс просадка» (`StatsGrid.tsx`)

В `DashboardData` interface добавить:
```ts
max_drawdown_peak_date?: string | null;
max_drawdown_trough_date?: string | null;
max_drawdown_duration_days?: number | null;
```

В `<StatsCard title={t.stats.maxDrawdown.title} ...>` в `description`:
```tsx
description={hasData ? (() => {
  const lines: string[] = [];
  lines.push(formatCurrency(stats?.max_drawdown_abs || 0));
  if (stats?.max_drawdown_peak_date && stats?.max_drawdown_trough_date) {
    const peakStr   = formatShortDate(stats.max_drawdown_peak_date);
    const troughStr = formatShortDate(stats.max_drawdown_trough_date);
    const days = stats.max_drawdown_duration_days ?? 0;
    lines.push(`${peakStr} → ${troughStr} (${days} дней)`);
  }
  return lines.join(' · ');
})() : ''}
```

`formatShortDate` — helper типа `"04 окт 2025"` (toLocaleDateString с {day, month, year}).

#### `EquityCurveCard.tsx` — шапка

Новый prop:
```ts
interface Props {
  ...existing,
  pctBaseline?: number;   // NEW: Σ NET_DEPOSIT для broker_user
  peakDate?: string | null;   // NEW
  troughDate?: string | null; // NEW
}
```

Обновить useMemo `stats`:
```tsx
const stats = useMemo(() => {
  if (!dataAdjusted || dataAdjusted.length === 0) return null;
  const end = dataAdjusted[dataAdjusted.length - 1].balance;

  if (isBrokerCumulative) {
    // Кривая начинается от 0 и показывает cumulative PnL.
    // % изменения = насколько просел/вырос капитал относительно реального
    // historical baseline (Σ NET_DEPOSIT). Без baseline % не показываем —
    // лучше пусто, чем мусор типа -113188%.
    if (!pctBaseline || pctBaseline <= 0) {
      return { start: 0, end, change: end, changePct: null };
    }
    return {
      start: 0,
      end,
      change: end,
      changePct: (end / pctBaseline) * 100,
    };
  }

  const start = initialBalance || dataAdjusted[0].balance;
  const change = end - start;
  const changePct = start !== 0 ? (change / Math.abs(start)) * 100 : 0;
  return { start, end, change, changePct };
}, [dataAdjusted, initialBalance, isBrokerCumulative, pctBaseline]);
```

В JSX header, где сейчас:
```tsx
<span className="opacity-70">
  ({stats.changePct >= 0 ? "+" : ""}{stats.changePct.toFixed(1)}%)
</span>
```

Заменить на conditional:
```tsx
{stats.changePct !== null && stats.changePct !== undefined && (
  <span className="opacity-70">
    ({stats.changePct >= 0 ? "+" : ""}{stats.changePct.toFixed(1)}%)
  </span>
)}
```

#### `EquityCurveCard.tsx` — маркер просадки на графике

Добавить в `<ComposedChart>` перед `<Area>`:
```tsx
{peakDate && troughDate && (
  <ReferenceArea
    x1={peakDate}
    x2={troughDate}
    fill="var(--danger)"
    fillOpacity={0.06}
    ifOverflow="extendDomain"
  />
)}
```

Импортировать `ReferenceArea` из `recharts`. ReferenceLine `y={initialBalance}` (label «Старт») остаётся без изменений.

#### `page.tsx`

Передать новые props в `<EquityCurveCard>`:
```tsx
<EquityCurveCard
  ...existing,
  pctBaseline={stats?.period_start_net_deposit ?? 0}
  peakDate={stats?.max_drawdown_peak_date ?? null}
  troughDate={stats?.max_drawdown_trough_date ?? null}
/>
```

## Тесты

### Backend

Новый файл (или дополнение к существующему): `backend/tests/test_analytics_drawdown_dates.py`:

```python
from datetime import datetime, timedelta
from analytics.risk import calculate_drawdown_stats


def test_returns_peak_and_trough_dates_when_dates_provided():
    base = datetime(2026, 1, 1)
    pnls  = [+100, +200, -50, -300, -200, +50]
    #         peak       drop, drop, drop, recovery
    #  balance: 100, 300, 250, -50, -250, -200 (с initial=0)
    # peak balance = 300 (после второй сделки, idx=1)
    # trough = -250 (после пятой сделки, idx=4)
    dates = [base + timedelta(days=i*10) for i in range(6)]

    result = calculate_drawdown_stats(pnls, initial_balance=1000, dates=dates)

    # initial=1000, balance: 1100, 1300, 1250, 950, 750, 800
    # peak=1300 (idx=1), trough=750 (idx=4, dd_abs=550)
    assert result["peak_date"]   == dates[1].isoformat()
    assert result["trough_date"] == dates[4].isoformat()
    assert result["dd_duration_days"] == 30  # idx 1 → 4 = 3 шагов × 10 дней


def test_dates_optional_backwards_compatible():
    result = calculate_drawdown_stats([+100, -200, +50], initial_balance=1000)
    assert result["peak_date"] is None
    assert result["trough_date"] is None
    assert result["dd_duration_days"] is None
    # Existing fields всё ещё работают
    assert "max_drawdown_pct" in result
    assert "max_drawdown_abs" in result
```

### Frontend

Manual smoke check: открыть дашборд, проверить:
- Шапка кривой капитала: `−248,xxx ₽ (−80.8%)` вместо `(−113188.4%)`.
- Плитка Макс просадка: показывает диапазон дат и длительность.
- График: красная полупрозрачная заливка между пиком и дном.

## План реализации (high-level)

1. Backend: написать failing test для дат.
2. Backend: расширить `calculate_drawdown_stats(dates=...)`.
3. Backend: тесты зелёные.
4. Backend: `stats.py` передаёт даты + surface новые поля в response.
5. Frontend: обновить `DashboardData` interface + добавить даты в плитку «Макс просадка».
6. Frontend: `EquityCurveCard` — pctBaseline + conditional % + ReferenceArea.
7. Frontend: `page.tsx` — передать новые props.
8. Manual smoke check в браузере.

## Риски

- **Recharts `ReferenceArea` с datetime x1/x2** — нужно чтобы строки date matched XAxis dataKey (date в формате "YYYY-MM-DD HH:MM"). Возможен mismatch: backend отдаёт ISO с T и часовым поясом, equity_curve в формате "YYYY-MM-DD HH:MM" (см. stats.py:417). Нормализуем backend response в тот же формат. Mitigation: тест визуальный (либо просто 10 символов префикса date).
- **Trade с exit_at=None** в `sorted_trades` — может попасть в pnls_sorted, но dates list будет короче. Mitigation: filter в stats.py — берём только trades с exit_at (которые уже фильтрованы выше).
- **broker_user без deposits** — `pctBaseline = 0` → header показывает только сумму без %. Это лучше чем мусорное число.

## Что НЕ в скоупе

- Annotation labels «пик»/«дно» на ReferenceArea — overhead, можем добавить позже если нужно.
- Несколько drawdown areas (top-3 drawdowns) — только max.
- Изменение Y-axis на %-scale — слишком инвазивно.

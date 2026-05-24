# Drawdown %% и даты пика/дна — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Убрать мусорный `-113188%` из шапки кривой капитала, добавить даты пика/дна в плитку «Макс просадка», подсветить участок просадки на графике.

**Spec:** `docs/superpowers/specs/2026-05-18-drawdown-pct-and-dates-design.md`

---

### Task 1: TDD — расширить `calculate_drawdown_stats` датами

**Files:**
- Create: `backend/tests/test_analytics_drawdown_dates.py`
- Modify: `backend/analytics/risk.py`

- [ ] **Step 1: Написать failing test**

```python
"""Тесты для peak_date/trough_date в calculate_drawdown_stats."""
from datetime import datetime, timedelta
from analytics.risk import calculate_drawdown_stats


def test_returns_peak_and_trough_dates_when_dates_provided():
    base = datetime(2026, 1, 1)
    pnls  = [+100, +200, -50, -300, -200, +50]
    dates = [base + timedelta(days=i*10) for i in range(6)]
    # initial=1000, balance: 1100, 1300, 1250, 950, 750, 800
    # peak=1300 (idx=1), trough=750 (idx=4, dd_abs=550)
    result = calculate_drawdown_stats(pnls, initial_balance=1000, dates=dates)

    assert result["peak_date"]   == dates[1].isoformat()
    assert result["trough_date"] == dates[4].isoformat()
    assert result["dd_duration_days"] == 30


def test_dates_optional_backwards_compatible():
    result = calculate_drawdown_stats([+100, -200, +50], initial_balance=1000)
    assert result["peak_date"] is None
    assert result["trough_date"] is None
    assert result["dd_duration_days"] is None
    # Existing keys всё ещё работают
    assert "max_drawdown_pct" in result
    assert "max_drawdown_abs" in result
```

- [ ] **Step 2: Run test — expected FAIL (поля peak_date/trough_date/dd_duration_days не существуют)**

```bash
cd backend && python -m pytest tests/test_analytics_drawdown_dates.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Расширить функцию в `analytics/risk.py`**

Изменить сигнатуру + добавить tracking peak_idx и trough_idx:

```python
def calculate_drawdown_stats(
    trades_pnl: List[float],
    initial_balance: float = 0,
    dates: Optional[List[datetime]] = None,
) -> Dict:
    if not trades_pnl:
        return {
            "max_drawdown_pct": 0, "max_drawdown_abs": 0, "current_drawdown_pct": 0,
            "peak_balance": initial_balance,
            "peak_date": None, "trough_date": None, "dd_duration_days": None,
        }

    balance = initial_balance
    peak = initial_balance
    peak_idx = None        # NEW
    trough_idx = None      # NEW
    max_dd_abs = 0
    max_dd_pct = 0
    cur_peak_idx = None    # peak_idx используемый для текущего max drawdown

    for i, pnl in enumerate(trades_pnl):
        balance += pnl
        if balance > peak:
            peak = balance
            cur_peak_idx = i   # запоминаем где был пик
        dd_abs = peak - balance
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0
        if dd_abs > max_dd_abs:
            max_dd_abs = dd_abs
            max_dd_pct = dd_pct
            peak_idx = cur_peak_idx
            trough_idx = i

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
        "peak_date":   peak_date_iso,
        "trough_date": trough_date_iso,
        "dd_duration_days": dd_duration_days,
    }
```

ВНИМАНИЕ к edge case: peak_idx инициализируется None. Если первая сделка убыток (balance < initial_balance), peak никогда не обновляется внутри цикла (он остаётся initial_balance), значит cur_peak_idx остаётся None. Но если есть просадка от initial → peak_idx будет None. Учтём — в этом случае peak_date_iso остаётся None, как и dd_duration_days. Для broker_user (initial = Σ deposits) такой кейс редок (первый pnl чаще не уведёт нас в минус сразу).

Если нужно — fallback: если peak_idx is None но max_dd_abs > 0, используем idx первой сделки в trough'е. Но это complicates. Оставим None в этом edge case — frontend просто не отрисует дату.

- [ ] **Step 4: Запустить тесты**

```bash
cd backend && python -m pytest tests/test_analytics_drawdown_dates.py -v 2>&1 | tail -10
```

Expected: 2 PASS.

Also run regressions:
```bash
cd backend && python -m pytest tests/ -k "drawdown or risk" -v 2>&1 | tail -15
```
Expected: existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_analytics_drawdown_dates.py backend/analytics/risk.py
git commit -m "feat(analytics): calculate_drawdown_stats возвращает peak_date/trough_date/duration

Опциональный параметр dates: List[datetime]. Если передан — функция дополнительно
возвращает дату пика капитала, дату дна max-просадки и длительность в днях.
Backward-compatible: без dates параметра поля возвращаются как None."
```

---

### Task 2: Backend — `stats.py` передаёт даты + surface поля

**Files:**
- Modify: `backend/routers/stats.py`

- [ ] **Step 1: В месте вызова calculate_drawdown_stats передать даты**

Найти строку:
```python
drawdown_data = analytics.calculate_drawdown_stats(pnls_sorted, initial_balance=drawdown_baseline)
```

Перед ней собрать даты:
```python
trade_dates_sorted = [
    (t.exit_at or t.entry_at)
    for t in sorted_trades
    if (t.exit_at or t.entry_at) is not None
]
# Если len дат не совпадает с pnls_sorted — fallback на None (без дат).
dates_arg = trade_dates_sorted if len(trade_dates_sorted) == len(pnls_sorted) else None

drawdown_data = analytics.calculate_drawdown_stats(
    pnls_sorted,
    initial_balance=drawdown_baseline,
    dates=dates_arg,
)
```

- [ ] **Step 2: Surface новые поля в response dict**

Найти где формируется `result = {...}` (есть несколько мест, ищи `"max_drawdown_pct"`). Рядом добавить:
```python
"max_drawdown_peak_date":   drawdown_data.get("peak_date"),
"max_drawdown_trough_date": drawdown_data.get("trough_date"),
"max_drawdown_duration_days": drawdown_data.get("dd_duration_days"),
```

- [ ] **Step 3: Запустить pytest на stats**

```bash
cd backend && python -m pytest -x --tb=short 2>&1 | tail -15
```
Expected: всё зелёное.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/stats.py
git commit -m "feat(stats): surface max_drawdown_peak_date/trough_date/duration в response"
```

---

### Task 3: Frontend — `EquityCurveCard` шапка с pctBaseline

**Files:**
- Modify: `frontend/src/components/dashboard/EquityCurveCard.tsx`

- [ ] **Step 1: Добавить prop `pctBaseline`**

В interface Props (около строк 44-61) добавить:
```ts
  // pctBaseline — для broker_user (isBrokerCumulative=true) используется как
  // знаменатель в % изменения капитала. Σ NET_DEPOSIT = вся capital deployed
  // на счёт за историю. Без baseline % в шапке не отрисуется.
  pctBaseline?: number;
```

Добавить в деструктуризацию props:
```tsx
pctBaseline,
```

- [ ] **Step 2: Обновить useMemo `stats`**

Заменить текущую реализацию (около строк 109-116):
```tsx
const stats = useMemo(() => {
  if (!dataAdjusted || dataAdjusted.length === 0) return null;
  const end = dataAdjusted[dataAdjusted.length - 1].balance;

  if (isBrokerCumulative) {
    // Кривая начинается от 0 → cumulative PnL. % считаем относительно
    // Σ NET_DEPOSIT (реальный historical baseline), не от data[0] (это
    // PnL первой сделки ≈ ноль, делёж даёт мусор типа -113188%).
    if (!pctBaseline || pctBaseline <= 0) {
      return { start: 0, end, change: end, changePct: null as number | null };
    }
    return {
      start: 0,
      end,
      change: end,
      changePct: (end / pctBaseline) * 100 as number | null,
    };
  }

  const start = initialBalance || dataAdjusted[0].balance;
  const change = end - start;
  const changePct = start !== 0 ? (change / Math.abs(start)) * 100 : 0;
  return { start, end, change, changePct: changePct as number | null };
}, [dataAdjusted, initialBalance, isBrokerCumulative, pctBaseline]);
```

- [ ] **Step 3: В JSX header сделать % опциональным**

Заменить (около строк 162-165):
```tsx
<span className="opacity-70">
  ({stats.changePct >= 0 ? "+" : ""}{stats.changePct.toFixed(1)}%)
</span>
```

На:
```tsx
{stats.changePct !== null && stats.changePct !== undefined && (
  <span className="opacity-70">
    ({stats.changePct >= 0 ? "+" : ""}{stats.changePct.toFixed(1)}%)
  </span>
)}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "EquityCurveCard|error TS" | head -10
```
Expected: только pre-existing layout.tsx error.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/EquityCurveCard.tsx
git commit -m "fix(equity-curve): % в шапке для broker_user из pctBaseline (Σ deposits)

Раньше formula (end - data[0]) / data[0]: data[0] для broker_user ≈ 0
(PnL первой сделки), деление давало мусорные числа типа -113188%.

Теперь для isBrokerCumulative считаем end / pctBaseline × 100, где
pctBaseline = Σ NET_DEPOSIT (вся deployed capital). Если pctBaseline
не передан или ≤ 0 — % не показываем (лучше пусто чем мусор)."
```

---

### Task 4: Frontend — ReferenceArea маркер просадки

**Files:**
- Modify: `frontend/src/components/dashboard/EquityCurveCard.tsx`

- [ ] **Step 1: Добавить props peakDate и troughDate**

В Props interface:
```ts
peakDate?: string | null;
troughDate?: string | null;
```

В деструктуризацию props.

- [ ] **Step 2: Импортировать ReferenceArea**

Изменить import из recharts (строки 12-22):
```tsx
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,  // NEW
} from "recharts";
```

- [ ] **Step 3: Добавить ReferenceArea в ComposedChart**

Найти `<ComposedChart>`, добавить **перед** `<Area>`:
```tsx
{peakDate && troughDate && (
  <ReferenceArea
    x1={peakDate.slice(0, 10)}
    x2={troughDate.slice(0, 10)}
    fill="var(--danger)"
    fillOpacity={0.06}
    ifOverflow="extendDomain"
  />
)}
```

ВАЖНО: `.slice(0, 10)` — берём первые 10 символов даты ISO (`YYYY-MM-DD`). Это match XAxis dataKey (`date` в формате `"YYYY-MM-DD HH:MM"` — префиксы `YYYY-MM-DD` совпадают). Recharts matchает строкой equality, так что нужна точная подстрока.

ХМ: если XAxis dataKey === "2026-05-18 14:30" а ReferenceArea x1 === "2026-05-18", они не matched. Reconsider.

Альтернатива: ReferenceArea принимает strings или numbers как x1/x2. Если XAxis tickFormatter преобразует строку в дату, internal matching по строке. Не гарантировано работает корректно. Safest подход: передать ПОЛНУЮ строку из equity_curve (нужно найти ближайшую точку по `peakDate`).

Реализация safe:
```tsx
// Найти ближайшую точку из dataAdjusted по date prefix (YYYY-MM-DD)
const findClosestDate = (target: string): string | null => {
  if (!target || !dataAdjusted) return null;
  const prefix = target.slice(0, 10);
  const point = dataAdjusted.find((p) => p.date.startsWith(prefix));
  return point ? point.date : null;
};
const peakX = peakDate ? findClosestDate(peakDate) : null;
const troughX = troughDate ? findClosestDate(troughDate) : null;
```

И:
```tsx
{peakX && troughX && (
  <ReferenceArea
    x1={peakX}
    x2={troughX}
    fill="var(--danger)"
    fillOpacity={0.06}
  />
)}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "EquityCurveCard|error TS" | head -10
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/EquityCurveCard.tsx
git commit -m "feat(equity-curve): ReferenceArea подсветка участка макс. просадки"
```

---

### Task 5: Frontend — плитка «Макс просадка» с датами

**Files:**
- Modify: `frontend/src/components/dashboard/StatsGrid.tsx`

- [ ] **Step 1: Расширить DashboardData interface**

Добавить:
```ts
max_drawdown_peak_date?: string | null;
max_drawdown_trough_date?: string | null;
max_drawdown_duration_days?: number | null;
```

- [ ] **Step 2: Helper formatShortDate (если ещё нет в файле)**

Добавить локальный helper:
```tsx
const formatShortDate = (iso: string | null | undefined): string => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('ru-RU', {
      day: '2-digit', month: 'short', year: 'numeric'
    });
  } catch { return ''; }
};
```

- [ ] **Step 3: Изменить description в плитке «Макс просадка»**

Найти `<StatsCard title={t.stats.maxDrawdown.title} ...>` (около строки 376). Заменить description prop:
```tsx
description={hasData ? (() => {
  const parts: string[] = [formatCurrency(stats?.max_drawdown_abs || 0)];
  if (stats?.max_drawdown_peak_date && stats?.max_drawdown_trough_date) {
    const peakStr = formatShortDate(stats.max_drawdown_peak_date);
    const troughStr = formatShortDate(stats.max_drawdown_trough_date);
    const days = stats.max_drawdown_duration_days ?? 0;
    parts.push(`${peakStr} → ${troughStr} (${days} дн.)`);
  }
  return parts.join(' · ');
})() : ''}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "StatsGrid|error TS" | head -10
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/StatsGrid.tsx
git commit -m "feat(stats-grid): даты пика и дна в плитке Макс просадка"
```

---

### Task 6: Frontend — `page.tsx` передаёт props в EquityCurveCard

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Найти `<EquityCurveCard ...>` в page.tsx**

```bash
grep -n "EquityCurveCard" /c/Users/Administrator/Empirik/ATOM/frontend/src/app/page.tsx
```

- [ ] **Step 2: Добавить новые props**

В JSX добавить:
```tsx
<EquityCurveCard
  ...existing props,
  pctBaseline={stats?.period_start_net_deposit ?? 0}
  peakDate={stats?.max_drawdown_peak_date ?? null}
  troughDate={stats?.max_drawdown_trough_date ?? null}
/>
```

ПРИМЕЧАНИЕ: `stats?.period_start_net_deposit` — это `Σ NET_DEPOSIT до period_start_date`. Для default (no period filter) это Σ всех deposits. Подходит как baseline для broker_user.

- [ ] **Step 3: TS check + commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "page\.tsx|error TS" | head -10
git add frontend/src/app/page.tsx
git commit -m "feat(page): передать pctBaseline + peak/trough dates в EquityCurveCard"
```

---

### Task 7: Manual smoke check

- [ ] **Step 1: Открыть дашборд acc#4**

В браузере Ctrl+Shift+R.

- [ ] **Step 2: Проверить:**

- Шапка «Кривая капитала»: `−248,xxx ₽ (−80.8%)` (НЕ −113188%)
- Плитка «Макс просадка»: показывает `76.27% · −275,522 ₽ · 04 окт 2025 → 18 мая 2026 (226 дн.)`
- График: красная полупрозрачная заливка между пиком и дном

- [ ] **Step 3: Если есть проблемы — fix отдельным commit'ом, не amend.**

---

## Self-Review

**Spec coverage:**

| Spec пункт | Task |
|---|---|
| Backend `calculate_drawdown_stats(dates=)` | Task 1 |
| Backend `stats.py` передаёт даты | Task 2 |
| EquityCurveCard `pctBaseline` | Task 3 |
| EquityCurveCard ReferenceArea | Task 4 |
| StatsGrid плитка с датами | Task 5 |
| page.tsx передаёт props | Task 6 |
| Manual smoke | Task 7 |
| Тесты backend | Task 1 (TDD) |

Все секции spec покрыты.

**Placeholder scan:** Шаги конкретные с кодом и командами, нет TBD/TODO.

**Type consistency:** Поля `peak_date` / `trough_date` / `dd_duration_days` (backend) → `peak_date` / `trough_date` / `dd_duration_days` в drawdown_data → `max_drawdown_peak_date` / `max_drawdown_trough_date` / `max_drawdown_duration_days` в response dict → одноимённые в DashboardData TS interface. Имя prop'ов EquityCurveCard: `peakDate` / `troughDate` (camelCase) — везде одинаково.

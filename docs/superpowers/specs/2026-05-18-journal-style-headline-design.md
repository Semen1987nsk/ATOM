# Journal-style live headline — design (Phase 6.4)

**Date**: 2026-05-18
**Author**: brainstorm-out (с user'ом, sarvanidi87@gmail.com)
**Supersedes**: Phase 6.3 cash-truth anchored headline (same-day morning), Phase 7 orphan-summing (2026-05-17)
**Related**: `domain/pnl/dashboard_pnl.py`, `routers/stats.py`, `services/pnl_health_service.py`

---

## 1. Цель и контекст

Headline P&L на главном дашборде Eqio должен **совпадать** с тем, что трейдер видит в Дневнике сделок (`/history`). Сейчас они расходятся на ~0.2–0.5%:

- Дневник: `Σ closed Trade.net_pnl + Σ live unrealized_pnl` (через `/trades/unrealized-pnl`, MOEX realtime).
- Dashboard (после Phase 6.3): `last_portfolio_value − Σ net_deposits` (broker cash truth, snapshot из sync'а).

Эта рассинхронизация — фактическая причина жалобы «расхождение осталось» после Phase 6.3 фикса. Headline дашборда математически правильный (matches broker statement), но трейдер сравнивает с Дневником, а не с T-Bank.

**Best-practice анкер**: Tradervue, TraderSync, TradeZella, Edgewonk, IBKR TWS — все показывают headline как **per-trade view** (`realized + unrealized`). Broker reconciliation у них — отдельный health badge, не headline.

## 2. Scope

**In**:
- Backend `routers/stats.py`: переключить `total_pnl_with_unrealized` на journal-формулу.
- Backend `schemas.py::DashboardStats`: новое поле `cash_truth_pnl`.
- Backend `tests/unit/test_dashboard_pnl_headline.py`: обновить под новую семантику.
- Frontend `app/page.tsx`: параллельный fetch `/trades/unrealized-pnl` и live override.
- Frontend `components/dashboard/StatsGrid.tsx`: использовать live unrealized для headline + equity curve tail.

**Out**:
- Logic Дневника сделок (`/history` page, `/trades/unrealized-pnl` endpoint) — не трогаем по жёсткому запросу user'а.
- `pnl_health_service.py` — уже корректен (Phase 6.3 фикс), не трогаем.
- Trade Journal pricing — без изменений.
- ROI, win_rate, profit_factor, MAE/MFE и прочие per-trade метрики — без изменений.

## 3. Архитектура

### Backend `/stats` ответ (изменения)

```typescript
{
  // ─── headline (новая семантика) ───
  total_pnl_with_unrealized: number,        // = total_pnl + unrealized_pnl_position_based (journal-style)
  total_pnl_with_unrealized_gross: number,  // = total_pnl_gross + unrealized_pnl_position_based

  // ─── компоненты ───
  total_pnl: number,                        // Σ closed Trade.net_pnl (unchanged)
  total_pnl_gross: number,                  // Σ closed Trade.pnl (unchanged)
  unrealized_pnl: number,                   // = Σ Position.unrealized_pnl (snapshot)
  unrealized_pnl_position_based: number,    // = unrealized_pnl (alias, для backward-compat)

  // ─── broker reconciliation (NEW) ───
  cash_truth_pnl: number,                   // last_portfolio_value − Σ net_deposits

  // ─── breakdown (info) ───
  account_level_adjustments: number,        // = cash_truth_pnl − total_pnl_with_unrealized (natural residual)
  account_level_adjustments_gross: number,  // = gross variant of same
  total_costs: number,                      // = −(broker + attr_fee + tax + income_tax)
  total_costs_breakdown: { broker_commission, attributed_fees, taxes },

  pnl_health: { ... }                       // PnLHealthBadge (unchanged)
}
```

Замена в `routers/stats.py:541-624`:

```python
if is_broker_user and account is not None:
    # Категории через классификатор (как сейчас).
    raw_broker        = _sum_category(BROKER_COMMISSION)
    raw_attr_fee      = _sum_category(ATTRIBUTABLE_FEE)
    raw_tax           = _sum_category(TAX)
    raw_income_tax    = _sum_category(INCOME_TAX)
    raw_deposits      = _sum_category(NET_DEPOSIT)
    last_portfolio_value = float(account.last_portfolio_value or 0)

    unrealized_pnl    = unrealized_pnl_position_based
    cash_truth_pnl    = last_portfolio_value - raw_deposits

    # Headline (journal-style — per-trade view).
    total_pnl_with_unrealized        = total_pnl + unrealized_pnl
    total_pnl_with_unrealized_gross  = total_pnl_gross + unrealized_pnl

    # Breakdown (info-only). Семантически — для NET; gross headline не имеет
    # cash-truth-эквивалента (gross — это «P&L движение цены без costs»,
    # cash_truth включает costs). Поэтому adjustments_gross = 0.0 (legacy field
    # сохранён для backward-compat schema).
    account_level_adjustments        = cash_truth_pnl - total_pnl_with_unrealized
    account_level_adjustments_gross  = 0.0
    total_costs                      = float(raw_broker + raw_attr_fee + raw_tax + raw_income_tax)
    total_costs_breakdown            = {
        "broker_commission": float(raw_broker),
        "attributed_fees":   float(raw_attr_fee),
        "taxes":             float(raw_tax + raw_income_tax),
    }
else:
    # Manual users: cash_truth_pnl = 0, остальное как раньше.
    unrealized_pnl                   = unrealized_pnl_position_based
    cash_truth_pnl                   = 0.0
    total_pnl_with_unrealized        = total_pnl + unrealized_pnl
    total_pnl_with_unrealized_gross  = total_pnl_gross + unrealized_pnl
    account_level_adjustments        = 0.0
    account_level_adjustments_gross  = 0.0
    total_costs                      = 0.0
    total_costs_breakdown            = {"broker_commission": 0.0, "attributed_fees": 0.0, "taxes": 0.0}
```

`domain/pnl/dashboard_pnl.py` — оставляем как pure utility но обновляем семантику:
- Поле `total_pnl_with_unrealized` теперь = `realized + unrealized` (не cash_truth).
- Поле `total_pnl_with_unrealized_gross` теперь = `realized_gross + unrealized`.
- Новое поле `cash_truth_pnl` = `last_portfolio_value − net_deposits` (для surface через /stats).
- `natural_residual` = `cash_truth_pnl − total_pnl_with_unrealized` (info-only).

### Frontend dashboard (page.tsx)

Параллельный fetch и live override:

```typescript
// Текущий useEffect → загрузка stats
const [statsRes, liveUnrealizedRes] = await Promise.all([
  api.get<DashboardData>('/stats/'),
  api.get<Array<{trade_id: number; unrealized_pnl: number}>>('/trades/unrealized-pnl')
    .catch((e) => { console.warn('live unrealized fetch failed', e); return []; })
]);

const liveUnrealizedSum = liveUnrealizedRes.reduce((s, t) => s + t.unrealized_pnl, 0);
const liveUnrealizedAvailable = liveUnrealizedRes.length > 0;

// Передаём в StatsGrid через props или context
```

В `StatsGrid.tsx`:

```typescript
const headlineUnrealized = liveUnrealizedAvailable
  ? liveUnrealizedSum
  : stats?.unrealized_pnl ?? 0;

const displayTotalPnlWithUnrealized =
  (isGross ? stats?.total_pnl_gross : stats?.total_pnl) ?? 0
  + headlineUnrealized;

// Под headline'ом: subtle timestamp "Цены MOEX: HH:MM" если liveUnrealizedAvailable.
```

### Equity curve

Текущее в `routers/stats.py:649-674`:
```python
_curve_tail_adjustment = unrealized_pnl + account_level_adjustments
equity_curve[-1].balance += _curve_tail_adjustment
```

Меняем — backend больше не добавляет adjustments к tail, оставляем только unrealized:
```python
_curve_tail_adjustment       = unrealized_pnl
_curve_tail_adjustment_gross = unrealized_pnl
```

Frontend опционально пересчитывает tail с live unrealized:
```typescript
// В EquityCurveCard, если liveUnrealizedAvailable:
const lastPoint = curve[curve.length - 1];
const adjustedLast = { ...lastPoint, balance: lastPoint.balance - stats.unrealized_pnl + liveUnrealizedSum };
const displayCurve = [...curve.slice(0, -1), adjustedLast];
```

## 4. Data flow (sequence)

```
User opens /dashboard
       │
       ├─► GET /stats/                          ─► returns realized + position_unrealized + cash_truth + health
       │
       └─► GET /trades/unrealized-pnl           ─► live MOEX prices per open trade
              (parallel, в Promise.all)
              │
              ▼
       Frontend computes:
         headline = total_pnl + Σ live_unrealized
         displayUnrealized = Σ live_unrealized
       │
       ▼
       Рендер:
         "Общий PnL"   headline
         "Реализ."     total_pnl (без unrealized)
         "Нереализ."   Σ live_unrealized + timestamp
         "Прочие"      cash_truth − headline (info, можно скрыть если <100₽)
         badge         pnl_health (ok 0.21%)
```

## 5. Edge cases

| Case | Backend | Frontend | Result |
|---|---|---|---|
| Нет open positions | `/trades/unrealized-pnl` → `[]` | `liveUnrealizedSum = 0` | Headline = realized only ✓ |
| MOEX rate-limit / network fail | `/trades/unrealized-pnl` → 500 / timeout | `.catch()` → `[]` | Fallback на `stats.unrealized_pnl` (position-based) ✓ |
| Manual user без broker | `cash_truth_pnl=0`, остальное unchanged | Live endpoint работает с stored entry/current prices | Headline = realized + unrealized ✓ |
| Gross/Net режим | Backend возвращает оба `*_gross` поля | StatsGrid выбирает по `settings.pnlDisplayMode` | Live override применяется к обоим ✓ |
| Live unrealized = stats.unrealized_pnl (после свежей синхронизации) | Совпадают по числу | Headline стабилен | OK |
| Live unrealized радикально отличается (>20% от position-based) | Допустимо, MOEX сдвинулся | Headline отражает live | OK, badge может стать warning |

## 6. Tests

### Unit (backend)

`tests/unit/test_dashboard_pnl_headline.py` — переписать:
- ❌ `test_headline_equals_cash_truth_for_broker_user` — удалить (старая семантика)
- ✅ `test_headline_equals_realized_plus_unrealized` — new
- ✅ `test_cash_truth_pnl_surfaced_separately` — new (поле в результате)
- ✅ `test_natural_residual_is_cash_truth_minus_headline` — обновить семантику
- ✅ Сохранить: gross-mode, total_costs invariant, edge zeros, profit account

`tests/unit/test_pnl_health.py` — без изменений (15 тестов).

### Integration (backend)

`tests/test_api.py::TestStats` — добавить:
- `test_get_stats_exposes_cash_truth_pnl_field`
- `test_total_pnl_with_unrealized_equals_realized_plus_position_unrealized`

### Manual smoke (frontend)

После deploy на acc#4:
1. Open `/` dashboard while logged in
2. Headline должен показать `−174,421 + (−73,492 ± live drift)` ≈ `−247,914`
3. Open `/history` page
4. Total там должен совпасть с dashboard headline (live unrealized одинаково в обоих местах)
5. PnLHealthBadge: статус `ok`, diff ~0.21–0.5% (зависит от live MOEX cdrift)

## 7. Trade-offs & known limitations

| Trade-off | Severity | Mitigation |
|---|---|---|
| Headline «дышит» с market | low (фича) | Timestamp под цифрой, ясно что это live |
| 1 лишний HTTP req на dashboard load | low | Уже есть в Journal — React Query дедуплицирует |
| Headline != broker statement на ~0.2% | low | PnLHealthBadge surface'ит diff явно |
| MOEX rate limit ~1qps/IP | medium | Cache в `market_data_service` (existing TTL 30s) |
| Live unrealized учитывает entry_price из Trade — для долгих open futures может расходиться с Position.expected_yield от Тинькова | low | Acceptable — Journal уже так считает, user привык |

## 8. Rollback plan

Если что-то ломается на проде:
1. Frontend: убрать `Promise.all` обёртку — вернуться к чтению `stats.total_pnl_with_unrealized`. 1 commit revert.
2. Backend: вернуть Phase 6.3 формулу в `stats.py:541-624`. 1 commit revert.
3. `cash_truth_pnl` field остаётся в schema (не breaking).
4. Tests: revert изменений `test_dashboard_pnl_headline.py`.

## 9. Acceptance criteria

- [ ] `/stats` response содержит `cash_truth_pnl` поле + `total_pnl_with_unrealized = total_pnl + unrealized_pnl`.
- [ ] Unit-тесты `test_dashboard_pnl_headline.py` зелёные (новая семантика).
- [ ] `test_pnl_health.py` без regression'а (15/15 passing).
- [ ] Frontend dashboard headline визуально совпадает с Journal page total ± 0.1% jitter.
- [ ] PnLHealthBadge показывает `ok` со значением 0.1–0.5%.
- [ ] `/trades/unrealized-pnl` failure → graceful fallback на position-based.

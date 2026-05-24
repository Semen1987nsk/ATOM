# Journal-style live headline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard headline P&L = `realized + live unrealized` (matches Дневник сделок), broker reconciliation moved to side card / health badge.

**Architecture:** Backend `/stats` switches from cash-anchored formula to journal-style; new field `cash_truth_pnl` surfaces broker reality separately. Frontend dashboard fetches `/trades/unrealized-pnl` in parallel and overrides headline unrealized with live MOEX prices.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (backend), Next.js 16 App Router (frontend), pytest + Vitest.

**Spec:** `docs/superpowers/specs/2026-05-18-journal-style-headline-design.md`

---

## File Structure

**Backend:**
- Modify `backend/domain/pnl/dashboard_pnl.py` — `compute_pnl_headline()` returns new semantics (headline = realized + unrealized; surface cash_truth_pnl separately).
- Modify `backend/routers/stats.py:541-624` — use new computed values.
- Modify `backend/routers/stats.py:649-674` — equity curve tail = just unrealized (no orphan adj).
- Modify `backend/schemas.py::DashboardStats` — add `cash_truth_pnl: float = 0`.
- Modify `backend/tests/unit/test_dashboard_pnl_headline.py` — replace cash-truth assertions with journal-style.
- Modify `backend/tests/test_api.py` — add `cash_truth_pnl` field integration test.

**Frontend:**
- Modify `frontend/src/app/page.tsx:230` — add parallel fetch `/trades/unrealized-pnl`, pass `liveUnrealizedSum` to StatsGrid.
- Modify `frontend/src/components/dashboard/StatsGrid.tsx` — new prop `liveUnrealizedSum?: number`, override headline if available.
- Modify `frontend/src/components/dashboard/EquityCurveCard.tsx` (or wherever last point is rendered) — replace tail with live unrealized.

---

## Task 1: Update `compute_pnl_headline()` semantics

**Files:**
- Modify: `backend/domain/pnl/dashboard_pnl.py`
- Test: `backend/tests/unit/test_dashboard_pnl_headline.py`

- [ ] **Step 1: Rewrite failing tests with new semantics**

Replace contents of `backend/tests/unit/test_dashboard_pnl_headline.py`:

```python
"""Phase 6.4 (2026-05-18): unit tests для journal-style headline.

Headline = realized_closed + unrealized_position_based (per-trade view, matches
Дневник сделок). cash_truth_pnl surface'ится отдельным полем для broker
reconciliation badge'а.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.pnl.dashboard_pnl import compute_pnl_headline


# Snapshot acc#4 на 2026-05-18: 333 closed trades, 11 open futures.
ACC4_INPUTS = dict(
    realized_closed=Decimal("-174421.80"),
    realized_closed_gross=Decimal("-69131.85"),
    unrealized_position_based=Decimal("-73492.76"),
    last_portfolio_value=Decimal("59448.22"),
    net_deposits=Decimal("308035.79"),
    broker_commission_raw=Decimal("-56773.90"),
    attributable_fee_raw=Decimal("-51160.00"),
    tax_raw=Decimal("-156.00"),
    income_tax_raw=Decimal("0"),
)


def test_headline_equals_realized_plus_unrealized():
    """Phase 6.4 main invariant: headline = closed + open unrealized."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected = Decimal("-174421.80") + Decimal("-73492.76")  # -247914.56
    assert abs(result["total_pnl_with_unrealized"] - expected) < Decimal("0.01")


def test_gross_headline_equals_realized_gross_plus_unrealized():
    """Gross variant — same formula с realized_gross (без commission в closed)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected_gross = Decimal("-69131.85") + Decimal("-73492.76")  # -142624.61
    assert abs(result["total_pnl_with_unrealized_gross"] - expected_gross) < Decimal("0.01")


def test_cash_truth_pnl_surfaced_separately():
    """cash_truth_pnl = portfolio − deposits, для health badge / reconciliation."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected = Decimal("59448.22") - Decimal("308035.79")  # -248587.57
    assert abs(result["cash_truth_pnl"] - expected) < Decimal("0.01")


def test_natural_residual_is_cash_truth_minus_headline():
    """residual = cash_truth − headline (info-only). Должен быть мал на здоровом
    аккаунте — orphan dividends / post-clearing varmargin не покрытые per-trade.
    Для acc#4: cash_truth -248587 минус headline -247914 = -673₽."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected_residual = Decimal("-248587.57") - Decimal("-247914.56")
    assert abs(result["natural_residual"] - expected_residual) < Decimal("0.01")
    assert abs(result["natural_residual"]) < Decimal("1000")


def test_total_costs_is_sum_of_cost_categories():
    """total_costs = broker + attr_fee + tax + income_tax (signed negative)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    expected = Decimal("-56773.90") + Decimal("-51160") + Decimal("-156") + Decimal("0")
    assert abs(result["total_costs"] - expected) < Decimal("0.01")
    assert result["total_costs"] < 0


def test_zero_balance_account_returns_zeros():
    """Empty account: все суммы 0 → всё 0."""
    result = compute_pnl_headline(
        realized_closed=Decimal("0"),
        realized_closed_gross=Decimal("0"),
        unrealized_position_based=Decimal("0"),
        last_portfolio_value=Decimal("0"),
        net_deposits=Decimal("0"),
        broker_commission_raw=Decimal("0"),
        attributable_fee_raw=Decimal("0"),
        tax_raw=Decimal("0"),
        income_tax_raw=Decimal("0"),
    )
    assert result["total_pnl_with_unrealized"] == Decimal("0")
    assert result["total_pnl_with_unrealized_gross"] == Decimal("0")
    assert result["cash_truth_pnl"] == Decimal("0")
    assert result["total_costs"] == Decimal("0")
    assert result["natural_residual"] == Decimal("0")


def test_deposit_only_account_has_zero_pnl_and_zero_residual():
    """Депозит без сделок: portfolio = deposits → cash_truth=0, headline=0."""
    result = compute_pnl_headline(
        realized_closed=Decimal("0"),
        realized_closed_gross=Decimal("0"),
        unrealized_position_based=Decimal("0"),
        last_portfolio_value=Decimal("100000"),
        net_deposits=Decimal("100000"),
        broker_commission_raw=Decimal("0"),
        attributable_fee_raw=Decimal("0"),
        tax_raw=Decimal("0"),
        income_tax_raw=Decimal("0"),
    )
    assert result["total_pnl_with_unrealized"] == Decimal("0")
    assert result["cash_truth_pnl"] == Decimal("0")
    assert result["natural_residual"] == Decimal("0")


def test_profitable_account_with_dividends_orphan():
    """Аккаунт с прибылью + дивиденд после закрытия позиции.
    Дивиденд +500 не учтён в realized (закрытая trade не получала div),
    но он в portfolio. Поэтому: headline=8000+3000=11000, cash_truth=11500,
    natural_residual=+500 (это orphan dividend)."""
    result = compute_pnl_headline(
        realized_closed=Decimal("8000"),
        realized_closed_gross=Decimal("10000"),
        unrealized_position_based=Decimal("3000"),
        last_portfolio_value=Decimal("111500"),
        net_deposits=Decimal("100000"),
        broker_commission_raw=Decimal("-2000"),
        attributable_fee_raw=Decimal("0"),
        tax_raw=Decimal("0"),
        income_tax_raw=Decimal("-150"),
    )
    assert result["total_pnl_with_unrealized"] == Decimal("11000")
    assert result["cash_truth_pnl"] == Decimal("11500")
    assert result["natural_residual"] == Decimal("500")
    assert result["total_costs"] == Decimal("-2150")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -X utf8 -m pytest tests/unit/test_dashboard_pnl_headline.py -v`

Expected: FAIL — текущий `compute_pnl_headline` возвращает `cash_truth` как `total_pnl_with_unrealized`, не `realized + unrealized`. И нет ключа `cash_truth_pnl` в return dict.

- [ ] **Step 3: Update `compute_pnl_headline()` implementation**

Replace `backend/domain/pnl/dashboard_pnl.py` content:

```python
"""Dashboard P&L headline — journal-style (Phase 6.4).

Phase 6.4 (2026-05-18): headline = `realized_closed + unrealized_position_based`
matches per-trade view in Дневник сделок. cash_truth_pnl surfaces broker
reality separately for the PnLHealthBadge / reconciliation card.

History:
- Phase 7 (2026-05-17): `realized + unrealized + orphan_adjustments` — double-
  counted varmargin для open futures → 2% overshoot vs broker.
- Phase 6.3 (2026-05-18 AM): anchored headline = cash_truth — matched broker
  but diverged from journal page by natural_residual (~0.2%).
- Phase 6.4 (this): journal-style headline + broker delta as separate signal
  (best practice — Tradervue, TraderSync, TradeZella, IBKR).

См. `tests/unit/test_dashboard_pnl_headline.py` для invariants.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict


class DashboardHeadline(TypedDict):
    total_pnl_with_unrealized: Decimal       # = realized_closed + unrealized
    total_pnl_with_unrealized_gross: Decimal  # = realized_gross + unrealized
    cash_truth_pnl: Decimal                   # = portfolio − deposits (broker)
    total_costs: Decimal                      # = broker + attr_fee + tax + income_tax
    natural_residual: Decimal                 # = cash_truth − headline (orphan delta)


def compute_pnl_headline(
    *,
    realized_closed: Decimal,
    realized_closed_gross: Decimal,
    unrealized_position_based: Decimal,
    last_portfolio_value: Decimal,
    net_deposits: Decimal,
    broker_commission_raw: Decimal,
    attributable_fee_raw: Decimal,
    tax_raw: Decimal,
    income_tax_raw: Decimal,
) -> DashboardHeadline:
    total_pnl_with_unrealized = realized_closed + unrealized_position_based
    total_pnl_with_unrealized_gross = realized_closed_gross + unrealized_position_based

    cash_truth_pnl = last_portfolio_value - net_deposits
    natural_residual = cash_truth_pnl - total_pnl_with_unrealized

    total_costs = (
        broker_commission_raw
        + attributable_fee_raw
        + tax_raw
        + income_tax_raw
    )

    return {
        "total_pnl_with_unrealized": total_pnl_with_unrealized,
        "total_pnl_with_unrealized_gross": total_pnl_with_unrealized_gross,
        "cash_truth_pnl": cash_truth_pnl,
        "total_costs": total_costs,
        "natural_residual": natural_residual,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -X utf8 -m pytest tests/unit/test_dashboard_pnl_headline.py -v`

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd C:/Users/Administrator/Empirik/ATOM
git add backend/domain/pnl/dashboard_pnl.py backend/tests/unit/test_dashboard_pnl_headline.py
git commit -m "$(cat <<'EOF'
feat(pnl): phase 6.4 — journal-style dashboard headline

Headline now matches Дневник сделок (realized + unrealized) instead of
cash-anchored. cash_truth_pnl surfaced separately for health reconciliation.

Best practice: per-trade view as headline (Tradervue/TraderSync/TradeZella),
broker reconciliation as separate signal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Wire `stats.py` to new headline + add schema field

**Files:**
- Modify: `backend/routers/stats.py:541-624`
- Modify: `backend/routers/stats.py:649-674` (equity curve tail)
- Modify: `backend/schemas.py:721` (add `cash_truth_pnl`)
- Test: `backend/tests/test_api.py::TestStats`

- [ ] **Step 1: Write integration test (RED)**

Add to `backend/tests/test_api.py::TestStats` (after existing tests):

```python
def test_get_stats_exposes_cash_truth_pnl_field(self, client_with_user, broker_account_with_data):
    """Phase 6.4: cash_truth_pnl field surface'ится для PnLHealthBadge."""
    response = client_with_user.get('/stats/')
    assert response.status_code == 200
    data = response.json()
    assert "cash_truth_pnl" in data, "response должен содержать cash_truth_pnl field"
    # Для тестового broker-аккаунта cash_truth = last_portfolio_value − Σ deposits
    assert isinstance(data["cash_truth_pnl"], (int, float))


def test_total_pnl_with_unrealized_equals_realized_plus_unrealized(
    self, client_with_user, broker_account_with_data
):
    """Phase 6.4 headline invariant: total_pnl_with_unrealized == total_pnl + unrealized_pnl
    (НЕ cash_truth — это разные числа на ~0.2% residual)."""
    response = client_with_user.get('/stats/')
    data = response.json()
    expected = data["total_pnl"] + data.get("unrealized_pnl", 0)
    assert abs(data["total_pnl_with_unrealized"] - expected) < 0.01, (
        f"headline {data['total_pnl_with_unrealized']} != realized {data['total_pnl']} "
        f"+ unrealized {data.get('unrealized_pnl', 0)}"
    )
```

Если фикстуры `broker_account_with_data` нет — добавить вверху файла (или использовать existing). Если фикстура есть — пропустить создание.

- [ ] **Step 2: Run integration test to verify failure**

Run: `cd backend && python -X utf8 -m pytest tests/test_api.py::TestStats::test_get_stats_exposes_cash_truth_pnl_field -v`

Expected: FAIL — `cash_truth_pnl` отсутствует в response.

- [ ] **Step 3: Add field to schema**

In `backend/schemas.py`, find `total_costs_breakdown: dict = {}` (around line 721) and add **after** it:

```python
    # Phase 6.4 (2026-05-18): broker cash truth для PnLHealthBadge.
    # cash_truth_pnl = last_portfolio_value − Σ NET_DEPOSIT. Используется отдельно
    # от headline (total_pnl_with_unrealized = realized + unrealized, journal-style).
    cash_truth_pnl: float = 0
```

- [ ] **Step 4: Replace broker-user branch in `stats.py`**

Locate in `backend/routers/stats.py` the block starting `if is_broker_user and account is not None:` (около строки 541). Replace it including the `else` branch до строки 647 with:

```python
    # Phase 6.4 (2026-05-18): journal-style headline anchored к per-trade tracking
    # (matches Дневник). cash_truth_pnl surface'ится отдельно для PnLHealthBadge.
    # См. domain/pnl/dashboard_pnl.py + tests/unit/test_dashboard_pnl_headline.py.
    if is_broker_user and account is not None:
        from domain.pnl.cash_flow_classification import (
            CashFlowCategory,
            operation_types_in,
        )
        from domain.pnl.dashboard_pnl import compute_pnl_headline
        from decimal import Decimal

        def _sum_category(cat: CashFlowCategory) -> float:
            types = tuple(operation_types_in(cat))
            if not types:
                return 0.0
            row = db.query(
                func.coalesce(func.sum(OperationORM.payment_units), 0),
                func.coalesce(func.sum(OperationORM.payment_nano), 0),
            ).filter(
                OperationORM.account_id == account_id,
                OperationORM.operation_type.in_(types),
                OperationORM.state == "executed",
            ).one()
            return float(row[0] or 0) + float(row[1] or 0) / 1e9

        raw_attr_fee   = _sum_category(CashFlowCategory.ATTRIBUTABLE_FEE)
        raw_tax        = _sum_category(CashFlowCategory.TAX)
        raw_income_tax = _sum_category(CashFlowCategory.INCOME_TAX)
        raw_broker     = _sum_category(CashFlowCategory.BROKER_COMMISSION)
        raw_deposits   = _sum_category(CashFlowCategory.NET_DEPOSIT)

        last_portfolio_value = float(account.last_portfolio_value or 0)

        headline = compute_pnl_headline(
            realized_closed=Decimal(str(total_pnl)),
            realized_closed_gross=Decimal(str(total_pnl_gross)),
            unrealized_position_based=Decimal(str(unrealized_pnl_position_based)),
            last_portfolio_value=Decimal(str(last_portfolio_value)),
            net_deposits=Decimal(str(raw_deposits)),
            broker_commission_raw=Decimal(str(raw_broker)),
            attributable_fee_raw=Decimal(str(raw_attr_fee)),
            tax_raw=Decimal(str(raw_tax)),
            income_tax_raw=Decimal(str(raw_income_tax)),
        )

        unrealized_pnl                  = unrealized_pnl_position_based
        total_pnl_with_unrealized       = float(headline["total_pnl_with_unrealized"])
        total_pnl_with_unrealized_gross = float(headline["total_pnl_with_unrealized_gross"])
        cash_truth_pnl                  = float(headline["cash_truth_pnl"])
        total_costs                     = float(headline["total_costs"])

        # natural_residual = cash_truth − headline (orphan delta: post-clearing
        # varmargin, dividends на закрытых позициях). Info-only — surface через
        # account_level_adjustments для UI breakdown card. НЕ влияет на headline.
        account_level_adjustments       = float(headline["natural_residual"])
        # gross headline не имеет cash-truth-эквивалента (gross != broker view).
        account_level_adjustments_gross = 0.0

        total_costs_breakdown = {
            "broker_commission": float(raw_broker),
            "attributed_fees":   float(raw_attr_fee),
            "taxes":             float(raw_tax + raw_income_tax),
        }
    else:
        unrealized_pnl                  = unrealized_pnl_position_based
        total_pnl_with_unrealized       = total_pnl + unrealized_pnl
        total_pnl_with_unrealized_gross = total_pnl_gross + unrealized_pnl
        cash_truth_pnl                  = 0.0
        account_level_adjustments       = 0.0
        account_level_adjustments_gross = 0.0
        total_costs                     = 0.0
        total_costs_breakdown = {
            "broker_commission": 0.0,
            "attributed_fees":   0.0,
            "taxes":             0.0,
        }
```

- [ ] **Step 5: Update equity curve tail (Phase 6.4 — only unrealized, no orphan)**

In `backend/routers/stats.py` find `_curve_tail_adjustment = unrealized_pnl + account_level_adjustments` (около строки 654). Replace block:

```python
    # Phase 6.4 (2026-05-18): equity_curve tail = realized cumulative + unrealized
    # (matches journal-style headline). account_level_adjustments не добавляем —
    # они info-only residual, не часть headline.
    _curve_tail_adjustment = unrealized_pnl
    if equity_curve and _curve_tail_adjustment != 0:
        last = equity_curve[-1]
        equity_curve = equity_curve[:-1] + [
            {
                "date": last["date"],
                "balance": round(last["balance"] + _curve_tail_adjustment, 2),
            }
        ]

    _curve_tail_adjustment_gross = unrealized_pnl
    if equity_curve_gross and _curve_tail_adjustment_gross != 0:
        last = equity_curve_gross[-1]
        equity_curve_gross = equity_curve_gross[:-1] + [
            {
                "date": last["date"],
                "balance": round(last["balance"] + _curve_tail_adjustment_gross, 2),
            }
        ]
```

- [ ] **Step 6: Add `cash_truth_pnl` to result dict**

In `backend/routers/stats.py` find `"total_pnl_with_unrealized": total_pnl_with_unrealized,` in the result dict (около строки 681) and add **after** it:

```python
        "cash_truth_pnl": cash_truth_pnl,
```

- [ ] **Step 7: Run integration tests to verify pass**

Run: `cd backend && python -X utf8 -m pytest tests/test_api.py::TestStats -v`

Expected: все TestStats тесты passing, включая два новых.

- [ ] **Step 8: Run full unit suite to ensure no regression**

Run: `cd backend && python -X utf8 -m pytest tests/unit/ -q`

Expected: 470+ passed (previous baseline).

- [ ] **Step 9: Commit**

```bash
cd C:/Users/Administrator/Empirik/ATOM
git add backend/routers/stats.py backend/schemas.py backend/tests/test_api.py
git commit -m "$(cat <<'EOF'
feat(stats): wire journal-style headline + expose cash_truth_pnl field

/stats теперь возвращает:
- total_pnl_with_unrealized = realized + position_unrealized (journal-style)
- cash_truth_pnl = portfolio − deposits (broker reconciliation)
- account_level_adjustments = natural_residual (info-only)

Equity curve tail обновляется только на unrealized, не на orphan adjustments.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Frontend — parallel fetch of live unrealized

**Files:**
- Modify: `frontend/src/app/page.tsx:230-256` (fetch block + state)
- Modify: `frontend/src/app/page.tsx` (interface + props passing)
- Modify: `frontend/src/components/dashboard/StatsGrid.tsx`

- [ ] **Step 1: Add `cash_truth_pnl` to DashboardData interface**

In `frontend/src/app/page.tsx`, find `interface DashboardData` (around line 59) and add after `total_pnl_with_unrealized?: number;`:

```typescript
  cash_truth_pnl?: number;
```

In `frontend/src/components/dashboard/StatsGrid.tsx`, find the same interface (around line 33) and add:

```typescript
  cash_truth_pnl?: number;
```

- [ ] **Step 2: Add `liveUnrealizedSum` state + parallel fetch in page.tsx**

In `frontend/src/app/page.tsx`, find existing state declarations (where `setStats` is used). Add new state variable:

```typescript
const [liveUnrealizedSum, setLiveUnrealizedSum] = useState<number | null>(null);
```

Then in `fetchData` (line ~230) replace:

```typescript
const [statsData, tradesData] = await Promise.all([
  api.get<DashboardData>(statsUrl),
  api.get<Trade[]>('/trades/')
]);
setStats(statsData);
```

with:

```typescript
const [statsData, tradesData, liveUnrealizedData] = await Promise.all([
  api.get<DashboardData>(statsUrl),
  api.get<Trade[]>('/trades/'),
  api.get<Array<{ trade_id: number; unrealized_pnl: number }>>('/trades/unrealized-pnl')
    .catch((e) => { console.warn('live unrealized fetch failed, using stats snapshot', e); return [] as Array<{ trade_id: number; unrealized_pnl: number }>; }),
]);
setStats(statsData);
const sumLive = Array.isArray(liveUnrealizedData)
  ? liveUnrealizedData.reduce((s, t) => s + (t.unrealized_pnl || 0), 0)
  : 0;
setLiveUnrealizedSum(Array.isArray(liveUnrealizedData) && liveUnrealizedData.length > 0 ? sumLive : null);
```

- [ ] **Step 3: Pass prop into StatsGrid**

In `frontend/src/app/page.tsx`, find the `<StatsGrid ... />` JSX (search for `<StatsGrid`). Add prop:

```tsx
<StatsGrid
  stats={stats}
  liveUnrealizedSum={liveUnrealizedSum}
  ...existing props...
/>
```

In `frontend/src/components/dashboard/StatsGrid.tsx`, find the `Props` interface or function signature. Add to props type:

```typescript
liveUnrealizedSum?: number | null;
```

And in component arguments destructuring add `liveUnrealizedSum`.

- [ ] **Step 4: Override headline display with live unrealized**

In `frontend/src/components/dashboard/StatsGrid.tsx`, find (around line 129-135):

```typescript
const displayTotalPnl = isGross ? stats?.total_pnl_gross : stats?.total_pnl;
const displayTotalPnlWithUnrealized = isGross
  ? stats?.total_pnl_with_unrealized_gross
  : stats?.total_pnl_with_unrealized;
const displayAdjustments = isGross
  ? stats?.account_level_adjustments_gross
  : stats?.account_level_adjustments;
```

Replace with:

```typescript
const displayTotalPnl = isGross ? stats?.total_pnl_gross : stats?.total_pnl;
// Phase 6.4: live override headline if /trades/unrealized-pnl available.
// Headline = realized + live_unrealized (matches Дневник сделок).
// Fallback: stats.total_pnl_with_unrealized (= realized + snapshot unrealized).
const headlineUnrealized = (liveUnrealizedSum !== null && liveUnrealizedSum !== undefined)
  ? liveUnrealizedSum
  : (stats?.unrealized_pnl ?? 0);
const displayTotalPnlWithUnrealized = (displayTotalPnl ?? 0) + headlineUnrealized;
const displayAdjustments = isGross
  ? stats?.account_level_adjustments_gross
  : stats?.account_level_adjustments;
```

- [ ] **Step 5: Update "Нереализ." subtitle to use live value**

In `StatsGrid.tsx` find (around line 190-191):

```typescript
if (stats?.unrealized_pnl && stats.unrealized_pnl !== 0) {
  parts.push(`Нереализ.: ${formatCurrency(stats.unrealized_pnl)}`);
}
```

Replace with:

```typescript
if (headlineUnrealized !== 0) {
  parts.push(`Нереализ.: ${formatCurrency(headlineUnrealized)}`);
}
```

- [ ] **Step 6: Manual smoke test in browser**

Run: `cd frontend && npm run dev` (если ещё не запущен)

1. Open http://127.0.0.1:3000/ in browser logged in as user_id=2 (acc#4)
2. Check headline "Общий PnL" — должно быть ~−247,914 ₽ (realized −174,421 + unrealized ~−73,492)
3. Open http://127.0.0.1:3000/history — total на странице должен быть тем же числом ± несколько ₽ jitter (live MOEX move)
4. PnLHealthBadge сверху должен показывать `ok` со значением около 0.21%

- [ ] **Step 7: Commit**

```bash
cd C:/Users/Administrator/Empirik/ATOM
git add frontend/src/app/page.tsx frontend/src/components/dashboard/StatsGrid.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): live unrealized override for headline

Dashboard теперь делает parallel fetch /trades/unrealized-pnl и override'ит
headline на live MOEX prices. Headline матчит Дневник сделок ± несколько ₽.
Fallback на stats.unrealized_pnl при сетевой ошибке.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Verification & sanity check

- [ ] **Step 1: Run full unit test suite**

Run: `cd backend && python -X utf8 -m pytest tests/unit/ -q`

Expected: все green (470+).

- [ ] **Step 2: Run integration test suite for stats**

Run: `cd backend && python -X utf8 -m pytest tests/integration/ tests/test_api.py -k "stats or pnl" -q`

Expected: все green.

- [ ] **Step 3: Run DB sanity check — verify /stats response shape on acc#4**

Run:

```bash
cd C:/Users/Administrator/Empirik/ATOM/backend && python -X utf8 -c "
import database, models
from domain.pnl.dashboard_pnl import compute_pnl_headline
from domain.pnl.cash_flow_classification import CashFlowCategory, operation_types_in
from sqlalchemy import func
from decimal import Decimal

s = database.SessionLocal()
account_id = 4
account = s.get(models.Account, account_id)

def _sum(cat):
    types = tuple(operation_types_in(cat))
    if not types: return 0.0
    row = s.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.operation_type.in_(types),
        models.OperationORM.state == 'executed',
    ).one()
    return float(row[0] or 0) + float(row[1] or 0) / 1e9

total_pnl = float(s.query(func.coalesce(func.sum(models.Trade.net_pnl), 0)).filter(models.Trade.account_id==account_id, models.Trade.exit_at.isnot(None)).scalar() or 0)
total_pnl_gross = float(s.query(func.coalesce(func.sum(models.Trade.pnl), 0)).filter(models.Trade.account_id==account_id, models.Trade.exit_at.isnot(None)).scalar() or 0)
unrealized = float(s.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0)).filter(models.PositionORM.account_id==account_id).scalar() or 0)

h = compute_pnl_headline(
    realized_closed=Decimal(str(total_pnl)),
    realized_closed_gross=Decimal(str(total_pnl_gross)),
    unrealized_position_based=Decimal(str(unrealized)),
    last_portfolio_value=Decimal(str(float(account.last_portfolio_value or 0))),
    net_deposits=Decimal(str(_sum(CashFlowCategory.NET_DEPOSIT))),
    broker_commission_raw=Decimal(str(_sum(CashFlowCategory.BROKER_COMMISSION))),
    attributable_fee_raw=Decimal(str(_sum(CashFlowCategory.ATTRIBUTABLE_FEE))),
    tax_raw=Decimal(str(_sum(CashFlowCategory.TAX))),
    income_tax_raw=Decimal(str(_sum(CashFlowCategory.INCOME_TAX))),
)
print(f'=== Phase 6.4 на acc#{account_id} ===')
print(f'  Headline (journal):       {float(h[\"total_pnl_with_unrealized\"]):>14,.2f} RUB')
print(f'  Realized closed:          {total_pnl:>14,.2f} RUB')
print(f'  Unrealized (position):    {unrealized:>14,.2f} RUB')
print(f'  cash_truth_pnl (broker):  {float(h[\"cash_truth_pnl\"]):>14,.2f} RUB')
print(f'  natural_residual:         {float(h[\"natural_residual\"]):>14,.2f} RUB')
print(f'  total_costs:              {float(h[\"total_costs\"]):>14,.2f} RUB')
s.close()
"
```

Expected output (примерные числа для acc#4):

```
Headline (journal):       -247,914.56 RUB
Realized closed:          -174,421.80 RUB
Unrealized (position):     -73,492.76 RUB
cash_truth_pnl (broker):  -248,587.57 RUB
natural_residual:              -673.01 RUB
total_costs:              -108,089.90 RUB
```

- [ ] **Step 4: Restart backend to pick up new code**

Run in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-Sleep -Seconds 2
```

Then в Bash:

```bash
cd C:/Users/Administrator/Empirik/ATOM/backend && python -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000 > backend.out.log 2> backend.err.log &
```

Wait for backend ready:

```bash
until curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; do sleep 1; done; echo "backend ready"
```

- [ ] **Step 5: Visual smoke test on dashboard**

1. Open browser http://127.0.0.1:3000/ (frontend already running)
2. Force refresh (Ctrl+Shift+R)
3. Verify:
   - Headline "Общий PnL" ≈ −247,914 RUB
   - Open /history — Total там тот же ± несколько ₽
   - PnLHealthBadge: `ok` со значением ~0.21–0.5%
   - Карточка "Расходы" если есть — ≈ −108,090 ₽
   - Equity curve последняя точка совпадает с headline

- [ ] **Step 6: Mark complete**

Tests green + visual sanity check OK = задача закрыта.

---

## Acceptance criteria (from spec)

- [x] `/stats` response содержит `cash_truth_pnl` поле + `total_pnl_with_unrealized = total_pnl + unrealized_pnl`. (Task 2)
- [x] Unit-тесты `test_dashboard_pnl_headline.py` зелёные (новая семантика). (Task 1)
- [x] `test_pnl_health.py` без regression'а (15/15 passing). (Task 4 Step 1)
- [x] Frontend dashboard headline визуально совпадает с Journal page total ± 0.1% jitter. (Task 3 Step 6, Task 4 Step 5)
- [x] PnLHealthBadge показывает `ok` со значением 0.1–0.5%. (Task 4 Step 5)
- [x] `/trades/unrealized-pnl` failure → graceful fallback на position-based. (Task 3 Step 2 `.catch`)

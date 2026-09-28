# Costs Breakdown Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать карточку «Расходы» на дашборде структурированной (4 строки разбивки + hint «Уже включены в Общий PnL»), и убрать визуальный double-count «Расходов» из subtitle карточки «Общий PnL».

**Architecture:** Backend: расширить `total_costs_breakdown` с 3 на 4 ключа (broker_commission, margin_fees, service_fees, taxes), реюзая existing constants из `fee_attribution.py`. Frontend: новый компонент `CostsBreakdownCard` вместо inline `StatsCard`, плюс удаление перцептивных дублей из subtitle/tooltip соседней карточки. P&L расчёты не меняются.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (backend), Next.js 16 + React 19 + Tailwind + lucide-react (frontend), pytest (backend tests).

**Spec:** `docs/superpowers/specs/2026-05-18-costs-breakdown-design.md`

---

### Task 1: Экспорт constants из fee_attribution

**Files:**
- Modify: `backend/domain/pnl/fee_attribution.py:86-102`

- [ ] **Step 1: Переименовать `_MARGIN_LIKE_FEE_TYPES` → `MARGIN_LIKE_FEE_TYPES` и `_SERVICE_LIKE_FEE_TYPES` → `SERVICE_LIKE_FEE_TYPES`**

Удалить ведущие подчёркивания для public-export. Это affects:
- Definition (строки 86-102)
- Usage в `_attributable_fee_column` (строки 107-110)

После изменения:
```python
MARGIN_LIKE_FEE_TYPES = frozenset({
    "margin_fee",
    "overnight",
    "over_com",
})

SERVICE_LIKE_FEE_TYPES = frozenset({
    "service_fee",
    "track_mfee",
    "track_pfee",
    "success_fee",
    "cash_fee",
    "out_fee",
    "out_stamp_duty",
    "output_penalty",
    "advice_fee",
})


def _attributable_fee_column(op_type: str) -> str:
    if op_type in MARGIN_LIKE_FEE_TYPES:
        return "margin_fee"
    if op_type in SERVICE_LIKE_FEE_TYPES:
        return "service_fee"
    return "other"
```

- [ ] **Step 2: Запустить существующие тесты fee_attribution убедиться что rename не сломал ничего**

Run: `cd backend && python -m pytest tests/unit/test_fee_attribution.py -v 2>&1 | tail -20`
Expected: всё PASS (только rename internal use, semantics не меняется).

- [ ] **Step 3: Поиск других usage сторон**

Run: `cd backend && grep -rn "_MARGIN_LIKE_FEE_TYPES\|_SERVICE_LIKE_FEE_TYPES" --include="*.py" .`
Expected: пусто (только определения уже переименованы).

Если найдены упоминания — обновить.

- [ ] **Step 4: Commit**

```bash
cd C:/Users/Administrator/Empirik/ATOM
git add backend/domain/pnl/fee_attribution.py
git commit -m "refactor: export MARGIN_LIKE_FEE_TYPES/SERVICE_LIKE_FEE_TYPES from fee_attribution

Готовим к реюзу в routers/stats.py для гранулярного costs breakdown.
Удаляем ведущее подчёркивание (private convention)."
```

---

### Task 2: TDD — disjoint invariant (MARGIN ∩ SERVICE = ∅)

**Files:**
- Create: `backend/tests/unit/test_costs_breakdown.py`

- [ ] **Step 1: Написать failing test**

```python
"""Unit tests для costs breakdown — disjoint и coverage invariants."""
from __future__ import annotations

from domain.pnl.cash_flow_classification import (
    CashFlowCategory,
    operation_types_in,
)
from domain.pnl.fee_attribution import (
    MARGIN_LIKE_FEE_TYPES,
    SERVICE_LIKE_FEE_TYPES,
)


def test_margin_and_service_fee_sets_are_disjoint():
    """MARGIN и SERVICE наборы не пересекаются — каждый op_type в ровно одно ведро."""
    overlap = MARGIN_LIKE_FEE_TYPES & SERVICE_LIKE_FEE_TYPES
    assert not overlap, (
        f"OperationType присутствует в обоих множествах: {overlap}. "
        f"Это сломает costs breakdown — будет double-count в стороне overlap."
    )
```

- [ ] **Step 2: Запустить тест — ожидаем PASS (рефакторинг Task 1 уже корректный)**

Run: `cd backend && python -m pytest tests/unit/test_costs_breakdown.py::test_margin_and_service_fee_sets_are_disjoint -v 2>&1 | tail -10`
Expected: PASS — invariant держится после Task 1.

(Этот тест не "failing-then-fixing" — это invariant lock-in. Он защищает от регрессии если кто-то добавит op_type в оба set'а.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_costs_breakdown.py
git commit -m "test: lock disjoint invariant for MARGIN/SERVICE fee sets"
```

---

### Task 3: TDD — coverage invariant (все ATTRIBUTABLE_FEE op_types в одном из бакетов)

**Files:**
- Modify: `backend/tests/unit/test_costs_breakdown.py` (добавить второй тест)

- [ ] **Step 1: Добавить тест в файл**

```python
def test_all_attributable_fees_covered_by_margin_or_service():
    """Все op_types в категории ATTRIBUTABLE_FEE должны попадать в margin OR service.

    Если Тинькофф добавит новый OperationType (например, premium_fee) и
    положит его в ATTRIBUTABLE_FEE category, но забудет добавить либо в
    MARGIN_LIKE_FEE_TYPES либо в SERVICE_LIKE_FEE_TYPES — этот тест упадёт
    на CI, и costs breakdown в дашборде потеряет этот тип.
    """
    attributable = operation_types_in(CashFlowCategory.ATTRIBUTABLE_FEE)
    covered = MARGIN_LIKE_FEE_TYPES | SERVICE_LIKE_FEE_TYPES
    missing = attributable - covered
    assert not missing, (
        f"OperationType в ATTRIBUTABLE_FEE без бакета: {missing}. "
        f"Добавь либо в MARGIN_LIKE_FEE_TYPES либо в SERVICE_LIKE_FEE_TYPES "
        f"в backend/domain/pnl/fee_attribution.py."
    )
```

- [ ] **Step 2: Запустить тест**

Run: `cd backend && python -m pytest tests/unit/test_costs_breakdown.py::test_all_attributable_fees_covered_by_margin_or_service -v 2>&1 | tail -10`
Expected: PASS (текущая система уже полностью покрывает).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_costs_breakdown.py
git commit -m "test: lock coverage invariant for ATTRIBUTABLE_FEE op_types"
```

---

### Task 4: Backend — расширить `total_costs_breakdown` в stats.py

**Files:**
- Modify: `backend/routers/stats.py:540-591`

- [ ] **Step 1: Добавить хелпер `_sum_op_types` и константы импорт**

В is_broker_user блоке после определения `_sum_category` (строки 540-552) добавить:

```python
from domain.pnl.fee_attribution import (
    MARGIN_LIKE_FEE_TYPES,
    SERVICE_LIKE_FEE_TYPES,
)

def _sum_op_types(op_types: frozenset[str]) -> float:
    """Сумма payment по конкретным OperationType.value (для подкатегорий
    внутри ATTRIBUTABLE_FEE — margin vs service)."""
    if not op_types:
        return 0.0
    row = db.query(
        func.coalesce(func.sum(OperationORM.payment_units), 0),
        func.coalesce(func.sum(OperationORM.payment_nano), 0),
    ).filter(
        OperationORM.account_id == account_id,
        OperationORM.operation_type.in_(tuple(op_types)),
        OperationORM.state == "executed",
    ).one()
    return float(row[0] or 0) + float(row[1] or 0) / 1e9
```

- [ ] **Step 2: Посчитать raw_margin и raw_service**

После строки `raw_attr_fee = _sum_category(CashFlowCategory.ATTRIBUTABLE_FEE)` добавить:

```python
raw_margin  = _sum_op_types(MARGIN_LIKE_FEE_TYPES)
raw_service = _sum_op_types(SERVICE_LIKE_FEE_TYPES)
```

- [ ] **Step 3: Заменить `total_costs_breakdown` dict (строки 587-591)**

Старое:
```python
total_costs_breakdown = {
    "broker_commission": float(raw_broker),
    "attributed_fees":   float(raw_attr_fee),
    "taxes":             float(raw_tax + raw_income_tax),
}
```

Новое:
```python
total_costs_breakdown = {
    "broker_commission": float(raw_broker),
    "margin_fees":       float(raw_margin),
    "service_fees":      float(raw_service),
    "taxes":             float(raw_tax + raw_income_tax),
}
```

- [ ] **Step 4: Обновить else-ветку (не-broker user, строки 600-604)**

```python
total_costs_breakdown = {
    "broker_commission": 0.0,
    "margin_fees":       0.0,
    "service_fees":      0.0,
    "taxes":             0.0,
}
```

- [ ] **Step 5: Sanity check — запустить весь pytest**

Run: `cd backend && python -m pytest -x --tb=short 2>&1 | tail -20`
Expected: всё зелёное (никаких regression).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/stats.py
git commit -m "feat(stats): расширить total_costs_breakdown на 4 категории

Старое:  broker_commission / attributed_fees / taxes
Новое:   broker_commission / margin_fees / service_fees / taxes

Реюзим MARGIN_LIKE_FEE_TYPES + SERVICE_LIKE_FEE_TYPES из fee_attribution.py."
```

---

### Task 5: TDD — integration test что breakdown суммируется в total_costs

**Files:**
- Modify: `backend/tests/unit/test_costs_breakdown.py` (добавить третий тест)

- [ ] **Step 1: Добавить integration test**

```python
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from domain.pnl.cash_flow_classification import operation_types_in, CashFlowCategory


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _add_op(session, account_id: int, op_type: str, units: int):
    """Helper: добавить одну OperationORM с payment_units."""
    op = models.OperationORM(
        operation_id=f"op-{op_type}-{units}",
        account_id=account_id,
        operation_type=op_type,
        payment_units=units,
        payment_nano=0,
        commission_units=0,
        commission_nano=0,
        price_units=0,
        price_nano=0,
        quantity=0,
        state="executed",
        executed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        currency="rub",
    )
    session.add(op)


def test_breakdown_sums_match_total_costs_categories(db_session):
    """Σ(broker + margin + service + taxes) равно raw category totals.

    Защищает что добавление новых op_types в категории не уйдёт мимо breakdown.
    """
    aid = 99
    # broker
    _add_op(db_session, aid, "broker_fee", -100)
    # margin
    _add_op(db_session, aid, "margin_fee", -50)
    _add_op(db_session, aid, "overnight",  -10)
    _add_op(db_session, aid, "over_com",   -5)
    # service
    _add_op(db_session, aid, "service_fee",  -30)
    _add_op(db_session, aid, "track_mfee",   -20)
    _add_op(db_session, aid, "success_fee",  -15)
    # tax
    _add_op(db_session, aid, "tax",          -7)
    _add_op(db_session, aid, "dividend_tax", -3)
    db_session.commit()

    from sqlalchemy import func
    from domain.pnl.fee_attribution import (
        MARGIN_LIKE_FEE_TYPES,
        SERVICE_LIKE_FEE_TYPES,
    )

    def _sum(op_types):
        row = db_session.query(
            func.coalesce(func.sum(models.OperationORM.payment_units), 0),
            func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
        ).filter(
            models.OperationORM.account_id == aid,
            models.OperationORM.operation_type.in_(tuple(op_types)),
            models.OperationORM.state == "executed",
        ).one()
        return float(row[0] or 0) + float(row[1] or 0) / 1e9

    raw_broker  = _sum(operation_types_in(CashFlowCategory.BROKER_COMMISSION))
    raw_margin  = _sum(MARGIN_LIKE_FEE_TYPES)
    raw_service = _sum(SERVICE_LIKE_FEE_TYPES)
    raw_tax     = _sum(operation_types_in(CashFlowCategory.TAX))
    raw_inctax  = _sum(operation_types_in(CashFlowCategory.INCOME_TAX))
    raw_attr    = _sum(operation_types_in(CashFlowCategory.ATTRIBUTABLE_FEE))

    # Инвариант 1: margin + service == raw_attr (вся ATTRIBUTABLE_FEE покрыта)
    assert abs((raw_margin + raw_service) - raw_attr) < 0.01, (
        f"margin={raw_margin} + service={raw_service} != attr={raw_attr}"
    )

    # Инвариант 2: суммы выставлены правильно (seed corresponds expectations)
    assert raw_broker  == -100
    assert raw_margin  == -65   # 50 + 10 + 5
    assert raw_service == -65   # 30 + 20 + 15
    assert raw_tax     == -7
    assert raw_inctax  == -3
```

- [ ] **Step 2: Запустить тест**

Run: `cd backend && python -m pytest tests/unit/test_costs_breakdown.py -v 2>&1 | tail -15`
Expected: все 3 теста PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_costs_breakdown.py
git commit -m "test: integration test для breakdown категорий через SQLite

Подтверждает что margin + service = вся ATTRIBUTABLE_FEE и суммы соответствуют seed'у."
```

---

### Task 6: Обновить Pydantic schema DashboardStats

**Files:**
- Modify: `backend/schemas.py`

- [ ] **Step 1: Найти DashboardStats**

Run: `cd backend && grep -n "total_costs_breakdown" schemas.py`

Если breakdown типизирован как TypedDict / nested schema — обновить. Если как `dict[str, float]` — нужно только обновить default value (если он есть).

- [ ] **Step 2: Привести структуру к 4 ключам**

Если найдена nested-схема `TotalCostsBreakdown`:
```python
class TotalCostsBreakdown(BaseModel):
    broker_commission: float = 0.0
    margin_fees:       float = 0.0
    service_fees:      float = 0.0
    taxes:             float = 0.0
```

Если просто `dict[str, float]` без явного типа — менять только default value у `DashboardStats.total_costs_breakdown`:
```python
total_costs_breakdown: dict[str, float] = Field(
    default_factory=lambda: {
        "broker_commission": 0.0,
        "margin_fees":       0.0,
        "service_fees":      0.0,
        "taxes":             0.0,
    }
)
```

- [ ] **Step 3: Запустить тесты + mypy если есть**

Run: `cd backend && python -m pytest -x --tb=short 2>&1 | tail -10`
Expected: всё зелёное.

Run: `cd backend && python -m mypy . 2>&1 | tail -10` (если mypy настроен)

- [ ] **Step 4: Commit**

```bash
git add backend/schemas.py
git commit -m "feat(schemas): расширить DashboardStats.total_costs_breakdown на 4 ключа"
```

---

### Task 7: Frontend — создать `CostsBreakdownCard` компонент

**Files:**
- Create: `frontend/src/components/dashboard/CostsBreakdownCard.tsx`

- [ ] **Step 1: Создать файл с компонентом**

```tsx
"use client";

/**
 * CostsBreakdownCard — отдельная плитка дашборда для расходов с разбивкой.
 *
 * Visual goal: одна большая сумма + 4 строки разбивки (брокер/маржа/сервис/налоги)
 * + явный hint снизу что «уже включены в Общий PnL» — это убирает перцептивный
 * двойной учёт. Расчёт P&L это число НЕ ПРИБАВЛЯЕТ — оно visualisation only.
 */
import { Info, Receipt } from "lucide-react";

interface Breakdown {
  broker_commission?: number;
  margin_fees?: number;
  service_fees?: number;
  taxes?: number;
}

interface Props {
  total: number;
  breakdown: Breakdown;
  formatCurrency: (n: number) => string;
}

export function CostsBreakdownCard({ total, breakdown, formatCurrency }: Props) {
  const rows: Array<{ label: string; value: number | undefined }> = [
    { label: "Брокер", value: breakdown.broker_commission },
    { label: "Маржа",  value: breakdown.margin_fees },
    { label: "Сервис", value: breakdown.service_fees },
    { label: "Налоги", value: breakdown.taxes },
  ];

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5 flex flex-col">
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-[13px] font-medium text-[var(--text-secondary)]">Расходы</h3>
        <Receipt size={18} className="text-[var(--text-tertiary)]" />
      </div>

      {/* Big number */}
      <div className="text-[22px] font-semibold tabular-nums text-[var(--danger)] mb-4">
        {formatCurrency(total)}
      </div>

      {/* Breakdown rows */}
      <div className="space-y-1.5 border-t border-[var(--border)] pt-3 flex-1">
        {rows.map(({ label, value }) =>
          !value || Math.abs(value) < 1 ? null : (
            <div key={label} className="flex justify-between text-[13px]">
              <span className="text-[var(--text-secondary)]">{label}</span>
              <span className="tabular-nums font-medium">{formatCurrency(value)}</span>
            </div>
          ),
        )}
      </div>

      {/* Hint */}
      <div className="mt-3 pt-3 border-t border-[var(--border)] flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)]">
        <Info size={12} />
        <span>Уже включены в Общий PnL</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Проверка TypeScript-компиляции**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -10`
Expected: нет ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/CostsBreakdownCard.tsx
git commit -m "feat(dashboard): новый компонент CostsBreakdownCard с 4 строками разбивки"
```

---

### Task 8: Frontend — обновить TypeScript interface в StatsGrid

**Files:**
- Modify: `frontend/src/components/dashboard/StatsGrid.tsx:46-50`

- [ ] **Step 1: Заменить определение `total_costs_breakdown`**

Старое:
```ts
total_costs_breakdown?: {
  broker_commission?: number;
  attributed_fees?: number;
  taxes?: number;
};
```

Новое:
```ts
total_costs_breakdown?: {
  broker_commission?: number;
  margin_fees?: number;
  service_fees?: number;
  taxes?: number;
};
```

- [ ] **Step 2: TypeScript проверка**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -15`
Expected: появятся ошибки в местах, где использовался `attributed_fees` (строки 245-247 и 262-263).

- [ ] **Step 3: Commit с временно-сломанным TS — продолжим в Task 9-10**

(Не коммитим пока — продолжим в следующих задачах. Помечаем шаг ✅ только когда дошли до Task 10.)

---

### Task 9: Frontend — удалить «Расходы» из subtitle и tooltip карточки PnL

**Files:**
- Modify: `frontend/src/components/dashboard/StatsGrid.tsx:203-205, 226-228`

- [ ] **Step 1: Удалить блок из subtitle (строки 203-205)**

Удалить:
```tsx
if (!isGross && stats?.total_costs && Math.abs(stats.total_costs) > 1) {
  parts.push(`Расходы: ${formatCurrency(stats.total_costs)}`);
}
```

- [ ] **Step 2: Удалить блок из tooltip (строки 226-228)**

Удалить:
```tsx
if (!isGross && stats?.total_costs && Math.abs(stats.total_costs) > 1) {
  lines.push(`Комиссии, сборы и налоги: ${formatCurrency(stats.total_costs)}`);
}
```

- [ ] **Step 3: Обновить comment на строке 191-192 (опционально, но красиво)**

Старое:
```tsx
// Phase 12: subtitle отражает компоненты headline.
//   net   = Реализ. body + Нереализ. + Прочие + Расходы
//   gross = Реализ. body + Нереализ. + Прочие (без Расходов)
```

Новое:
```tsx
// Subtitle = компоненты headline. Расходы НЕ показываем здесь:
// в net-режиме они уже зашиты в displayTotalPnl через Trade.net_pnl,
// и параллельная строка «Расходы» читается как visual double-count.
// Отдельная карточка <CostsBreakdownCard /> ниже даёт разбивку расходов.
```

- [ ] **Step 4: Commit (отложим до Task 10 — TS будет сломан)**

(Не коммитим — продолжаем в Task 10.)

---

### Task 10: Frontend — заменить inline StatsCard на CostsBreakdownCard

**Files:**
- Modify: `frontend/src/components/dashboard/StatsGrid.tsx:1-6, 235-274`

- [ ] **Step 1: Добавить импорт компонента наверху файла (строка ~6)**

После строки `import { StatsCard } from '@/components/StatsCard';`:
```tsx
import { CostsBreakdownCard } from '@/components/dashboard/CostsBreakdownCard';
```

- [ ] **Step 2: Удалить ненужный импорт `Receipt`**

Из строки 4-5:
```tsx
import { Activity, TrendingUp, TrendingDown, Target, Zap, AlertTriangle,
         GitGraph, BarChart3, Flame, Scale, Shield, Wallet, Gauge, Receipt } from 'lucide-react';
```

Удалить `Receipt` (он теперь только в `CostsBreakdownCard`).

- [ ] **Step 3: Заменить блок Phase 12 StatsCard (строки 235-274)**

Старый блок (целиком, со всеми тултипами):
```tsx
{hasData && stats?.total_costs !== undefined && stats.total_costs !== 0 && (
  <StatsCard
    title="Расходы"
    value={formatStatCurrency(stats.total_costs)}
    description={...}
    trend={...}
    icon={<Receipt size={18} />}
    tooltipText={...}
    manualAnchor="total-costs"
  />
)}
```

Заменить на:
```tsx
{hasData && stats?.total_costs !== undefined && stats.total_costs !== 0 && (
  <CostsBreakdownCard
    total={stats.total_costs}
    breakdown={stats.total_costs_breakdown ?? {}}
    formatCurrency={formatCurrency}
  />
)}
```

- [ ] **Step 4: TypeScript полная проверка**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -15`
Expected: нет ошибок.

- [ ] **Step 5: ESLint**

Run: `cd frontend && npx eslint src/components/dashboard/ 2>&1 | tail -10`
Expected: нет ошибок (warnings ОК).

- [ ] **Step 6: Commit все frontend-изменения вместе (Tasks 8-10)**

```bash
git add frontend/src/components/dashboard/StatsGrid.tsx
git commit -m "feat(dashboard): подключить CostsBreakdownCard, убрать double-count из subtitle

- StatsGrid.tsx: total_costs_breakdown interface обновлён под 4 ключа
- Удалены строки 'Расходы' из subtitle и tooltip карточки 'Общий PnL'
  (они уже учтены в Trade.net_pnl — параллельная строка читалась как
  visual double-count)
- Inline StatsCard 'Расходы' заменён на <CostsBreakdownCard /> с разбивкой
  Брокер/Маржа/Сервис/Налоги + hint 'Уже включены в Общий PnL'"
```

---

### Task 11: Smoke check в браузере

**Files:** (none — manual verification)

- [ ] **Step 1: Запустить backend + frontend**

Run в одном терминале:
```bash
cd backend && python -m uvicorn main:app --reload --port 8000
```

В другом:
```bash
cd frontend && npm run dev
```

- [ ] **Step 2: Открыть http://localhost:3000, войти под sarvanidi87@gmail.com**

Залогиниться → перейти на дашборд (acc#4).

- [ ] **Step 3: Визуальная проверка карточки «Общий PnL»**

Ожидаемо:
- Headline сумма: −247k (без изменений)
- Subtitle: `Реализ.: −174k | Нереализ.: −73k | Прочие: −6k` (БЕЗ строки «Расходы»)
- Tooltip — то же самое (без строки про комиссии)

- [ ] **Step 4: Визуальная проверка карточки «Расходы»**

Ожидаемо:
- Заголовок «Расходы» + иконка Receipt
- Большая сумма −110,656 ₽
- 4 строки:
  - Брокер: −56,773 ₽
  - Маржа: −46,529 ₽ (margin_fee + overnight + over_com)
  - Сервис: −2,040 ₽
  - Налоги: −156 ₽
- Снизу: иконка Info + «Уже включены в Общий PnL»

- [ ] **Step 5: Проверка console на ошибки**

DevTools → Console → не должно быть красных errors.

- [ ] **Step 6: Если всё ОК — финальный commit-tag**

```bash
git log --oneline -10
```

Если что-то выглядит криво — фикс инлайн, отдельный commit с описанием. Не амендим предыдущие.

---

## Self-Review

**1. Spec coverage:**

| Spec секция | Task |
|---|---|
| Backend: расширить total_costs_breakdown | Task 4 |
| Реюз `_MARGIN_LIKE_FEE_TYPES` через export | Task 1 |
| `schemas.py: DashboardStats` обновить | Task 6 |
| `CostsBreakdownCard.tsx` новый компонент | Task 7 |
| TypeScript interface в StatsGrid | Task 8 |
| Удалить subtitle/tooltip строки «Расходы» | Task 9 |
| Заменить inline StatsCard | Task 10 |
| Тесты: no_overlap, coverage, sums_match | Tasks 2, 3, 5 |
| Manual smoke check | Task 11 |

Все секции spec покрыты.

**2. Placeholder scan:**

- Нет "TBD" / "TODO" / "implement later"
- Все шаги содержат actual code или actual command
- Команды все с expected output

**3. Type consistency:**

- `MARGIN_LIKE_FEE_TYPES` и `SERVICE_LIKE_FEE_TYPES` (без подчёркивания) консистентно в Task 1, 2, 3, 4, 5.
- Ключи `broker_commission` / `margin_fees` / `service_fees` / `taxes` — одинаковые в backend (Task 4) и frontend (Tasks 7, 8).
- Имя компонента `CostsBreakdownCard` — одинаковое в Task 7 (create) и Task 10 (import).
- Имя файла теста `test_costs_breakdown.py` — одинаковое в Tasks 2, 3, 5.

Всё консистентно.

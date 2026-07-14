# Costs Breakdown Card — design

**Дата:** 2026-05-18
**Автор:** sarvanidi87
**Контекст:** dashboard P&L UI

## Проблема

Пользователь видит на дашборде карточку «Расходы: −110,656 ₽», а в subtitle карточки «Общий PnL» одновременно строки:

```
Реализ.: −174,421 | Нереализ.: −72,942 | Прочие: −5,526 | Расходы: −110,656
```

Это создаёт впечатление **двойного учёта расходов**: «Реализ.» уже включает все commission/fees/taxes через `Trade.net_pnl`, а отдельная строка «Расходы» рядом читается как дополнительное слагаемое. Если их визуально просуммировать → −363k, но headline показывает −247k. Несостыковка путает пользователя.

Параллельно — текущая разбивка `total_costs_breakdown` в API имеет всего 3 ключа (`broker_commission`, `attributed_fees`, `taxes`), где `attributed_fees` смешивает в одну кучу margin/overnight + service/track/success/out. Для торгового анализа это недостаточно гранулярно.

## Заметка про P&L расчёт

**На уровне расчётов double-count нет.** Trade.commission_total берётся из inline `op.commission` BUY/SELL операций. `fee_attribution.attribute_fees()` явно исключает `BROKER_COMMISSION` категорию. Trade.net_pnl содержит commission один раз. Headline `total_pnl_with_unrealized = realized + unrealized` — корректен.

Tinkoff API физически дублирует broker_fee в двух местах (inline в trade-operation + отдельная BROKER_FEE operation с `parent_operation_id`), но это устранено архитектурой: для journal-side используется inline, для reconciliation_service — standalone broker_fee (AU15 fix, см. `services/reconciliation_service.py:303-313`).

**Задача — только UI.** Сделать карточку расходов структурированной и убрать визуальный perception double-count из subtitle.

## Цель

1. Карточка «Расходы» на дашборде показывает **сумма + 4 строки разбивки внутри** (Брокер / Маржа / Сервис / Налоги) + явный hint «Уже включены в Общий PnL».
2. Subtitle карточки «Общий PnL» больше **не упоминает «Расходы»** — это убирает визуальный двойной учёт.
3. Гранулярность достаточна для торговой аналитики (отделить маржинальные сборы от сервисных — Tinkoff брокер vs Tinkoff Capital management).

Не меняем: расчёт P&L, FIFO matcher, attribute_fees, equity curve, PnLHealthBadge, Journal page.

## Архитектура

### Backend

#### Файл: `backend/routers/stats.py`

В is_broker_user ветке (около строк 540-591) — расширить `total_costs_breakdown`.

Сейчас:
```python
total_costs_breakdown = {
    "broker_commission": float(raw_broker),
    "attributed_fees":   float(raw_attr_fee),    # margin + service + overnight + ... всё вместе
    "taxes":             float(raw_tax + raw_income_tax),
}
```

После:
```python
from domain.pnl.fee_attribution import _MARGIN_LIKE_FEE_TYPES, _SERVICE_LIKE_FEE_TYPES

def _sum_op_types(op_types: frozenset[str]) -> float:
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

raw_margin  = _sum_op_types(_MARGIN_LIKE_FEE_TYPES)   # margin_fee, overnight, over_com
raw_service = _sum_op_types(_SERVICE_LIKE_FEE_TYPES)  # service_fee, track_mfee, track_pfee,
                                                       # success_fee, cash_fee, out_fee, out_stamp_duty,
                                                       # output_penalty, advice_fee

total_costs_breakdown = {
    "broker_commission": float(raw_broker),
    "margin_fees":       float(raw_margin),
    "service_fees":      float(raw_service),
    "taxes":             float(raw_tax + raw_income_tax),
}
```

Инвариант: `broker_commission + margin_fees + service_fees + taxes == total_costs` (с точностью до FP rounding).

#### Файл: `backend/domain/pnl/fee_attribution.py`

Экспортировать `_MARGIN_LIKE_FEE_TYPES` и `_SERVICE_LIKE_FEE_TYPES` — переименовать удалением подчёркивания → `MARGIN_LIKE_FEE_TYPES`, `SERVICE_LIKE_FEE_TYPES`. (Альтернатива: оставить с underscore и импортить как есть — Python это не блокирует, просто convention. Делаем без подчёркивания для чистого export.)

#### Файл: `backend/schemas.py`

Расширить `DashboardStats.total_costs_breakdown`:
```python
total_costs_breakdown: dict[str, float] = {
    "broker_commission": 0.0,
    "margin_fees":       0.0,
    "service_fees":      0.0,
    "taxes":             0.0,
}
```

### Frontend

#### Новый компонент: `frontend/src/components/dashboard/CostsBreakdownCard.tsx`

Кастомный, в визуальном стиле `StatsCard` (rounded-xl, border, bg-surface-1, padding p-5). Не использует `<StatsCard>` напрямую, потому что нужны sub-rows и hint-блок снизу — `StatsCard` для этого не приспособлен.

Структура:
```tsx
interface Props {
  total: number;
  breakdown: {
    broker_commission?: number;
    margin_fees?: number;
    service_fees?: number;
    taxes?: number;
  };
  formatCurrency: (n: number) => string;
}

<div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5">
  {/* Header: Title + Icon + Tooltip */}
  <div className="flex items-start justify-between mb-2">
    <h3 className="text-sm font-medium text-[var(--text-secondary)]">Расходы</h3>
    <Tooltip content="Все комиссии, сборы и налоги. Уже вычтены из P&L каждой сделки.">
      <Receipt size={18} className="text-[var(--text-tertiary)]" />
    </Tooltip>
  </div>

  {/* Big number */}
  <div className="text-2xl font-semibold tabular-nums text-[var(--danger)] mb-4">
    {formatCurrency(total)}
  </div>

  {/* Breakdown rows */}
  <div className="space-y-1.5 border-t border-[var(--border)] pt-3">
    <BreakdownRow label="Брокер"  value={breakdown.broker_commission} format={formatCurrency} />
    <BreakdownRow label="Маржа"   value={breakdown.margin_fees}       format={formatCurrency} />
    <BreakdownRow label="Сервис"  value={breakdown.service_fees}      format={formatCurrency} />
    <BreakdownRow label="Налоги"  value={breakdown.taxes}             format={formatCurrency} />
  </div>

  {/* Hint: уже включены */}
  <div className="mt-3 pt-3 border-t border-[var(--border)] flex items-center gap-1.5
                  text-[11px] text-[var(--text-tertiary)]">
    <Info size={12} />
    <span>Уже включены в Общий PnL</span>
  </div>
</div>
```

`BreakdownRow` — внутренний sub-component:
```tsx
function BreakdownRow({ label, value, format }) {
  if (!value || Math.abs(value) < 1) return null;  // не показывать нулевые
  return (
    <div className="flex justify-between text-[13px]">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="tabular-nums font-medium">{format(value)}</span>
    </div>
  );
}
```

Нулевые строки не показываются — пользователь не видит «Маржа 0 ₽» если у него не маржинальный счёт.

#### Изменения в `StatsGrid.tsx`

1. **TypeScript interface** — обновить `DashboardData.total_costs_breakdown` (строки 46-50):
   ```ts
   total_costs_breakdown?: {
     broker_commission?: number;
     margin_fees?: number;
     service_fees?: number;
     taxes?: number;
   };
   ```

2. **Удалить строку «Расходы» из subtitle карточки PnL** (строки 203-205):
   ```tsx
   // УДАЛЯЕМ:
   if (!isGross && stats?.total_costs && Math.abs(stats.total_costs) > 1) {
     parts.push(`Расходы: ${formatCurrency(stats.total_costs)}`);
   }
   ```

3. **Удалить строку «Комиссии, сборы и налоги» из tooltip** (строки 226-228):
   ```tsx
   // УДАЛЯЕМ:
   if (!isGross && stats?.total_costs && Math.abs(stats.total_costs) > 1) {
     lines.push(`Комиссии, сборы и налоги: ${formatCurrency(stats.total_costs)}`);
   }
   ```

4. **Заменить inline `<StatsCard title="Расходы" ...>`** (строки 235-274) на:
   ```tsx
   {hasData && stats?.total_costs !== undefined && stats.total_costs !== 0 && (
     <CostsBreakdownCard
       total={stats.total_costs}
       breakdown={stats.total_costs_breakdown ?? {}}
       formatCurrency={formatCurrency}
     />
   )}
   ```

### Поток данных

```
backend/routers/stats.py
  ├─ _sum_op_types(MARGIN_LIKE_FEE_TYPES)  ─┐
  ├─ _sum_op_types(SERVICE_LIKE_FEE_TYPES) ─┼─→ total_costs_breakdown (4 ключа)
  ├─ _sum_category(BROKER_COMMISSION)      ─┤
  └─ _sum_category(TAX) + INCOME_TAX       ─┘
        ↓
  Response JSON: total_costs_breakdown: {broker_commission, margin_fees, service_fees, taxes}
        ↓
frontend/page.tsx
        ↓
StatsGrid → CostsBreakdownCard (4 rows, hint снизу)
```

## Тесты

### Backend (TDD)

#### `backend/tests/unit/test_costs_breakdown.py` (новый)

1. **`test_no_overlap_between_margin_and_service`**
   ```python
   def test_no_overlap_between_margin_and_service():
       """Каждый OperationType в ATTRIBUTABLE_FEE попадает в РОВНО одно ведро."""
       from domain.pnl.fee_attribution import (
           MARGIN_LIKE_FEE_TYPES,
           SERVICE_LIKE_FEE_TYPES,
       )
       assert MARGIN_LIKE_FEE_TYPES.isdisjoint(SERVICE_LIKE_FEE_TYPES)
   ```

2. **`test_coverage_of_attributable_fees`**
   ```python
   def test_coverage_of_attributable_fees():
       """Все OperationType из ATTRIBUTABLE_FEE category покрыты margin OR service."""
       from domain.pnl.cash_flow_classification import (
           CashFlowCategory,
           operation_types_in,
       )
       from domain.pnl.fee_attribution import (
           MARGIN_LIKE_FEE_TYPES,
           SERVICE_LIKE_FEE_TYPES,
       )
       attributable = operation_types_in(CashFlowCategory.ATTRIBUTABLE_FEE)
       covered = MARGIN_LIKE_FEE_TYPES | SERVICE_LIKE_FEE_TYPES
       missing = attributable - covered
       assert not missing, (
           f"OperationType в ATTRIBUTABLE_FEE без бакета: {missing}. "
           f"Добавь либо в MARGIN_LIKE_FEE_TYPES либо в SERVICE_LIKE_FEE_TYPES."
       )
   ```

3. **`test_breakdown_sums_to_total_costs`**
   ```python
   def test_breakdown_sums_to_total_costs(db_session, broker_account):
       """broker + margin + service + taxes == total_costs (с точностью до FP)."""
       # Seed: несколько операций разных категорий
       # Call stats endpoint
       # Assert math holds
   ```

### Frontend

- Manual visual check после изменений: открыть `/dashboard` (acc#4), убедиться что:
  - Карточка «Расходы» показывает 4 строки с правильными суммами
  - Subtitle карточки PnL больше НЕ упоминает «Расходы»
  - Hint «Уже включены в Общий PnL» виден
- (Опционально) добавить snapshot тест для `CostsBreakdownCard` если есть jest setup. В текущем проекте frontend tests минимальны — пропускаем.

## План реализации (high-level)

1. Backend: переименовать `_MARGIN_LIKE_FEE_TYPES` → `MARGIN_LIKE_FEE_TYPES` (и service) в `fee_attribution.py`; внутренние usage обновить.
2. Backend: написать failing tests в `test_costs_breakdown.py`.
3. Backend: расширить `stats.py` breakdown с 3 на 4 ключа.
4. Backend: расширить `schemas.py`.
5. Backend: тесты зелёные, run pytest.
6. Frontend: создать `CostsBreakdownCard.tsx`.
7. Frontend: обновить `DashboardData` interface в `StatsGrid.tsx`.
8. Frontend: удалить строки «Расходы» из subtitle и tooltip карточки PnL.
9. Frontend: заменить inline StatsCard на `<CostsBreakdownCard />`.
10. Manual smoke check в браузере (acc#4).

## Риски и edge cases

- **Новый OperationType от Тинькофф в `ATTRIBUTABLE_FEE` без бакета** — тест `test_coverage_of_attributable_fees` упадёт на CI, разработчик добавит его в нужное множество. Защита от регрессии.
- **`total_costs_breakdown == 0` на старте счёта без операций** — `CostsBreakdownCard` рендерится только при `stats.total_costs !== 0`, иначе hidden (как сейчас).
- **Узкий экран** — карточка может стать высокой (~140-160px), но grid `md:grid-cols-2 lg:grid-cols-4` это переваривает. Никаких overflow проблем.
- **Backwards compatibility API** — поле `attributed_fees` исчезает из breakdown. Если кто-то на старом фронтенде это читает — увидит `undefined`. Production frontend деплоится синхронно с backend, поэтому ОК.

## Что НЕ в скоупе

- Отдельная страница `/costs` с timeline и breakdown по инструментам / месяцам — рассмотрим позже, если будет нужно.
- 8+ строк разбивки по каждому подтипу операции (track_mfee отдельно от track_pfee и т.д.) — пользователь выбрал 4 категории как достаточный уровень.
- Изменение headline P&L формулы — она уже корректна, расходы учтены один раз через `Trade.net_pnl`.
- Изменения в Дневнике сделок — там commission уже отображается корректно для каждой сделки.

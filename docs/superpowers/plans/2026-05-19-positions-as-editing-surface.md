# Positions = editing surface для open trades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Семантическое разделение UI: `/history` (журнал) показывает только closed Trade rows; `/positions` (Открытые позиции) становится editing surface для open Trade rows с expand-row → EditTradeModal flow.

**Architecture:** Backend без изменений — endpoint `GET /trades/positions?status=open|closed` уже поддерживает фильтрацию. На frontend `/history` явно фильтрует `?status=closed` и удаляет open-ветки из `PositionJournalView`. `/positions` параллельно тянет `/positions` (snapshot) + `/trades/positions?status=open`, join по `instrument_uid` на клиенте, expand row показывает executions и переиспользует existing `EditTradeModal`.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, Tailwind v4, lucide-react icons, native fetch через `@/lib/apiClient`. Backend: FastAPI + SQLAlchemy 2.0 (без изменений).

**Spec:** [docs/superpowers/specs/2026-05-19-positions-as-editing-surface-design.md](../specs/2026-05-19-positions-as-editing-surface-design.md)

---

## File Structure

**Create:**
- `frontend/src/app/positions/joinPositionsTrades.ts` — pure function для join Position[] × PositionTrade[] по `instrument_uid` (изолированная testable логика)
- `frontend/src/app/positions/OpenPositionExpand.tsx` — компонент expand-row для /positions (executions list + кнопка «Редактировать»)

**Modify:**
- `frontend/src/app/history/page.tsx` — fetch URL `?status=closed`
- `frontend/src/components/PositionJournalView.tsx` — удалить StatusBadge usage, isOpen ветки, italic-PnL, ExecutionList «Открытие/Закрытие» — упростить под «всё закрыто»
- `frontend/src/app/positions/page.tsx` — параллельный fetch, join, expand state, EditTradeModal integration
- `frontend/src/components/AppShell.tsx:85` — переименовать sidebar item

**Не трогаем:**
- `backend/routers/trades.py` — endpoint уже поддерживает фильтр
- `backend/schemas.py`, `models.py` — без изменений
- `frontend/src/components/EditTradeModal.tsx` — переиспользуем как есть
- Backend tests — coverage есть в `tests/integration/test_position_aggregation.py:184`

---

## Task 1: Журнал — фильтр `?status=closed`

**Files:**
- Modify: `frontend/src/app/history/page.tsx` (fetch URL)
- Test: backend coverage уже есть (test_position_aggregation.py:184); frontend smoke вручную

- [ ] **Step 1: Найти fetch к `/trades/positions` в history/page.tsx**

Найти строку с `api.get` и URL `/trades/positions`. В Eqio она может выглядеть как:

```ts
const data = await api.get<PositionTrade[]>('/trades/positions');
// или
const data = await api.get<PositionTrade[]>('/trades/positions?status=all');
```

Используй Grep:

```bash
grep -n "trades/positions" frontend/src/app/history/page.tsx
```

- [ ] **Step 2: Заменить URL на `?status=closed`**

Изменить fetch на:

```ts
const data = await api.get<PositionTrade[]>('/trades/positions?status=closed');
```

Если есть any other fetch'ы (например, для filter UI «Open / Closed / All» toggle) — удалить ту часть UI тоже. На /history больше нет open trades, фильтр не нужен.

- [ ] **Step 3: TypeScript check**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsc --noEmit
```

Expected: 0 errors. Если новые errors появились — это означает где-то ещё ссылка на open-status branch. Зафиксируй в Step 4 (PositionJournalView cleanup).

- [ ] **Step 4: Manual smoke check**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npm run dev
```

Открой http://localhost:3000/history. Expected:
- Видны только закрытые позиции (если у тебя в БД есть mix open + closed).
- StatusBadge всё ещё рендерится (это починим в Task 2).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/history/page.tsx
git commit -m "feat(history): фильтровать журнал только closed позициями"
```

---

## Task 2: PositionJournalView — удалить open-ветки

**Files:**
- Modify: `frontend/src/components/PositionJournalView.tsx` (удалить StatusBadge usage, isOpen branches, italic-PnL, «Открытие/Закрытие» в ExecutionList)

- [ ] **Step 1: Удалить StatusBadge usage в PositionRow**

В `PositionRow` (~line 557-564), удалить `<StatusBadge>`:

```diff
 {has('side') && (
   <td className="py-3 px-2">
     <div className="flex items-center gap-1.5">
       <DirectionBadge direction={position.direction} />
-      <StatusBadge status={position.status} />
     </div>
   </td>
 )}
```

Сам компонент `StatusBadge` (line 277-290) **оставить пока** — может использоваться в `OpenPositionExpand` для open-позиций на /positions (там бейдж «ОТКРЫТА» уместен).

- [ ] **Step 2: Упростить `isOpen` ветки в `PositionRow`**

В `PositionRow` (line 511):

```diff
- const isOpen = position.status === 'open';
- const pnlValue = isOpen ? position.unrealized_pnl : position.realized_pnl;
+ const pnlValue = position.realized_pnl;
```

Удалить usage `italic` пропсов в `<PnLValue value={pnlValue} italic={isOpen} />` и аналогичных `<PctValue>`, `<RValue>`:

```diff
- <PnLValue value={pnlValue} italic={isOpen} />
+ <PnLValue value={pnlValue} />
```

Если есть условный rendering "если open показываем X, если closed — Y" — оставить только closed branch.

- [ ] **Step 3: Упростить `PnLBreakdownCard`**

В `PnLBreakdownCard` (line 446-498):

```diff
- const isOpen = position.status === 'open';
- const total = isOpen ? position.unrealized_pnl : position.realized_pnl;
+ const total = position.realized_pnl;
```

Удалить блок "Нереализованная (MTM)" (lines 481-486) полностью. Удалить условный label «Net P&L (open, MTM)» — оставить только «Net P&L»:

```diff
- <span className="text-slate-200 font-semibold uppercase text-[11px]">
-   {isOpen ? 'Net P&L (open, MTM)' : 'Net P&L'}
- </span>
+ <span className="text-slate-200 font-semibold uppercase text-[11px]">Net P&L</span>
  <span className="text-base">
-   <PnLValue value={total} italic={isOpen} />
+   <PnLValue value={total} />
  </span>
```

- [ ] **Step 4: Упростить `ExecutionList`**

В `ExecutionList` (line 376-377):

```diff
 {executions.map((ex, idx) => {
-  const isClosed = ex.exit_at !== null;
   return (
     <tr key={ex.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
       <td className="py-1.5 pr-2 text-slate-500 font-mono">{idx + 1}</td>
       <td className="py-1.5 px-2">
-        {isClosed
-          ? <span className="text-rose-300 text-[10px] font-semibold uppercase">Закрытие</span>
-          : <span className="text-emerald-300 text-[10px] font-semibold uppercase">Открытие</span>}
+        <span className="text-rose-300 text-[10px] font-semibold uppercase">Закрытие</span>
       </td>
       ...
```

В журнале все executions закрыты (после filter `?status=closed`), но всё ещё могут быть mid-life entry executions у round-trip позиции (entry → partial close → entry → full close → итого 4 executions, 2 типа). Чтобы не сломать аналитику scale-in, **корректнее так**: проверить тип execution по `direction` и логике entry/exit, а не по `exit_at`. Если `direction` означает «open» (LONG/SHORT entry) — это Открытие; если это close — Закрытие.

Если простой `isClosed = ex.exit_at !== null` сейчас работает корректно (например, в Eqio Trade row = одна round-trip строка, не split на entry+exit) — оставить ветку как fallback. Проверь Trade модель ([backend/models.py](../../backend/models.py)) перед удалением. Если Trade row хранит entry+exit в одной строке, то после фильтра status=closed все Trade rows имеют exit_at !== null → весь conditional collapsable в hardcoded «Закрытие». Это и есть правильное упрощение.

- [ ] **Step 5: TypeScript check + smoke**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsc --noEmit; npm run dev
```

Открой http://localhost:3000/history. Expected:
- Нет «ОТКРЫТА» бейджа.
- PnL не курсивный.
- Нет блока «Нереализованная (MTM)» в expand карточке.
- Все executions помечены как «Закрытие».

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PositionJournalView.tsx
git commit -m "refactor(journal): удалить open-ветки из PositionJournalView"
```

---

## Task 3: Sidebar — переименовать «Позиции» → «Открытые позиции»

**Files:**
- Modify: `frontend/src/components/AppShell.tsx:85`

- [ ] **Step 1: Заменить label**

```diff
-{ label: "Позиции", href: "/positions", icon: <Wallet size={18} /> },
+{ label: "Открытые позиции", href: "/positions", icon: <Wallet size={18} /> },
```

- [ ] **Step 2: Smoke check**

Открой любую страницу с AppShell. Sidebar показывает «Открытые позиции».

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AppShell.tsx
git commit -m "ui(nav): переименовать sidebar item «Позиции» → «Открытые позиции»"
```

---

## Task 4: Pure function `joinPositionsTrades`

**Files:**
- Create: `frontend/src/app/positions/joinPositionsTrades.ts`
- Test: проверка через standalone Node script (опционально) + использование в Task 5 (manual smoke)

- [ ] **Step 1: Создать `joinPositionsTrades.ts`**

```ts
// frontend/src/app/positions/joinPositionsTrades.ts

/**
 * Join Position-snapshot (Tinkoff Portfolio API) с агрегированными
 * round-trip позициями (Trade table) по `instrument_uid`. Возвращает
 * массив enriched-позиций: snapshot строка с прикреплёнными open Trade
 * rows для expand-row UI.
 *
 * Контракт endpoint'ов:
 * - `/positions` отдаёт `PositionResponse[]` (snapshot).
 * - `/trades/positions?status=open` отдаёт `PositionTrade[]` (aggregate
 *   с executions внутри).
 *
 * Если у snapshot позиции нет matching open Trade rows — позиция
 * показывается с пустым executions (UI отрендерит «Trade row не создан»
 * placeholder).
 *
 * Если есть open Trade rows без matching snapshot — они отфильтровываются
 * (Position table = source of truth для отображения, см. design doc).
 */

export interface PositionResponse {
  instrument_uid: string;
  instrument_type: string;
  figi: string | null;
  ticker: string | null;
  name: string | null;
  quantity: number;
  avg_entry_price: string;
  current_price: string | null;
  unrealized_pnl: string | null;
  unrealized_pnl_percent: number | null;
  last_priced_at: string | null;
  currency: string;
}

export interface TradeExecution {
  id: number;
  entry_at: string;
  exit_at: string | null;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  direction: string;
  notes?: string | null;
  has_notes?: boolean;
  setup_name?: string | null;
  screenshot_url?: string | null;
}

export interface PositionTrade {
  symbol: string;
  asset_name: string | null;
  instrument_uid: string | null;
  status: 'open' | 'closed';
  executions: TradeExecution[];
}

export interface EnrichedPosition extends PositionResponse {
  open_executions: TradeExecution[];
}

export function joinPositionsTrades(
  snapshot: PositionResponse[],
  openTrades: PositionTrade[],
): EnrichedPosition[] {
  // Индексируем open Trade rows по instrument_uid → executions.
  // Один instrument_uid может иметь только одну PositionTrade-группу
  // в статусе 'open' (round-trip lifecycle = один открытый цикл per
  // instrument). Если несколько — мерджим executions (defensive).
  const tradesByUid = new Map<string, TradeExecution[]>();
  for (const pt of openTrades) {
    if (!pt.instrument_uid || pt.status !== 'open') continue;
    const existing = tradesByUid.get(pt.instrument_uid) || [];
    tradesByUid.set(pt.instrument_uid, [...existing, ...pt.executions]);
  }

  return snapshot.map((pos) => ({
    ...pos,
    open_executions: tradesByUid.get(pos.instrument_uid) || [],
  }));
}
```

- [ ] **Step 2: TypeScript check**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Verify via ad-hoc Node script (optional, recommended)**

Создай временный файл `frontend/src/app/positions/__joinPositionsTrades.smoke.ts`:

```ts
import { joinPositionsTrades } from './joinPositionsTrades';

const snap = [
  { instrument_uid: 'sber-uid', ticker: 'SBER', name: 'Сбер', quantity: 10,
    avg_entry_price: '300', current_price: '305', unrealized_pnl: '50',
    unrealized_pnl_percent: 1.67, last_priced_at: null, instrument_type: 'share',
    figi: null, currency: 'rub' },
  { instrument_uid: 'gazp-uid', ticker: 'GAZP', name: 'Газпром', quantity: 5,
    avg_entry_price: '150', current_price: '148', unrealized_pnl: '-10',
    unrealized_pnl_percent: -1.33, last_priced_at: null, instrument_type: 'share',
    figi: null, currency: 'rub' },
];
const trades = [
  { symbol: 'SBER', asset_name: 'Сбер', instrument_uid: 'sber-uid',
    status: 'open' as const, executions: [
      { id: 1, entry_at: '2026-05-15', exit_at: null, entry_price: 300,
        exit_price: null, quantity: 10, direction: 'LONG', notes: 'пробой' },
    ] },
];

const result = joinPositionsTrades(snap, trades);
console.log(JSON.stringify(result, null, 2));
// Expected: SBER row has open_executions=[id=1], GAZP row has open_executions=[].
```

Run:

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsx src/app/positions/__joinPositionsTrades.smoke.ts
```

Expected output: SBER с одной execution, GAZP с пустым массивом.

Удалить temp файл после verification:

```powershell
del src/app/positions/__joinPositionsTrades.smoke.ts
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/positions/joinPositionsTrades.ts
git commit -m "feat(positions): pure function joinPositionsTrades для join snapshot×trades"
```

---

## Task 5: `OpenPositionExpand` компонент

**Files:**
- Create: `frontend/src/app/positions/OpenPositionExpand.tsx`

- [ ] **Step 1: Создать компонент**

```tsx
// frontend/src/app/positions/OpenPositionExpand.tsx
'use client';

import { StickyNote, ImageIcon, Edit2 } from 'lucide-react';
import type { TradeExecution } from './joinPositionsTrades';

interface OpenPositionExpandProps {
  executions: TradeExecution[];
  onEdit: (executionId: number) => void;
}

const fmtDate = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};

const fmtPrice = (n: number): string =>
  n.toLocaleString('ru-RU', { maximumFractionDigits: 4 });

const fmtQty = (n: number): string =>
  n.toLocaleString('ru-RU');

export function OpenPositionExpand({ executions, onEdit }: OpenPositionExpandProps) {
  if (executions.length === 0) {
    return (
      <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-4 text-sm text-amber-200">
        Trade row для этой позиции ещё не создан. Будет добавлен при следующей
        синхронизации с брокером.
      </div>
    );
  }

  // Default sort: новейший вход сверху (desc по entry_at) — по решению пользователя.
  const sorted = [...executions].sort(
    (a, b) => new Date(b.entry_at).getTime() - new Date(a.entry_at).getTime(),
  );

  return (
    <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 font-semibold">
        Входы ({executions.length})
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-700/50">
            <th className="text-left py-1.5 pr-2 font-medium">Дата входа</th>
            <th className="text-right py-1.5 px-2 font-medium">Кол-во</th>
            <th className="text-right py-1.5 px-2 font-medium">Цена входа</th>
            <th className="text-left py-1.5 px-2 font-medium">Сетап</th>
            <th className="text-left py-1.5 px-2 font-medium">Заметка</th>
            <th className="text-right py-1.5 pl-2 font-medium">Действия</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((ex) => {
            // Note preview: 1 строка truncate (max 60 символов), full в EditTradeModal.
            const notePreview = ex.notes && ex.notes.length > 60
              ? ex.notes.slice(0, 60) + '…'
              : ex.notes;
            return (
              <tr key={ex.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                <td className="py-2 pr-2 text-slate-300 whitespace-nowrap">{fmtDate(ex.entry_at)}</td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-slate-200">
                  {fmtQty(ex.quantity)}
                </td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-slate-200">
                  {fmtPrice(ex.entry_price)}
                </td>
                <td className="py-2 px-2 text-slate-300">
                  {ex.setup_name || <span className="text-slate-600">—</span>}
                </td>
                <td className="py-2 px-2 text-slate-300 max-w-[260px]">
                  <div className="flex items-center gap-1.5">
                    {ex.screenshot_url && (
                      <span title="Есть скриншот">
                        <ImageIcon size={12} className="text-cyan-400 shrink-0" />
                      </span>
                    )}
                    {notePreview ? (
                      <span title={ex.notes ?? undefined} className="truncate cursor-help">
                        <StickyNote size={12} className="text-cyan-400 inline mr-1" />
                        {notePreview}
                      </span>
                    ) : (
                      <span className="text-slate-600 text-[11px]">Нет заметки</span>
                    )}
                  </div>
                </td>
                <td className="py-2 pl-2 text-right">
                  <button
                    onClick={() => onEdit(ex.id)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-slate-200 bg-slate-700/50 hover:bg-slate-700"
                  >
                    <Edit2 size={11} />
                    Редактировать
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/positions/OpenPositionExpand.tsx
git commit -m "feat(positions): OpenPositionExpand компонент для expand-row"
```

---

## Task 6: `/positions/page.tsx` — параллельный fetch + expand + EditTradeModal

**Files:**
- Modify: `frontend/src/app/positions/page.tsx` (полный rework state и render)

- [ ] **Step 1: Заменить state и fetch**

Импорты сверху файла:

```tsx
import { joinPositionsTrades, type EnrichedPosition, type PositionTrade } from './joinPositionsTrades';
import { OpenPositionExpand } from './OpenPositionExpand';
import { EditTradeModal } from '@/components/EditTradeModal';
```

Замени state-блок (~line 124-131 — `positions`, `loading`, `error`, `syncing`, `activeConnectionId`, `sortKey`, `sortDir`) на:

```tsx
const [enriched, setEnriched] = useState<EnrichedPosition[]>([]);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [syncing, setSyncing] = useState(false);
const [activeConnectionId, setActiveConnectionId] = useState<number | null>(null);
const [sortKey, setSortKey] = useState<SortKey>('pnl');
const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
const [expanded, setExpanded] = useState<Set<string>>(new Set());
const [editingTradeId, setEditingTradeId] = useState<number | null>(null);
```

Замени `fetchPositions` на параллельный fetch + join:

```tsx
const fetchPositions = useCallback(async () => {
  setLoading(true);
  setError(null);
  try {
    const [snap, openPos] = await Promise.all([
      api.get<PositionResponse[]>('/positions'),
      api.get<PositionTrade[]>('/trades/positions?status=open').catch(() => []),
    ]);
    setEnriched(joinPositionsTrades(snap, openPos));
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Не удалось загрузить позиции';
    setError(msg);
  } finally {
    setLoading(false);
  }
}, []);
```

Note: `.catch(() => [])` для `/trades/positions` — graceful degradation если endpoint отвалился, /positions всё равно покажется как read-only (по сценарию из spec error handling).

- [ ] **Step 2: Заменить usage `positions` → `enriched` в sort и render**

В sort logic (~line 177-189):

```diff
- const sorted = [...positions].sort((a, b) => { ... });
+ const sorted = [...enriched].sort((a, b) => { ... });
```

В summary card (~line 199-205):

```diff
- const totalUnrealized = positions.reduce(...);
- const portfolioCurrency = positions[0]?.currency || 'rub';
+ const totalUnrealized = enriched.reduce(...);
+ const portfolioCurrency = enriched[0]?.currency || 'rub';
```

В таблице (~line 298+):

```diff
- {!loading && !error && positions.length > 0 && (
+ {!loading && !error && enriched.length > 0 && (
```

И empty state:

```diff
- {!loading && !error && positions.length === 0 && (
+ {!loading && !error && enriched.length === 0 && (
```

И summary card outer condition:

```diff
- {!loading && positions.length > 0 && (
+ {!loading && enriched.length > 0 && (
```

В summary card text:

```diff
- <div className="text-2xl font-bold">{positions.length}</div>
+ <div className="text-2xl font-bold">{enriched.length}</div>
```

- [ ] **Step 3: Добавить expand column в таблицу**

В `<thead>` добавь первую колонку (~line 302):

```diff
 <thead className="bg-[var(--surface-hover)] text-[var(--text-secondary)]">
   <tr>
+    <th className="px-2 py-3 w-8" aria-label="Expand"></th>
     <th onClick={() => setSort('ticker')} ...>Тикер</th>
```

В `<tbody>` (~line 330) замени один `<tr>` на fragment с двумя `<tr>` (main row + optional expand row):

```tsx
{sorted.map((p) => {
  const pnl = p.unrealized_pnl ? parseFloat(p.unrealized_pnl) : null;
  const pct = p.unrealized_pnl_percent;
  const isLong = p.quantity > 0;
  const isExpanded = expanded.has(p.instrument_uid);
  const toggleExpand = () => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(p.instrument_uid)) next.delete(p.instrument_uid);
      else next.add(p.instrument_uid);
      return next;
    });
  };
  return (
    <Fragment key={p.instrument_uid}>
      <tr
        className="border-t border-[var(--border)] hover:bg-[var(--surface-hover)] cursor-pointer"
        onClick={toggleExpand}
      >
        <td className="px-2 py-3 align-middle">
          <button
            className="text-[var(--text-secondary)] hover:text-[var(--foreground)]"
            aria-label={isExpanded ? 'Свернуть' : 'Развернуть'}
            onClick={(e) => { e.stopPropagation(); toggleExpand(); }}
          >
            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        </td>
        {/* ...existing <td>...</td> ячейки... */}
      </tr>
      {isExpanded && (
        <tr className="bg-[var(--surface-hover)]/40 border-t border-[var(--border)]">
          <td colSpan={10} className="px-4 py-3">
            <OpenPositionExpand
              executions={p.open_executions}
              onEdit={(executionId) => setEditingTradeId(executionId)}
            />
          </td>
        </tr>
      )}
    </Fragment>
  );
})}
```

Добавь `import { ChevronDown, ChevronRight, Fragment } from ...` где нужно (Fragment из 'react', chevrons из 'lucide-react').

- [ ] **Step 4: Добавить EditTradeModal**

После `</AppShell>` (перед closing `</>` если есть, или в конце JSX) добавь:

```tsx
{editingTradeId !== null && (
  <EditTradeModal
    isOpen={true}
    trade={
      // Найти Trade execution по id в enriched.open_executions
      enriched
        .flatMap((p) => p.open_executions)
        .find((ex) => ex.id === editingTradeId) ?? null
    }
    onClose={() => setEditingTradeId(null)}
    onSuccess={() => {
      setEditingTradeId(null);
      fetchPositions();
    }}
  />
)}
```

**Важно:** проверить точную сигнатуру `EditTradeModalProps` ([frontend/src/components/EditTradeModal.tsx:7](../../frontend/src/components/EditTradeModal.tsx#L7)). Если `trade` ожидает другой тип (не `TradeExecution`), а полный `Trade` из API — нужно либо:
- (a) расширить `TradeExecution` interface в `joinPositionsTrades.ts` до полей, которые требует EditTradeModal, или
- (b) дотянуть полный Trade через `GET /trades/{id}` при клике «Редактировать».

Default — (a): расширить `TradeExecution` всеми manual fields (note, setup_id, screenshot_url, tags, confidence, mood, discipline, timeframe, risk_amount, r_multiple_planned, leverage, commission, swap). Backend endpoint `/trades/positions?status=open` уже возвращает их в `executions` массиве (см. `schemas.TradeExecution` или соответствующий schema — проверить и подтвердить наличие полей).

Если backend не возвращает все нужные поля — (b) лазить за полным Trade при клике редактировать:

```tsx
onEdit={async (executionId) => {
  const full = await api.get<Trade>(`/trades/${executionId}`);
  setEditingTrade(full);
}}
```

Это решение принять при чтении кода `EditTradeModal` и `PositionTrade` schema на Step 4.

- [ ] **Step 5: TypeScript check**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 6: Manual smoke check**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npm run dev
```

Открой http://localhost:3000/positions. Expected flow:
1. Видна таблица с открытыми позициями (как раньше).
2. Каждая строка имеет chevron слева.
3. Клик по chevron → раскрывается expand с executions list.
4. Если есть executions — таблица с датой/qty/цена/setup/note + кнопка «Редактировать».
5. Клик «Редактировать» → открывается EditTradeModal с заполненными полями.
6. Сохранение → modal закрывается, данные refetch'ятся.
7. Если у Position нет open_executions (phantom) → видно «Trade row не создан».

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/positions/page.tsx
git commit -m "feat(positions): editing surface — parallel fetch + expand + EditTradeModal"
```

---

## Task 7: Финальный verification + summary

**Files:** Никаких изменений кода. Только manual smoke checklist.

- [ ] **Step 1: Полный smoke checklist**

Запусти dev server, открой каждую страницу и пройди:

**`/history` (Дневник сделок):**
- [ ] Видны ТОЛЬКО закрытые позиции.
- [ ] Нет «ОТКРЫТА» бейджа нигде.
- [ ] PnL не курсивный.
- [ ] В expand карточке нет блока «Нереализованная (MTM)».
- [ ] Колонка «Тип» в executions — везде «Закрытие».
- [ ] EditTradeModal открывается на закрытую сделку и сохраняет.

**Sidebar:**
- [ ] Пункт меню называется «Открытые позиции» (не «Позиции»).

**`/positions` (Открытые позиции):**
- [ ] H1 — «Открытые позиции».
- [ ] Таблица с открытыми позициями загружается.
- [ ] Chevron слева у каждой строки.
- [ ] Клик chevron → expand раскрывается.
- [ ] Если есть open_executions → видна таблица с note/setup/screenshot icon + кнопка «Редактировать».
- [ ] Если нет open_executions (phantom case) → видно «Trade row не создан».
- [ ] Клик «Редактировать» → EditTradeModal открывается.
- [ ] Сохранение → modal закрывается, refetch обновляет данные.
- [ ] Несколько входов на один инструмент (scale-in) — все видны в expand с независимым editing.

**Регрессии:**
- [ ] Dashboard не сломан (headline PnL, equity curve работают).
- [ ] Sync кнопка на /positions работает.
- [ ] `/history` sort, filters работают.

- [ ] **Step 2: Run typecheck + linter**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\frontend; npx tsc --noEmit; npm run lint
```

Expected: 0 errors.

- [ ] **Step 3: Run backend tests (sanity)**

```powershell
cd c:\Users\Administrator\Eqio\ATOM\backend; pytest tests/integration/test_position_aggregation.py -q
```

Expected: все тесты pass (мы backend не трогали, но coverage уверенность).

- [ ] **Step 4: Финальный commit (если есть оставшиеся изменения)**

Если по ходу smoke check всплыли мелкие правки:

```bash
git add <files>
git commit -m "fix(positions): <конкретная правка>"
```

Иначе пропустить шаг.

---

## Self-Review

**1. Spec coverage** ([2026-05-19-positions-as-editing-surface-design.md](../specs/2026-05-19-positions-as-editing-surface-design.md)):

| Spec section | Task |
|---|---|
| `/history` фильтр `?status=closed` | Task 1 ✓ |
| PositionJournalView — удалить open-ветки | Task 2 ✓ |
| Sidebar переименование | Task 3 ✓ |
| Pure join function | Task 4 ✓ |
| Expand UI + executions list | Task 5 ✓ |
| EditTradeModal integration | Task 6 ✓ |
| Phantom case placeholder | Task 5 (внутри `OpenPositionExpand`) ✓ |
| Graceful degradation /trades/positions отвалился | Task 6, Step 1 (`.catch(() => [])`) ✓ |
| Sort executions desc | Task 5 ✓ |
| Note preview 1 строка truncate | Task 5 ✓ |
| Screenshot icon + hover tooltip | Task 5 ✓ |

**2. Placeholder scan**: TODO/TBD/«implement later» — нет. Все code blocks с конкретным кодом.

**3. Type consistency**: `EnrichedPosition extends PositionResponse with open_executions: TradeExecution[]` — используется консистентно в Task 4, 5, 6. `joinPositionsTrades(snapshot, openTrades)` сигнатура одна. `onEdit(executionId: number)` сигнатура одна в Task 5 и Task 6.

**4. Known caveat в Task 6, Step 4**: точная сигнатура EditTradeModal зависит от backend schema `PositionTrade.executions`. Решение (a vs b) принимается при чтении кода — это явно flag'нуто, не скрытый placeholder.

---

## Execution Handoff

Plan complete and saved to `c:/Users/Administrator/Eqio/ATOM/docs/superpowers/plans/2026-05-19-positions-as-editing-surface.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — я диспатчу свежего subagent на каждую task, ревью между tasks, быстрая итерация. Лучше для UI work где manual smoke check между шагами критичен.

2. **Inline Execution** — выполняем tasks в текущей сессии через executing-plans skill, batch execution с checkpoint'ами для ревью. Быстрее но меньше изоляции контекста.

Какой подход?

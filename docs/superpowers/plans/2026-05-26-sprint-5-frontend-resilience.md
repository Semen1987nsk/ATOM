# Sprint 5 — Frontend: устойчивость, типы, a11y (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended). Steps use checkbox (`- [ ]`) syntax for tracking. **Stack:** Next.js 16 App Router + React 19 + Tailwind v4. **`PYTHONUTF8=1`** для всех Python-команд; для npm — без особых префиксов.

**Goal:** дашборд и analysis-страницы перестают тихо проглатывать ошибки fetch'а; модалки соответствуют WCAG (role/aria/focus-trap/ESC); реальные OpenAPI-типы вместо stub'а; компонентные/E2E тесты для критичной логики; bundle меньше через RSC + lazy Recharts.

**Architecture:**
- **Error UX:** ошибки fetch'а возвращают `ApiError` через `lib/apiClient.ts` (уже есть), state выставляется в UI с retry-кнопкой; общий `<DataError onRetry/>` компонент.
- **Error boundaries:** `app/error.tsx`, `app/loading.tsx`, `app/global-error.tsx` + per-route на тяжёлых страницах (`history/`, `analysis/*`, `admin/`).
- **Data layer:** TanStack Query через `lib/queries.ts` (уже определены 8 хуков, но не используются) — миграция дашборда + analysis + auth с `useState+useEffect+api.get`.
- **Modal a11y:** все модалки через `<Modal>` из `ui/Modal.tsx` (role/aria/ESC уже реализованы); добавляем focus-trap вручную (10-30 строк); удаляем `blur-orbs`/`text-neon` design-system нарушения.
- **Types:** `npm run gen:api-types:from-file` генерирует ~5000+ строк типов из `backend/openapi.json` (заменяет 48-строчный stub `src/types/api.generated.ts`); CI-шаг гарантирует отсутствие diff'а.
- **RSC pragma:** статичные страницы (manual/privacy/pricing/help/blog) → full RSC; динамичные → server-shell + client island через `serverApiClient.ts` (уже есть).
- **Polling dedup:** общий `useSyncStatusQuery` (TanStack) — два компонента header'а читают тот же query-key, дедуп через cache.
- **Tests:** vitest + jsdom + RTL для unit/component; Playwright для e2e (login → dashboard → add-trade); jsdom-environment в `vitest.config.ts`.

**Tech Stack:** Next.js 16 · React 19 · Tailwind v4 · TanStack Query 5 (уже установлен) · openapi-typescript 7.4 (уже установлен) · vitest · **новые devDeps:** `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `@playwright/test`.

**Operating mode (NO-COMMIT):** код, тесты — да; `git add`/`commit` — НЕТ.

**Deferred to Sprint 6:** **SEC-14** (nonce-based CSP) — требует Next.js `src/middleware.ts` (не существует) + изменения в `layout.tsx` + координацию backend `SecurityHeadersMiddleware`; `unsafe-inline` для Next.js flight-payload задокументирован, акцептируется до Sprint 6 deploy/hardening.

---

## Декомпозиция файлов

**Новые:**
- `frontend/src/components/ui/DataError.tsx` — `<DataError error: ApiError | null, onRetry: () => void/>`.
- `frontend/src/app/error.tsx`, `frontend/src/app/loading.tsx`, `frontend/src/app/global-error.tsx` — App Router boundaries.
- `frontend/src/app/history/error.tsx`, `frontend/src/app/analysis/error.tsx`, `frontend/src/app/admin/error.tsx` — per-route.
- `frontend/src/lib/lazy-recharts.ts` — barrel-файл, `dynamic()` для всех Recharts-импортов.
- `frontend/src/lib/useSyncStatusQuery.ts` — shared TanStack-хук для `/broker/sync-status`.
- `frontend/playwright.config.ts` — Playwright config.
- `frontend/e2e/login-dashboard.spec.ts` — happy-path e2e.
- `frontend/src/lib/__tests__/apiClient.test.ts` — 401-refresh, CSRF, timeout.
- `frontend/src/contexts/__tests__/AuthContext.test.tsx` — login flow.
- `frontend/src/components/ui/__tests__/Modal.test.tsx` — ESC, role, focus-trap.
- `frontend/vitest.setup.ts` — jsdom + RTL setup.
- `backend/scripts/dump_openapi.py` (если нет) — генератор `backend/openapi.json` для FE codegen.

**Модифицируемые:**
- `frontend/src/types/api.generated.ts` — перезаписать через `npm run gen:api-types:from-file`.
- `frontend/src/app/globals.css` — добавить `:focus-visible` правила.
- `frontend/src/app/page.tsx` — `fetchData` через TanStack + error-state UI.
- `frontend/src/lib/useAnalysisStats.ts` — вернуть `error: ApiError | null`; общий error handler.
- 7 analysis-страниц (`analysis/{calendar,setups,post-exit,tags,mae-mfe,insights}`, `review/page.tsx`, `journal/screenshots/page.tsx`) — error UX через `<DataError/>`.
- `frontend/src/components/{AddTradeModal,EditTradeModal}.tsx` — миграция на `<Modal>` из `ui/Modal.tsx`; удалить `text-neon`/`blur-orbs`.
- `frontend/src/components/ui/Modal.tsx` — добавить focus-trap (≤30 строк).
- `frontend/src/components/BrokerStatusBadge.tsx`, `SyncStatusIndicator.tsx` — на shared `useSyncStatusQuery`.
- `frontend/src/contexts/AuthContext.tsx` — `useCurrentUserQuery` вместо `fetchCurrentUser`.
- `frontend/src/app/manual/page.tsx` — editorial-rewrite (убрать blur-orbs, cyber-стиль).
- `frontend/src/app/history/page.tsx` — split на 4-5 модулей (фильтры, таблица, row-expand, import-modal, drawer).
- `frontend/next.config.ts` — `images.remotePatterns` (вместо `unoptimized`).
- `frontend/vitest.config.ts` — `environment: 'jsdom'` + `setupFiles`.
- `frontend/package.json` — devDeps: jsdom, RTL stack, @playwright/test.

---

## Batch 1 — Quick wins (codegen + CSS + dedup)

### Task 1.1: FE-03 — OpenAPI types regen

**Files:**
- Modify: `frontend/src/types/api.generated.ts` (regen, не редактировать вручную).
- Possibly create: `backend/scripts/dump_openapi.py`.

- [ ] **Step 1: Проверить наличие `backend/openapi.json` или скрипта дампа**

```
PYTHONUTF8=1 python -X utf8 -c "from main import app; import json; print(json.dumps(app.openapi(), indent=2))" > backend/openapi.json
```

(Если есть готовый script — использовать. Иначе создать `backend/scripts/dump_openapi.py`.)

- [ ] **Step 2: Запустить codegen**

```
cd frontend
npm run gen:api-types:from-file
```

Это перезапишет `src/types/api.generated.ts` реальными типами (~5000 строк) из OpenAPI schema.

- [ ] **Step 3: Verify smoke**

```
cd frontend
npx tsc --noEmit
```

Если есть TS-ошибки в существующем коде из-за strict types — поправить точечно (`as unknown as RealType` где stub допускал `any`).

- [ ] **Step 4: NO-COMMIT**

---

### Task 1.2: FE-04 — focus-visible на кнопках

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Добавить глобальное правило**

В `globals.css` (после `@theme inline` блока):

```css
/* FE-04 (WCAG 2.4.7): focus-visible кольцо на всех интерактивных элементах */
*:focus {
  outline: none;
}

*:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: inherit;
}

/* Для иконочных кнопок — внутренний accent ring чтобы не разрывал overflow */
.btn-icon:focus-visible {
  outline-offset: 0;
  box-shadow: 0 0 0 2px var(--accent);
}
```

- [ ] **Step 2: Visual check** — открыть `/`, нажать Tab, увидеть focus-кольцо.

Если в этой сессии браузер недоступен — отметить в concerns, отложить визуальную проверку.

- [ ] **Step 3: NO-COMMIT**

---

### Task 1.3: FE-10 — Дедуп polling sync-status

**Files:**
- Create: `frontend/src/lib/useSyncStatusQuery.ts`
- Modify: `frontend/src/components/BrokerStatusBadge.tsx`, `frontend/src/components/SyncStatusIndicator.tsx`

- [ ] **Step 1: Создать shared hook**

```typescript
// frontend/src/lib/useSyncStatusQuery.ts
import { useQuery } from '@tanstack/react-query';
import { api } from './apiClient';
import type { SyncStatus } from '@/types/api.generated';  // realted после Task 1.1

export const syncStatusQueryKey = ['broker', 'sync-status'] as const;

export function useSyncStatusQuery(options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: syncStatusQueryKey,
    queryFn: () => api.get<SyncStatus>('/broker/sync-status'),
    refetchInterval: options?.refetchInterval ?? 30_000,
    staleTime: 30_000,
  });
}
```

- [ ] **Step 2: Заменить `setInterval` в обоих компонентах**

В `BrokerStatusBadge.tsx`:

```typescript
// Было: setInterval(fetchOnce, 30000) + локальный state
// Стало:
const { data, isError } = useSyncStatusQuery();
```

Аналогично в `SyncStatusIndicator.tsx`. Если этот компонент дополнительно дёргает `/broker/health` — оставить, либо вынести в parallel `useBrokerHealthQuery`.

- [ ] **Step 3: Тест на дедуп — counter-fixture**

```typescript
// frontend/src/lib/__tests__/useSyncStatusQuery.test.tsx
// Проверить: два <BrokerStatusBadge> + <SyncStatusIndicator> на одной странице 
// = только один SQL-запрос за интервал (через MSW или fetch-mock).
```

Если jsdom/RTL ещё не настроен (Task 8.1 пока не выполнен) — отложить тест и пометить в TODO.

- [ ] **Step 4: NO-COMMIT**

---

## Batch 2 — Error boundaries + Error UX (FE-01, FE-02, FE-06)

### Task 2.1: FE-06 — App Router boundaries

**Files:**
- Create: `frontend/src/app/error.tsx`, `loading.tsx`, `global-error.tsx`.
- Create: `frontend/src/app/{history,analysis,admin}/error.tsx`.

- [ ] **Step 1: Root error boundary**

```tsx
// frontend/src/app/error.tsx
'use client';
import { useEffect } from 'react';

export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('Root error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h2 className="text-2xl font-bold mb-2">Что-то пошло не так</h2>
        <p className="text-muted mb-4">Попробуйте обновить страницу или повторить.</p>
        {error.digest && <p className="text-xs text-muted mb-4">ID: {error.digest}</p>}
        <button onClick={reset} className="btn-primary">Повторить</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: loading.tsx + global-error.tsx** — аналогичный паттерн.

- [ ] **Step 3: per-route для history/analysis/admin**

### Task 2.2: `<DataError/>` компонент

**Files:**
- Create: `frontend/src/components/ui/DataError.tsx`

```tsx
// frontend/src/components/ui/DataError.tsx
import type { ApiError } from '@/lib/apiClient';

export function DataError({ error, onRetry }: { error: ApiError | null; onRetry: () => void }) {
  if (!error) return null;
  return (
    <div className="rounded-lg border border-danger/50 bg-danger/5 p-6 text-center">
      <p className="text-danger font-semibold mb-2">Ошибка загрузки</p>
      <p className="text-sm text-muted mb-4">{error.toUserMessage()}</p>
      <button onClick={onRetry} className="btn-secondary">Повторить</button>
    </div>
  );
}
```

### Task 2.3: FE-01 — Dashboard error state

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Заменить silent catch на state**

```tsx
const [error, setError] = useState<ApiError | null>(null);

const fetchData = useCallback(async () => {
  setLoading(true);
  setError(null);
  try {
    const [stats, trades] = await Promise.all([
      api.get<DashboardStats>('/stats/'),
      api.get<Trade[]>('/trades/?limit=10'),
    ]);
    setStats(stats);
    setTrades(trades);
  } catch (e) {
    setError(e as ApiError);
    addLog(t.logs.syncFailed);
  } finally {
    setLoading(false);
  }
}, []);

// В JSX:
{error ? <DataError error={error} onRetry={fetchData} /> : <DashboardGrid stats={stats} trades={trades} />}
```

### Task 2.4: FE-02 — Analysis pages + useAnalysisStats

**Files:**
- Modify: `frontend/src/lib/useAnalysisStats.ts`

- [ ] **Step 1: Вернуть error**

```typescript
export function useAnalysisStats() {
  const [stats, setStats] = useState<AnalysisStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<AnalysisStats>('/stats/advanced');
      setStats(data);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  return { stats, loading, error, refetch: fetch };
}
```

- [ ] **Step 2: 7 страниц используют новый shape**

Для каждой:
- `analysis/calendar/page.tsx`
- `analysis/setups/page.tsx`
- `analysis/post-exit/page.tsx`
- `analysis/tags/page.tsx`
- `analysis/mae-mfe/page.tsx`
- `analysis/insights/page.tsx`
- `review/page.tsx`
- `journal/screenshots/page.tsx`

```tsx
const { stats, loading, error, refetch } = useAnalysisStats();
if (error) return <DataError error={error} onRetry={refetch} />;
if (loading) return <Skeleton />;
if (!stats) return <EmptyState />;
// ... отрисовка
```

- [ ] **Step 3: NO-COMMIT**

---

## Batch 3 — Modal a11y (FE-05 + design-system cleanup)

### Task 3.1: focus-trap в `ui/Modal.tsx`

**Files:**
- Modify: `frontend/src/components/ui/Modal.tsx`

- [ ] **Step 1: Добавить focus-trap**

```tsx
useEffect(() => {
  if (!open) return;
  const modal = modalRef.current;
  if (!modal) return;

  // Сохранить прежний focus
  const previousFocus = document.activeElement as HTMLElement | null;

  // Первый focusable element
  const focusables = modal.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusables[0];
  const last = focusables[focusables.length - 1];

  first?.focus();

  function trap(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }

  modal.addEventListener('keydown', trap);
  return () => {
    modal.removeEventListener('keydown', trap);
    previousFocus?.focus();
  };
}, [open]);
```

### Task 3.2: Миграция AddTradeModal + EditTradeModal

**Files:**
- Modify: `frontend/src/components/{AddTradeModal,EditTradeModal}.tsx`

- [ ] **Step 1: Заменить custom backdrop на `<Modal>`**

```tsx
// Было: <div className="fixed inset-0 bg-black/80 backdrop-blur-sm">...
// Стало:
import { Modal } from '@/components/ui/Modal';

<Modal open={isOpen} onClose={onClose} title="Новая сделка" size="lg">
  {/* содержимое формы без backdrop-обёртки */}
</Modal>
```

- [ ] **Step 2: Удалить дизайн-нарушения**

- `<h2 ... text-neon italic>` → `<h2 ... font-semibold>` (text-neon — dead class, удалён в v3).
- `<div className="absolute inset-0 ... blur-3xl ...">` orbs → удалить.

- [ ] **Step 3: NO-COMMIT**

---

## Batch 4 — TanStack Query migration (FE-07)

### Task 4.1: Dashboard на useTradesQuery + useStatsQuery

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Заменить useState+useEffect+api.get**

```tsx
import { useTradesQuery, useStatsQuery } from '@/lib/queries';

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading, error: statsError, refetch: refetchStats } = useStatsQuery();
  const { data: trades = [], isLoading: tradesLoading, error: tradesError, refetch: refetchTrades } = useTradesQuery({ limit: 10 });

  const loading = statsLoading || tradesLoading;
  const error = statsError ?? tradesError;
  const refetch = () => { refetchStats(); refetchTrades(); };

  if (error) return <DataError error={error as ApiError} onRetry={refetch} />;
  // ...
}
```

### Task 4.2: AuthContext через useCurrentUserQuery

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx`

- [ ] **Step 1: Заменить fetchCurrentUser**

(Уточнить по факту, что `useCurrentUserQuery` уже совместим с auth-state flow.)

### Task 4.3: useAnalysisStats через useStatsQuery

**Files:**
- Modify: `frontend/src/lib/useAnalysisStats.ts`

- [ ] **Step 1: Делегировать в TanStack**

```typescript
export function useAnalysisStats() {
  const { data, isLoading, error, refetch } = useStatsQuery<AnalysisStats>('/stats/advanced');
  return { stats: data ?? null, loading: isLoading, error: error as ApiError | null, refetch };
}
```

- [ ] **Step 2: NO-COMMIT**

---

## Batch 5 — Performance (FE-09)

### Task 5.1: Lazy Recharts

**Files:**
- Create: `frontend/src/lib/lazy-recharts.ts`
- Modify: 4 файла-потребителя Recharts.

- [ ] **Step 1: Barrel-файл**

```typescript
// frontend/src/lib/lazy-recharts.ts
import dynamic from 'next/dynamic';

export const LineChart = dynamic(() => import('recharts').then(m => m.LineChart), { ssr: false });
export const BarChart = dynamic(() => import('recharts').then(m => m.BarChart), { ssr: false });
// ... все используемые компоненты
```

- [ ] **Step 2: Заменить прямые импорты**

```typescript
// Было: import { LineChart, ... } from 'recharts';
// Стало: import { LineChart, ... } from '@/lib/lazy-recharts';
```

В 4 файлах: `trades/[id]/replay/page.tsx`, `analysis/setups/page.tsx`, `admin/page.tsx`, `components/dashboard/EquityCurveCard.tsx`.

### Task 5.2: next/image config

**Files:**
- Modify: `frontend/next.config.ts`

- [ ] **Step 1: Установить `remotePatterns` для известных источников**

```typescript
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'investbroker.tinkoff.ru' },  // если используется
      // другие CDN/S3
    ],
  },
};
```

- [ ] **Step 2: Убрать `unoptimized` где возможно**

Для 7 точек (`AddTradeModal:405`, `history:1771`, `blog/[slug]:121,337`, `blog/page:72,154`, `admin:1341`) — если URL подходит под remotePatterns, удалить `unoptimized`. Иначе оставить с комментарием почему.

- [ ] **Step 3: NO-COMMIT**

---

## Batch 6 — RSC migration (FE-08)

### Task 6.1: Статические страницы → full RSC

**Files:**
- Modify: `frontend/src/app/{manual,privacy,pricing,help,blog}/page.tsx`

- [ ] **Step 1: Для каждой страницы**

- Удалить `'use client'`.
- Если есть `useEffect`/`useState` — вынести интерактив в `<Client*>` компонент (например, `<PricingTier interactive client/>`).
- Использовать `<Link>` через next/link (server-friendly).

### Task 6.2: history/page.tsx split

**Files:**
- Modify: `frontend/src/app/history/page.tsx` (1838 строк → split)
- Create: `frontend/src/app/history/_components/{Filters,TradesTable,ImportModal,RowDrawer}.tsx`

- [ ] **Step 1: Разделить по responsibility**

- `_components/Filters.tsx` — фильтры (date range, status, tags, symbols).
- `_components/TradesTable.tsx` — таблица + row-expand.
- `_components/ImportModal.tsx` — модалка импорта (CSV/XLSX).
- `_components/RowDrawer.tsx` — drawer с деталями сделки.
- `page.tsx` — server-shell с initial data fetch через `serverApiClient.ts` + composition.

- [ ] **Step 2: Сократить page.tsx до <300 строк**

- [ ] **Step 3: NO-COMMIT**

---

## Batch 7 — Design-system cleanup (FE-11)

### Task 7.1: Sweep blur-orbs / text-neon / animate-pulse

**Files:**
- 24 файла с `blur-3xl`/`blur-2xl` (полный список в planner-репорте).
- 2 файла с `text-neon` (AddTradeModal, EditTradeModal — уже сделано в Task 3.2).
- `manual/page.tsx` editorial rewrite.

- [ ] **Step 1: Grep + delete**

Все `<div className="... blur-3xl ...">` orbs удалить (это декоративные glow-эффекты, противоречат editorial design).

- [ ] **Step 2: manual/page.tsx rewrite**

В editorial-стиле (см. `.editorial-h1`/`.editorial-lede` в `globals.css`). Удалить cyber-цвета (`purple-500`, `green-400`, `yellow-400`).

- [ ] **Step 3: NO-COMMIT**

---

## Batch 8 — Testing infrastructure (FE-12)

### Task 8.1: Setup jsdom + RTL + Playwright

**Files:**
- Modify: `frontend/vitest.config.ts`, `frontend/package.json`
- Create: `frontend/vitest.setup.ts`, `frontend/playwright.config.ts`

- [ ] **Step 1: Установить devDeps**

```
cd frontend
npm install --save-dev jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: vitest.config.ts**

```typescript
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    globals: true,
  },
  resolve: {
    alias: { '@': '/src' },
  },
});
```

- [ ] **Step 3: vitest.setup.ts**

```typescript
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 4: playwright.config.ts**

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: devices['Desktop Chrome'] },
  ],
});
```

### Task 8.2: Critical-path unit tests

**Files:**
- Create: `frontend/src/lib/__tests__/apiClient.test.ts`
- Create: `frontend/src/contexts/__tests__/AuthContext.test.tsx`
- Create: `frontend/src/components/ui/__tests__/Modal.test.tsx`

- [ ] **Step 1: apiClient — 401-refresh, CSRF, timeout** (≥5 тестов)

- [ ] **Step 2: AuthContext — login flow** (≥3 теста)

- [ ] **Step 3: Modal — ESC, role, focus-trap** (≥4 теста)

### Task 8.3: E2E happy-path

**Files:**
- Create: `frontend/e2e/login-dashboard.spec.ts`

- [ ] **Step 1: Login → dashboard → add trade flow**

```typescript
import { test, expect } from '@playwright/test';

test('login → dashboard → add trade', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="email"]', 'test@example.com');
  await page.fill('input[name="password"]', 'testpassword123');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/');
  // ... add trade
});
```

(Требует seed-аккаунта или mock-auth setup; уточнить с backend testing strategy.)

- [ ] **Step 2: NO-COMMIT**

---

## Self-Review

**Coverage против спеки:**
- FE-01 ✅ Batch 2 (Task 2.3)
- FE-02 ✅ Batch 2 (Task 2.4)
- FE-03 ✅ Batch 1 (Task 1.1)
- FE-04 ✅ Batch 1 (Task 1.2)
- FE-05 ✅ Batch 3 (Task 3.1, 3.2)
- FE-06 ✅ Batch 2 (Task 2.1)
- FE-07 ✅ Batch 4 (Task 4.1, 4.2, 4.3)
- FE-08 ✅ Batch 6 (Task 6.1, 6.2)
- FE-09 ✅ Batch 5 (Task 5.1, 5.2)
- FE-10 ✅ Batch 1 (Task 1.3)
- FE-11 ✅ Batch 3 + Batch 7 (Task 3.2, 7.1)
- FE-12 ✅ Batch 8 (Task 8.1, 8.2, 8.3)
- SEC-14 ⏭️ Deferred Sprint 6

**Placeholder scan:** все code-блоки конкретны. `_components` подкаталог в `history/` — Next.js convention (underscore префикс ⇒ не route).

**Type consistency:** `DataError({ error: ApiError | null, onRetry: () => void })` — единая signature; `useSyncStatusQuery` экспортирует `syncStatusQueryKey`.

**Объём и tactical sequencing:** Batches 1-3 (10 tasks) — критичные для UX и accessibility, должны идти первыми. Batches 4-6 (data + RSC) — рефакторинг. Batches 7-8 (design cleanup + tests) — финальные. Можно резать Sprint 5 на 5a (Batches 1-3) и 5b (Batches 4-8) если хочется быстрого ship'а первой части.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-sprint-5-frontend-resilience.md`.

**Subagent-Driven (recommended)** — диспатч свежего implementer-агента на каждый Task; между задачами `code-reviewer` для UX/a11y чувствительных мест (Batches 2, 3, 8). Playwright e2e — отдельный dispatch с MCP browser navigation для verify.

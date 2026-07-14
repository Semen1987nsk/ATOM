---
name: nextjs-react19-server-patterns
description: Use when writing or refactoring Next.js 16 App Router pages, React 19 components, Server Components, Server Actions, Suspense boundaries, streaming, or data fetching in the Empirik project. Triggers on "Server Component", "Client Component", "Server Action", "Suspense", "streaming", "use client", "Next.js", "React 19", "TanStack Query", "Recharts", "page.tsx", "layout.tsx", "loading.tsx".
---

# Next.js 16 + React 19 Server-first паттерны для Empirik

Гайд для написания страниц и компонентов в `frontend/` Empirik. Цель — отойти от текущего «всё Client» и перейти на Server-first архитектуру там, где это даёт выигрыш: меньше bundle, быстрее first paint, нативный streaming.

## 1. Контекст: Empirik frontend сейчас

Что зафиксировано в `frontend/package.json`:

- `next` 16.1.1, `react` / `react-dom` 19.2.3
- `typescript` 5.x (strict в `tsconfig.json`)
- `tailwindcss` 4.x (через `@tailwindcss/postcss`)
- `@tanstack/react-query` 5.59 + devtools
- `recharts` 3.6
- `lucide-react`, `cmdk`, `clsx`, `tailwind-merge`
- `dompurify` для санитизации, `openapi-typescript` для генерации типов из FastAPI

Бекенд — FastAPI на `localhost:8003` (через `NEXT_PUBLIC_API_URL` или Codespaces), httpOnly cookies для auth, CSRF через `atom_csrf_token`.

### Что преобладает сейчас

Проверка по `src/app/**/page.tsx` показывает **21 из 21 страниц помечены `'use client'`** — Server Components в проекте фактически отсутствуют. `Server Actions` — `0`. Все мутации идут через `apiClient.ts` напрямую к FastAPI с client-side. Контексты (`AuthContext`, `SettingsContext`, `LanguageContext`, `QueryProvider`, `ErrorBoundary`) подняты на root в `src/app/layout.tsx` — это нормально, layout сам остаётся Server.

### Конкретные проблемы

- `src/app/page.tsx` — главный дашборд, 1013 строк, всё Client. Получает 16+ метрик одним `Promise.all([api.get(...), api.get(...)])` — пользователь видит `<DashboardSkeleton />`, пока **все** запросы не вернутся.
- `src/components/AppShell.tsx` — Client (логично, sidebar с popover/cmdk), но содержит достаточно статических данных, которые могли бы быть Server.
- `src/components/dashboard/EquityCurveCard.tsx` — Client (Recharts требует `window`), но получает `data` уже как prop. Это правильная половина паттерна, не хватает Server-обёртки которая фетчит данные.
- `src/lib/apiClient.ts` — клиентский (использует `document.cookie`, `window.dispatchEvent`). Для Server Components нужна параллельная Server-only версия, которая читает cookies через `next/headers`.

### Куда движемся

- `loading.tsx` рядом с `page.tsx` для каждого тяжёлого роута
- Server Components на статичных страницах: `/blog/[slug]`, `/manual`, `/help`, `/pricing`
- Server Components с `<Suspense>` на дашборде и аналитике — каждая плитка стримится независимо
- TanStack Query остаётся для **интерактивности** (live-обновления, refetch по событиям, оптимистичные мутации). Для **initial render** — Server Components с `initialData` пробросом.

## 2. Decision tree: Server vs Client

Главное правило: **по умолчанию Server, делать Client только когда нужно.**

```
Компонент использует одно из:
  - useState / useReducer
  - useEffect / useLayoutEffect / useRef
  - onClick / onChange / onSubmit (event handlers)
  - browser-only API: window, document, localStorage, navigator, IntersectionObserver
  - React Context (consumer)
  - библиотеки, требующие window: recharts, framer-motion, cmdk
        → Client ('use client')
Иначе:
        → Server (по умолчанию, ничего писать не нужно)
```

### Граничные случаи

**Accordion с одним `useState`.** Не превращайте всю страницу в Client. Выделите крошечный Client-компонент `<Accordion>` (заголовок + кнопка + state), а контент внутри передавайте через `children` — они останутся Server, если родитель Server.

```tsx
// page.tsx (Server)
export default async function Page() {
  const article = await fetchArticle(); // server fetch
  return (
    <Accordion title="Подробности"> {/* Client (state) */}
      <ArticleBody html={article.html} /> {/* Server */}
    </Accordion>
  );
}
```

**Контекст в Client-провайдере.** `AuthContext`, `SettingsContext` поднимаются один раз в root layout как `<AuthProvider>` (Client). Дочерние страницы могут оставаться Server — `<AuthProvider>` обёрнут вокруг `{children}` в `layout.tsx`, и React-серверу плевать, что `children` рендерятся Server-side, а провайдер — Client.

### Pattern: leaf-client

Client-компоненты должны быть **листьями** дерева, а не корнями. Если `page.tsx` — Server, а внутри — Client `<TradeFilterBar>`, в котором дальше `<TradeList>` (тоже Client из-за useState), — это уже плохо. `<TradeList>` стоит сделать Server и принимать данные через props, а Client-частью оставить только сам фильтр.

### Empirik антипаттерн прямо сейчас

`src/app/page.tsx` — `'use client'` стоит на корне страницы. Всё, что внутри, — Client, включая `<EquityCurveCard>`, `<StatsGrid>`, `<AppShell>`. Рекомендованный рефактор:

- `src/app/page.tsx` — Server, async, фетчит `stats` и `trades` через server-side `apiClient` (нужно написать)
- `src/components/dashboard/StatsGrid.tsx` — оставить как есть (получает `stats` props), снять `'use client'` если не использует state
- `src/app/page-client.tsx` — Client-обёртка только для модалок и табов

## 3. Server Actions — мутации без API-роута

### Что это

Функции с директивой `'use server'`, вызываемые с клиента как обычные функции, но выполняющиеся на сервере. Под капотом — POST на спец-URL, который Next.js монтирует автоматически.

### Когда использовать в Empirik

Хорошие кандидаты:
- Toggle тега у сделки (`<form action={addTagToTradeAction}>`)
- Переименование setup
- Закрытие сделки одной кнопкой (без модалки)
- Удаление сделки
- Простые формы профиля (изменить имя, аватар)

Плохие кандидаты:
- Импорт CSV (большой payload — пусть идёт прямо в FastAPI)
- AI-аналитика (медленная — нужен progress, лучше через TanStack Query или SSE)
- Подключение брокера (OAuth-flow с редиректами — отдельная история)
- Платежи (критично, нужен прямой POST с retry / idempotency-key)

### Структура

```
src/actions/
  trades.ts        // 'use server' в шапке
  tags.ts
  setups.ts
  profile.ts
src/lib/
  serverApiClient.ts   // server-only fetch к FastAPI с cookies из next/headers
```

`serverApiClient.ts` нужен потому, что `src/lib/apiClient.ts` использует `document.cookie` — это сломается на сервере. На сервере cookies читаются через `import { cookies } from 'next/headers'`.

### Шаблон Server Action

```ts
'use server';

import { z } from 'zod'; // нужно добавить в deps
import { revalidateTag } from 'next/cache';
import { serverApi } from '@/lib/serverApiClient';

const Schema = z.object({
  tradeId: z.coerce.number().int().positive(),
  tag: z.string().min(1).max(50),
});

export async function addTagToTradeAction(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const parsed = Schema.safeParse({
    tradeId: formData.get('tradeId'),
    tag: formData.get('tag'),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? 'Validation failed' };
  }
  try {
    await serverApi.post(`/trades/${parsed.data.tradeId}/tags`, { body: { tag: parsed.data.tag } });
    revalidateTag(`trades:${parsed.data.tradeId}`);
    revalidateTag('trades-list');
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Unknown error' };
  }
}
```

### Прокидывание ошибок: throw vs Result

`throw` в Server Action вызывает client-side error boundary и user-friendly fallback. Хорошо для «совсем плохо» (база упала). Для пользовательских ошибок (дубликат тега, превышен лимит) — возвращайте Result-type `{ ok: false, error: string }`. Тогда `useActionState` отдаст это как `state` без перехода в error boundary.

## 4. Server Actions vs прямой fetch к FastAPI в Empirik

Архитектура Empirik: Next на 3000, FastAPI на 8003. Server Action всё равно идёт через сетевой хоп Next → FastAPI. Это не бесплатно. Когда выбирать что:

| Задача | Что использовать | Почему |
|---|---|---|
| Платежи, удаление аккаунта, 2FA | Прямой POST из Client через `apiClient.ts` | Надо точно знать статус, retry-policy, idempotency-key |
| AI-генерация (долгие) | TanStack Query mutation → FastAPI | Нужен progress, retry, мелкая работа со state |
| Toggle тега, rename setup | Server Action | Минимум boilerplate, `revalidateTag` сам инвалидирует кэш |
| Импорт CSV | Прямой POST из Client | Большой FormData, прогресс upload'а |
| Простой submit формы профиля | Server Action + `<Form action={...}>` | Работает без JS, прогрессивное улучшение |

### Преимущества Server Action в Empirik

1. CSRF-токен и cookies проброс — Next делает сам
2. После мутации `revalidateTag('trades-list')` — и Server Component на дашборде получит свежие данные при следующей навигации, без TanStack Query инвалидации
3. Нет нужды в client-side `setLoading(true) / catch / finally` — `useActionState` даёт `pending`

## 5. Suspense — правильное использование

Suspense — граница, на которой React готов показать `fallback`, пока что-то внутри ещё не готово.

### Где ставить

**Не вокруг всей страницы.** Это эквивалент `<DashboardSkeleton />` который у нас сейчас.

**Вокруг каждой независимо-загружаемой секции.** На дашборде — это `<EquityCurveCard>` отдельно, `<StatsGrid>` отдельно, `<AdvancedStatsGrid>` отдельно. Тогда equity-чарт может появиться через 200ms, а advanced-метрики — через 1.5s, и пользователь не ждёт самую медленную часть.

```tsx
export default function Dashboard() {
  return (
    <AppShellLayout>
      <Suspense fallback={<EquityCurveSkeleton />}>
        <EquityCurveSection />
      </Suspense>
      <Suspense fallback={<StatsGridSkeleton />}>
        <StatsGridSection />
      </Suspense>
      <Suspense fallback={<AdvancedStatsSkeleton />}>
        <AdvancedStatsSection />
      </Suspense>
    </AppShellLayout>
  );
}
```

Каждая `*Section` — Server, async, фетчит свой кусок. Все три fetch'а Next запустит параллельно, но рендер будет поточный.

### loading.tsx

Файл `app/dashboard/loading.tsx` — это автоматический Suspense-fallback на уровне сегмента роута. Полезен для перехода между страницами (пользователь кликнул, шелл уже виден, контент грузится). Не заменяет Suspense внутри — `loading.tsx` показывается **только** при навигации, не при первоначальной загрузке secondary-данных.

### Skeleton fallback

В Empirik уже есть `src/components/Skeleton.tsx` (`<DashboardSkeleton>`, `<TradeHistorySkeleton>`). Используйте их прямо как `<Suspense fallback={<DashboardSkeleton />}>`. Не делайте `null` как fallback — пользователь увидит layout-сдвиг.

## 6. Streaming через loading.tsx и Suspense

### Принцип

Next.js 16 стримит HTML по чанкам: shell приходит мгновенно (header, nav, sidebar), внутри — комментарий-заглушка для каждого Suspense-boundary. По мере того как async-компоненты резолвятся, сервер досылает HTML и `<script>`-инструкцию заменить заглушку.

### Pattern для Empirik

```tsx
// app/page.tsx (Server, async)
export default async function HomePage() {
  // НЕ делать await здесь — иначе шелл не отдадим до конца fetch'а
  return (
    <AppShell>
      <DashboardHeader /> {/* Server, синхронный */}
      <Suspense fallback={<EquityCurveSkeleton />}>
        <EquityCurveSection /> {/* async внутри */}
      </Suspense>
      <Suspense fallback={<StatsGridSkeleton />}>
        <StatsGridSection />
      </Suspense>
    </AppShell>
  );
}

// EquityCurveSection.tsx (Server, async)
async function EquityCurveSection() {
  const data = await serverApi.get<EquityData>('/stats/equity-curve');
  return <EquityCurveCard data={data.curve} />; // EquityCurveCard — Client, recharts
}
```

### Антипаттерн

```tsx
// НЕ ТАК
export default async function HomePage() {
  const stats = await serverApi.get('/stats/'); // блокирует весь рендер
  const trades = await serverApi.get('/trades/'); // блокирует ещё больше
  return <Dashboard stats={stats} trades={trades} />;
}
```

Шелл не будет отдан, пока оба fetch'а не вернутся. Поток разрушен.

### layout.tsx — синхронные данные

В `src/app/layout.tsx` сейчас живут провайдеры. Если когда-нибудь захочется получать `user` на сервере — это **тоже async Server Component**:

```tsx
// layout.tsx
export default async function RootLayout({ children }: ...) {
  const user = await getCurrentUser(); // прочитал cookie, спросил FastAPI /auth/me
  return (
    <html>
      <body>
        <AuthProvider initialUser={user}>{children}</AuthProvider>
      </body>
    </html>
  );
}
```

Сейчас в Empirik `AuthContext` фетчит `/auth/me` сам в `useEffect` — это лишний flicker (сначала пустое, потом залогиненный UI). Server-side проброс убирает это.

## 7. Кэширование Next.js 16

### По умолчанию OFF

В Next.js 16 `fetch()` **не кэшируется по умолчанию**. Это отличие от Next 14. Кэш надо включать явно:

```ts
// TTL-кэш на 60 секунд
const res = await fetch(url, { next: { revalidate: 60 } });

// Тегированный кэш — инвалидируется по revalidateTag
const res = await fetch(url, { next: { tags: ['trades-list', `trade:${id}`] } });

// Полностью статичный (для blog, manual)
const res = await fetch(url, { cache: 'force-cache' });

// Никогда не кэшируется (для personalized data)
const res = await fetch(url, { cache: 'no-store' });
```

### Empirik cookbook

| Endpoint | Стратегия | Почему |
|---|---|---|
| `/stats/` (per-user) | `cache: 'no-store'` | Зависит от user-cookie, кэшировать опасно |
| MOEX котировки в `/marketdata` | `next: { revalidate: 30, tags: ['moex'] }` | Дёшево обновлять раз в 30 сек, но не на каждый рендер |
| `/blog/[slug]` контент | `next: { revalidate: 3600, tags: [`blog:${slug}`] }` | Меняется редко, при публикации админ → revalidateTag |
| `/auth/me` | `cache: 'no-store'` | Personalized |
| `/instruments` справочник | `cache: 'force-cache'` | Меняется крайне редко |

### Инвалидация после мутации

```ts
'use server';
import { revalidateTag, revalidatePath } from 'next/cache';

export async function closeTradeAction(...) {
  await serverApi.patch(`/trades/${tradeId}/close`, ...);
  revalidateTag('trades-list');     // /history, /dashboard перерендерят
  revalidateTag(`trade:${tradeId}`); // конкретная trade-страница
  // или, если несколько роутов и не хочется тегировать:
  revalidatePath('/', 'layout');     // инвалидирует всё
}
```

## 8. TanStack Query vs Server Components

Самый частый вопрос 2026: «у нас уже TanStack Query, зачем Server Components?» Граница такая:

| | Server Components | TanStack Query |
|---|---|---|
| Initial render | Да | Нет (только после hydration) |
| SEO | Да | Нет |
| Client-side кэш | Нет | Да |
| Refetch по событию | Нет | Да |
| Оптимистичные мутации | Через `useOptimistic` | Через `onMutate` + rollback |
| Live-обновления (socket, polling) | Нет | Да |
| Background refetch | Нет | Да |

### Pattern: Server initial → TanStack ownership

```tsx
// app/history/page.tsx (Server, async)
export default async function HistoryPage() {
  const initialTrades = await serverApi.get<Trade[]>('/trades/');
  return <HistoryClient initialTrades={initialTrades} />;
}

// components/HistoryClient.tsx (Client)
'use client';
export function HistoryClient({ initialTrades }: { initialTrades: Trade[] }) {
  const { data: trades } = useQuery({
    queryKey: ['trades'],
    queryFn: () => api.get<Trade[]>('/trades/'),
    initialData: initialTrades,
    staleTime: 30_000,
  });
  // ... интерактивность, фильтры, мутации
}
```

Что получили:
- Initial HTML с реальными сделками (SEO, мгновенный first paint)
- TanStack Query сразу после hydration считает данные свежими (`staleTime: 30s`), не делает дубль-fetch
- Все мутации/инвалидации работают через QueryClient как обычно
- Если `revalidateTag('trades-list')` сработал из Server Action — `initialTrades` обновится при следующем визите страницы, и `initialData` будет новый

### Что в Empirik оставить на TanStack

- Live-portfolio (`PortfolioCard`) — polling каждые 30s
- Notifications в шапке
- Live trade updates пока торговая сессия открыта
- AI-аналитика с прогрессом

## 9. React 19 features

### `use()` хук

Заменяет `useEffect + setState` для async данных в Client-компонентах. Может вызываться **условно** (в отличие от других хуков).

```tsx
'use client';
import { use } from 'react';

export function TradeAIAnalysis({ tradePromise }: { tradePromise: Promise<AIAnalysis> }) {
  const analysis = use(tradePromise); // suspends, пока promise не resolved
  return <AIVerdictCard data={analysis} />;
}

// page.tsx (Server)
export default function Page() {
  const aiPromise = serverApi.get('/ai/analysis'); // НЕ await — promise отдаём в Client
  return (
    <Suspense fallback={<Skeleton />}>
      <TradeAIAnalysis tradePromise={aiPromise} />
    </Suspense>
  );
}
```

### `useTransition` и `startTransition`

Для тяжёлых state updates без блокировки UI. В Empirik пригодится при смене периода в `<EquityCurveCard>`:

```tsx
const [isPending, startTransition] = useTransition();
const onPeriodChange = (p: Period) => {
  startTransition(() => setPeriod(p)); // не блокирует input
};
```

### `<Form action={serverAction}>`

Нативная интеграция. Без JS — обычный POST. С JS — Server Action. Прогрессивное улучшение бесплатно.

```tsx
import Form from 'next/form'; // для client-navigation
// или нативный <form action={...}> для submit с server action
```

### `useOptimistic`

Оптимистичный UI без TanStack Query. Подходит для мелких toggle'ов:

```tsx
const [optimisticTags, setOptimistic] = useOptimistic(
  tags,
  (state, newTag: string) => [...state, newTag],
);
```

### `forwardRef` больше не нужен

В React 19 `ref` — обычный prop:

```tsx
// React 18:
const Input = forwardRef<HTMLInputElement, Props>((props, ref) => <input ref={ref} {...props} />);

// React 19:
function Input({ ref, ...props }: Props & { ref?: Ref<HTMLInputElement> }) {
  return <input ref={ref} {...props} />;
}
```

Почистите по проекту: `grep -r forwardRef src/` и убирайте.

### Document metadata

`<title>`, `<meta>` могут жить прямо в компоненте — React автоматически hoist'ит их в `<head>`. Но для SEO Next.js `export const metadata` остаётся предпочтительным.

## 10. TypeScript strict паттерны

### PageProps в Next.js 16

`params` и `searchParams` теперь `Promise`:

```ts
type PageProps = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function Page({ params, searchParams }: PageProps) {
  const { slug } = await params;
  const sp = await searchParams;
  // ...
}
```

### Action state

```ts
export type ActionState =
  | { ok: true; data?: unknown }
  | { ok: false; error: string; fieldErrors?: Record<string, string> };
```

### Branded types для ID

```ts
export type TradeId = number & { readonly __brand: 'TradeId' };
export type SetupId = number & { readonly __brand: 'SetupId' };
export const tradeId = (n: number): TradeId => n as TradeId;
```

Не дадут случайно передать `setupId` в `closeTrade(tradeId)`.

### Zod на границах

Все Server Action inputs и все парсинги fetch-response'ов — через Zod. У Empirik уже есть `openapi-typescript` для типов из FastAPI — это чисто **типы**, не **runtime-валидация**. На бэкенд можно доверять, но Server Action input от пользователя — нет.

### Без `as`

`as` — это эскейп от системы типов. Используйте `satisfies`, type predicates, Zod, type narrowing. Если `as` всё-таки нужен — комментарий `// TODO why`.

## 11. Recharts + Server Components

Recharts ломается на сервере (нужен `window`). Empirik это уже понимает (`EquityCurveCard.tsx` помечен `'use client'`). Правильный паттерн:

```tsx
// app/dashboard/equity/page.tsx (Server)
export default async function EquityPage() {
  const data = await serverApi.get<EquityCurve>('/stats/equity-curve');
  return <EquityChartClient data={data} />;
}

// components/EquityChartClient.tsx (Client)
'use client';
import { ResponsiveContainer, LineChart, ... } from 'recharts';
export function EquityChartClient({ data }: { data: EquityCurve }) {
  return <ResponsiveContainer>...</ResponsiveContainer>;
}
```

### dynamic import

Для совсем тяжёлых чартов (heatmap, treemap), которые видны не на каждой странице:

```ts
import dynamic from 'next/dynamic';
const HeatmapChart = dynamic(() => import('./HeatmapChart'), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});
```

Это уберёт чарт из main-bundle и из server-render полностью.

## 12. Производительность Empirik frontend

### Bundle size

Каждый `'use client'` тянет код в bundle. По состоянию на сейчас все 21 страниц + 100+ компонентов в bundle. Реалистичные цели рефактора:

- `app/blog/[slug]/page.tsx` → Server (контент статичный)
- `app/manual/page.tsx` → Server
- `app/help/page.tsx` → Server
- `app/pricing/page.tsx` → Server
- `app/page.tsx` (guest landing) → Server, авторизованную часть — Client под Suspense

### Code-splitting модалок

`AddTradeModal`, `CloseTradeModal`, `ImportPreviewModal`, `BrokerConnectModal`, `DepositManagerModal`, `SetupManagerModal`, `SettingsModal` — 7 модалок импортируются eagerly в `app/page.tsx`. Все 7 в bundle, даже если пользователь ничего не открыл. Решение:

```ts
const AddTradeModal = dynamic(() => import('@/components/AddTradeModal').then(m => m.AddTradeModal));
```

### `next/image`

В коде есть `import Image from 'next/image'` (`history/page.tsx`), но в guest-landing `app/page.tsx` `<img>` не используется — там только иконки lucide. На скриншотах сделок (`/journal/screenshots`) — проверить, используется ли next/image; если `<img>` — заменить.

### `next/font`

Уже используется (`Geist`, `Geist_Mono` в `layout.tsx`). Хорошо, не трогаем.

## 13. Полезные snippet'ы

### `noStore()` — отключить кэш в Server Component

```ts
import { unstable_noStore as noStore } from 'next/cache';

export default async function Page() {
  noStore(); // эта страница никогда не статична
  const data = await serverApi.get('/stats/');
  return <Dashboard stats={data} />;
}
```

### `cookies()` и `headers()`

```ts
import { cookies, headers } from 'next/headers';

export async function getCurrentUser() {
  const c = await cookies(); // Next 16: Promise
  const sessionCookie = c.get('session');
  if (!sessionCookie) return null;
  const h = await headers();
  const csrfHeader = h.get('x-csrf-token');
  // ...
}
```

### `redirect()` и `notFound()`

```ts
import { redirect, notFound } from 'next/navigation';

export default async function TradePage({ params }: PageProps) {
  const { id } = await params;
  const trade = await serverApi.get(`/trades/${id}`).catch(() => null);
  if (!trade) notFound();
  if (trade.user_id !== currentUserId) redirect('/');
  return <TradeView trade={trade} />;
}
```

### `generateStaticParams` для блога

```ts
// app/blog/[slug]/page.tsx
export async function generateStaticParams() {
  const posts = await serverApi.get<{ slug: string }[]>('/blog/posts');
  return posts.map(p => ({ slug: p.slug }));
}
```

Next сгенерит страницы на build-time, дальше — холодный CDN.

## 14. Чек-лист перед PR

- [ ] Любой `'use client'` обоснован: state, event handler, browser API, или зависимость требует Client (recharts, cmdk, framer-motion)
- [ ] `<Suspense>` вокруг каждой независимо-загружаемой части (не одна обёртка вокруг всей страницы)
- [ ] После каждой мутации в Server Action — `revalidateTag` или `revalidatePath`
- [ ] Нет `any` без TODO-комментария
- [ ] Нет `as Type` без обоснования
- [ ] TanStack Query использован только для интерактивности (live, refetch). Initial render — Server Component
- [ ] `dynamic()` для тяжёлых Client-компонентов, которые видны не сразу
- [ ] `params`/`searchParams` типизированы как `Promise<...>`
- [ ] Server Action input провалидирован через Zod
- [ ] Recharts/cmdk/framer-motion — только в Client-листьях, не в page.tsx
- [ ] `loading.tsx` рядом с тяжёлыми `page.tsx`
- [ ] Для personalized данных — `cache: 'no-store'` или `noStore()`
- [ ] Для статичного контента — `revalidate` + `tags`

## Примеры

См. `examples/`:

1. `server_action_example.tsx` — Server Action добавления тега к сделке (Zod, revalidateTag, useActionState, useOptimistic)
2. `streaming_page_example.tsx` — дашборд со streaming через 4 независимых Suspense
3. `suspense_chart_example.tsx` — Server fetches data, Client renders Recharts (паттерн для всех чартов Empirik)

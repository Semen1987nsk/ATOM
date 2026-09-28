# ADR-0003: Server Components — точечная миграция, не «всё разом»

**Статус:** Принято и продемонстрировано (PR4 от 2026-05-07)
**Контекст PR:** Аудит выявил, что 21/21 страниц фронта помечены `'use client'`. `app/page.tsx` (1013 строк) делает `Promise.all([api.get('/stats/'), api.get('/trades/')])` блокируя shell на ~800 ms.

## Контекст

Next.js 16 + React 19 поддерживают Server Components, Suspense streaming, Server Actions. У нас:
- TanStack Query уже используется для server-state на клиенте
- Auth — httpOnly cookies на FastAPI, нужен passthrough
- Recharts требует Client (canvas + интерактивность)
- Сложный AppShell со state в Client (sidebar, modals)

**Соблазн:** мигрировать всё разом на Server-first.
**Риск:** сломать рабочий дашборд, потерять TanStack-кеширование, провалить сроки.

## Решение

**Гибридная стратегия. Не рефакторим существующее — добавляем Server-secciones рядом.**

1. **Создаём `serverApiClient.ts`** — Server-only fetch wrapper с passthrough auth-cookies (`atom_access_token`, `atom_refresh_token`, `atom_csrf_token`) через `next/headers.cookies()`.
2. **Демо-страница `/dashboard-demo`** — отдельный URL, не трогая `/`. Показывает паттерн: 1 Suspense вокруг 1 Server Component-секции.
3. **EquityCurveCard остаётся Client** (Recharts) — но получает `data` как props, не фетчит сам.
4. **AppShell остаётся Client** (sidebar state, modals) — Client-родитель не «заражает» Server-children через `{children}`.

**Когда мигрируем существующий `/`:**
- После того как пользователь увидит работающее `/dashboard-demo` и решит «давай так же на главной»
- Только тогда — секциями, не разом

## Последствия

**Плюсы:**
- Нулевой риск для рабочего дашборда
- Демонстрация паттерна на изолированной странице
- Возможность А/B-теста «старая `/` vs новая `/dashboard-demo`»
- Build success, route помечен `ƒ Dynamic` (Server-rendered on demand)

**Минусы / риски:**
- Дублирование кода в течение переходного периода
- Команда должна знать оба паттерна (Client + Server)

## Поведенческие правила

1. **Чарты = Client.** Recharts/D3 требуют canvas, всегда `'use client'`. Но получают данные через props, не фетчат сами.
2. **Server Component не может содержать `useState`/`useEffect`/`onClick`.** Если нужно — выноси интерактивную часть в Client-компонент-листок.
3. **`cache: 'no-store'`** для финансовых данных (котировки, /stats). Кешировать можно только blog/manual/help.
4. **Cookies passthrough** — обязательно через `next/headers.cookies()`. `credentials: 'include'` на Server-fetch не работает.

## BACKEND_URL — нюанс

`apiClient.ts` (Client) дефолтит на `http://localhost:8003`.
`serverApiClient.ts` дефолтит на `http://localhost:8000`.

**Источник истины:** `frontend/.env.local` → `BACKEND_URL=...`. Если порты разойдутся — фронт упадёт.

## Связанные ADR

- Будущий ADR-NNNN «Полная миграция `/` на Server» — когда подтвердим успех `/dashboard-demo`

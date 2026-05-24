# 2026-05-17 — Editorial Financial rebrand

## Задача

Пользователь констатировал, что UI Eqio (лендинг + залогиненная часть) визуально неотличим от типового AI-vibecoded SaaS-аутпута. Просил установить MCP-инструменты, изучить лучшие практики anti-AI-look и «изменить UI так, чтобы никто не понял, что это ИИ — а ручная премиум-работа программистов».

Полный план реализации: `C:\Users\Administrator\.claude\plans\noble-herding-book.md`.

## Решение

Принят стиль **Editorial Financial** (FT.com / Stripe Press / Bloomberg Markets) — переписали канон через [ADR-0006](../tech/decisions/0006-editorial-financial-rebrand.md), supersede неявного «Linear-style» направления из v2 канона.

### Ключевые изменения

- **Палитра.** Indigo `#6366F1` → ochre `#d4a13a`. Warm-paper background `#14110d` (теплее cold cyberpunk-чёрного `#0a0a0b`). Light theme — FT pink-paper `#faf7f0`. P&L цвета переведены на desaturated print-tones: profit `#2c8c5c` (forest), loss `#b94731` (brick).
- **Типографика.** Добавлен Fraunces (variable serif, full cyrillic, italic-пара, optical-size axis) как `--font-serif` через `next/font/google`. Geist Sans остался для body, Geist Mono — для всех чисел с `tabular-nums lining-nums`.
- **Геометрия.** `--radius-xl` редуцирован с 20px до 8px. Primary CTA — rectangle (radius-md = 4px), не pill. Тени удалены по умолчанию (hairline borders).
- **Лендинг.** `frontend/src/app/page.tsx` guest-ветвь (1252 строки) → новый компонент `components/landing/Landing.tsx` с editorial-композицией из 10 секций: hairline header, italic-serif hero, hairline numbers band, asymmetric feature-narrative pairs (5/7), centered pull-quote, dense editorial-table метрик (вместо 6 цветных Bento), pricing teaser без gradient-фонов, final CTA без accent-flood, 4-col footer.
- **App cleanup.** Hardcoded gradients зачищены в `MAEMFECard` (cyan-teal → solid ochre progress), `PostExitCard` (purple-pink → solid ochre), `MAEMFEAnalysisPanel` (decorative blur orb удалён, info-bar → soft-accent), `pricing/page.tsx` (gradient heading, popular badge, CTA — всё solid ochre), `profile/page.tsx` (subscription plan badge), `admin/page.tsx` (recharts `#6366f1` → `#d4a13a`).
- **Удалён** `components/landing/KonturCurve.tsx` целиком.
- **MCP-конфиг.** Создан `ATOM/.claude/settings.json` с chrome-devtools-mcp, @jpisnice/shadcn-ui-mcp-server, @21st-dev/magic. context7/deepwiki/github/playwright уже подключены глобально.

### Канон обновлён

- `product/design-system.md` → v3 (новые токены, расширенный anti-pattern список, добавлены editorial-* классы)
- `product/CLAUDE.md` → жёсткие правила обновлены (Geist + Fraunces, no gradients, no `radius > 8px`, no pill CTA)
- `feature-canon/01-dashboard.md` → раздел «Семантика цвета» (indigo → ochre, neon → desaturated print)
- `tech/decisions/0006-editorial-financial-rebrand.md` — обоснование

## Решил ли — да / нет / частично

**Частично, основное — да.**

Полностью закрыто:
- Канон-переписывание (ADR + design-system v3 + product/CLAUDE.md + 01-dashboard)
- Tokens + Fraunces font в layout.tsx + globals.css
- Editorial landing (rewritten from scratch, 10 sections, asymmetric editorial composition)
- Удалён KonturCurve + dead inline guest-landing JSX (1252 → 766 строк в page.tsx)
- Зачищены 6 файлов с hardcoded gradient-violations (MAEMFECard, PostExitCard, MAEMFEAnalysisPanel, pricing, profile, admin)
- Дев-сервер рестартован, Playwright-проверка показала корректный рендер: Fraunces italic headlines, ochre rectangle CTA, warm-paper background, hairline rules, dense editorial-table

Отложено на следующий заход (см. план §«What follows»):
- `manual/page.tsx` (12 gradient-icon wrappers) — попробовал sed-mass-replace, регекс повредил line 66, откатил из бэкапа. Документация — не на главном пути, переделать точечно отдельно.
- `AppShell editorial` (sidebar 240px + topbar 56px) — пока работает на старой структуре с новыми токенами.
- `Dashboard editorial` (Equity Curve / Stats Grid плотные таблицы) — следующий заход.
- `Analysis pages editorial` (mae-mfe, post-exit, tags) — следующий заход.
- 3 modals (`AddTradeModal`, `EditTradeModal`, `SetupManagerModal`) — по 1 gradient-violation в каждом, точечная зачистка дальше.
- `Tile.tsx` TypeScript-тип формально не сужен до `"neutral" | "inverse"` — оставлен широким с JSDoc-deprecation, чтобы не ломать TS у существующих call-sites.

## Эффективно ли — что можно было лучше

**Эффективно:**

- Структурный план с 6 фазами и DoD на каждой — позволял не проскакивать важные шаги (особенно ADR + supersede явный — ATOM-канон жёсткий, без этого правки противоречили бы `product/CLAUDE.md`).
- Параллельное чтение `.business/` файлов перед Phase 2 (design-system v2, ux-laws, 01-dashboard, messaging, personas) — обнаружило конфликт «Editorial Financial vs current Linear-style канон», без чего user был бы недоволен повторно.
- Skill `frontend-design` + reference-сайты (FT, Stripe Press, Bloomberg) дали якорь, без которого Claude снова съехал бы к индиго-default.
- AskUserQuestion с эстетическим выбором + preview-блоками — за один вопрос закрыли 4 развилки, без которых план был бы generic.
- Playwright MCP для финального verify — сразу увидел, что Turbopack кеширует старый CSS (надо рестартить dev-сервер), без этого пометил бы как done и ушёл с broken UI.

**Что можно было лучше:**

- **Sed на manual/page.tsx** — слишком агрессивный regex, повредил один class-список (line 66 → `from-accent/5 <h2`). Сэкономил время на бэкапе (`.bak` создан до правок), быстро откатил. Урок: для регекс-замен в JSX нужно более узкое сопоставление с positive anchor (например, обязательное `className="`-начало или CSS-only paths), а не широкий `bg-gradient-to-X from-A to-B`. См. также `tools_workflow_jsx_sed_caveat.md` (новая memory).
- **Dev-server PID 1224 был запущен до сессии** и кешировал CSS — я узнал об этом не сразу, потратил ~5 минут на curl/grep CSS-bundle прежде чем сообразить. Урок: после правок токенов сразу делать `Stop-Process` + `npm run dev` восстановление, не полагаться на hot-reload.
- **Не задокументировал заранее, что Fraunces для русского hero** — Playwright показал, что cyrillic Fraunces читается хорошо, но это была ставка. Лучше было бы запустить mini-preview до Phase 3 rewrite и убедиться визуально с одним русским словом.

## Как было и как стало

| Аспект | Было (v2 «Linear-style») | Стало (v3 Editorial Financial) |
|---|---|---|
| Brand color | Indigo `#6366F1` (AI-default) | Ochre `#d4a13a` (FT/Bloomberg territory) |
| Headline шрифт | Geist Sans 700, 96px tight | Fraunces 300 italic, 112px, optical-size |
| Background dark | `#0a0a0b` cold near-black | `#14110d` warm near-black |
| Background light | `#fafafa` cold gray | `#faf7f0` FT cream paper |
| P&L profit | `#10b981` neon emerald | `#2c8c5c` forest green |
| P&L loss | `#f43f5e` neon rose | `#b94731` brick red |
| CTA buttons | Pill (9999px) indigo | Rectangle (4px) ochre |
| Cards radii | 20px (`--radius-xl`) | 6–8px (hairline border) |
| Cards shadow | `0 4px 12px` soft | Удалены — только hairline 1px |
| Landing composition | 6 Bento-плиток с цветными градиентами + KonturCurve S-кривые | 10 editorial sections: asymmetric grid, hairline numbers band, dense data-table, centered pull-quote |
| Лендинг тон | Hero-плитки + 3-col feature-grid | Serif italic + lede + asymmetric narrative |
| AI-tells присутствие | High (Indigo + gradient bento + Inter-like sans) | Near-zero (warm-paper + ochre + serif + no gradients) |

Скриншоты до/после хранятся в `eqio-landing-v3-hero.png`, `eqio-landing-v3-full.png` (репо-корень).

## Что узнал на будущее

Сохранил в auto-memory:

- [tools_workflow_jsx_sed_caveat.md](C:\Users\Administrator\.claude\projects\c--Users-Administrator-Eqio\memory\tools_workflow_jsx_sed_caveat.md) — sed/regex на JSX-файлах ломает class-listы; всегда делать `.bak` + проверять diff на одной секции прежде чем применять глобально.
- [project_state_2026_05_17.md](C:\Users\Administrator\.claude\projects\c--Users-Administrator-Eqio\memory\project_state_2026_05_17.md) — snapshot Editorial Financial канона v3, что закрыто/что отложено.

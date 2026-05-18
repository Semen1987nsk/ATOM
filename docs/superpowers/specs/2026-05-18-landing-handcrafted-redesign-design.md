# Landing hand-crafted redesign — design spec

**Дата:** 2026-05-18
**Автор:** sarvanidi87@gmail.com + Claude (brainstorming через superpowers)
**Статус:** approved (готов к implementation plan)
**Связанные документы:**
- [BRAND.md](../../../../BRAND.md) — канон бренда МААТТ
- [LANDING_COPY.md](../../../../LANDING_COPY.md) — копирайт лендинга (МААТТ)
- [REBRAND.md](../../../../REBRAND.md) — план ребрендинга Eqio → МААТТ
- Текущая реализация: [src/components/landing/Landing.tsx](../../../frontend/src/components/landing/Landing.tsx) (Editorial Financial v3, ADR-0006)

---

## 1. Цель

Поднять текущий лендинг (Editorial Financial v3, dark mode, ASCII-моки) до уровня **«видно ручную работу инженера-дизайнера»**, одновременно выполняя rebrand на МААТТ.

**Что user отверг в текущем v3:**
1. ASCII-моки вместо настоящих визуалов
2. Страница мёртвая (нет «живых» моментов)
3. Типографика верхне-средняя (Fraunces есть, но без drop-cap, marginalia, font-variation tuning)
4. Бренд МААТТ не рассказан (на лендинге всё ещё «Eqio»)

**Что НЕ цель:**
- Не пересмотр копирайта (LANDING_COPY.md остаётся каноном)
- Не пересмотр архитектуры frontend (Next.js 16, App Router, RSC)
- Не темная тема (отдельный спринт)
- Не /manifesto страница (cut-in на главной достаточно)
- Не testimonials с реальными фото (юзеров реальных пока нет)

---

## 2. Direction решения

| Ось | Выбор | Альтернативы |
|---|---|---|
| **Стартовая точка** | Iterate v3 hand-crafted | Hybrid Hero only / полный редизайн |
| **Бренд** | МААТТ — rebrand сразу | Eqio остаётся / hybrid visual без имени |
| **Палитра** | C — Cream / soft papyrus (`#FAF8F2`) | A — Papyrus canon / B — Dark ink+gold |
| **Характер** | B — Trader Desk (live ticker + mini equity curve) | A — Editorial Quarterly / C — Manuscript Modern |

---

## 3. Информационная архитектура

Лендинг — single page, 14 секций сверху вниз:

| # | Секция | Размер | Hand-craft момент |
|---|---|---|---|
| 1 | **Header** (sticky) | h-16 | Custom wordmark Fraunces italic «МААТТ», перо-favicon, nav |
| 2 | **Live ticker MOEX** | h-9 | Real prices через API, pulse-индикатор, fallback static |
| 3 | **Hero** | ~85vh | H1 + lede + 2 CTA + mini SVG equity curve справа |
| 4 | **Numbers band** | py-12 | 30+ метрик · 10 000 МК · 60 сек · 399₽ с monospace + footnotes |
| 5 | **Manifest cut-in** | py-20 | Pull-quote «Каждая сделка измерена. Каждое решение взвешено.» |
| 6 | **Раздел 01 · AI-разбор** | py-24 lg:py-32 | Editorial 5/7, **реальный PNG-скриншот** AI-карточки |
| 7 | **Раздел 02 · MAE/MFE** | py-24 lg:py-32 | Editorial 7/5, **интерактивный SVG candle chart** SBER |
| 8 | **Раздел 03 · Trade Replay** ⭐ | py-24 lg:py-32 | Новая. **Slider по таймлайну** на свечах, точки entry/exit |
| 9 | **Pull-quote** | py-20 | «Перестал гадать. Начал считать.» — drop-cap + золотая полоса |
| 10 | **Раздел 04 · Метрики таблицей** | py-24 | Editorial table, footnote-ссылки на работы Винса/Тарпа |
| 11 | **МААТТ-история** ⭐ | py-32 | Новая. Custom SVG-перо + marginalia origin-story |
| 12 | **Pricing teaser** | py-24 | Free / Pro, без изменений в копирайте, типографика подтянута |
| 13 | **Final CTA** | py-32 lg:py-40 | Editorial h1 + одна кнопка |
| 14 | **Footer** | py-16 | 4 колонки, МААТТ wordmark, контакты, 152-ФЗ |

**Δ vs текущий v3:**
- ⊕ live MOEX ticker (секция 2)
- ⊕ Trade Replay секция (8)
- ⊕ МААТТ-история секция (11)
- ⊖ ASCII-моки удалены везде
- ↻ Numbers band переоформляется в footnote-стиль (была flat-сетка)
- ↻ Pull-quote получает drop-cap (была без)

---

## 4. Компоненты — что новое, что меняется

### 4.1 Новые компоненты (frontend)

```
src/components/landing/
├── Landing.tsx                      ← перекомпонован (пере-разметка)
├── parts/                           ⭐ новая папка
│   ├── LiveTicker.tsx               ⭐ client-component, real API + fallback
│   ├── HeroEquityCurve.tsx          ⭐ SVG, static data из JSON snapshot
│   ├── InteractiveCandleChart.tsx   ⭐ client SVG + hover tooltip
│   ├── TradeReplayWidget.tsx        ⭐ client SVG + slider
│   ├── ManuscriptFeather.tsx        ⭐ SVG-иллюстрация перо
│   ├── ManifestCutIn.tsx            ⭐ pull-quote + decorative rule
│   └── MaattOrigin.tsx              ⭐ marginalia + feather + text
└── data/
    ├── ticker-fallback.ts           ⭐ статические prices на случай fail
    ├── hero-equity-snapshot.ts      ⭐ cohort-anonymous equity curve
    ├── sber-candles-2026-04-21.ts   ⭐ MOEX свечи для MAE/MFE секции
    └── trade-replay-sample.ts       ⭐ свечи + точки для replay секции
```

### 4.2 Backend (FastAPI)

```
backend/app/routers/landing.py       ⭐ новый router
  GET /api/landing/ticker            → 5 symbols через moex_iss_client, 60s cache
```

- Cache layer: `functools.lru_cache` + TTL через `cachetools.TTLCache(maxsize=1, ttl=60)`
- Symbols hardcoded: `SBER, GAZP, LKOH, YNDX, IMOEX`
- Если MOEX API down — endpoint возвращает 200 + флаг `stale: true` + последний known good
- Если cache пуст и API down — 503 (клиент покажет fallback static)

### 4.3 Public assets

```
public/landing/
├── og-image-maatt.png               ⭐ 1200×630 для OG/Twitter
├── favicon-feather.svg              ⭐ перо как favicon
├── ai-card-sber-screenshot.png      ⭐ playwright capture с cohort-данными
└── trade-replay-sample.png          ⭐ static fallback для mobile (slider скрыт)
```

---

## 5. Hero — детальная композиция

### 5.1 Layout

Grid 12-col, gap-6, max-width 1200px:

```
┌────────────────────────────────────────────────────────┐
│ col 1-7                          │ col 8-12            │
│                                  │                     │
│ eyebrow: ── Журнал сделок · MOEX │  ╭─────────────╮    │
│                                  │  │ equity SVG  │    │
│ h1: Системная торговля           │  │ (cohort)    │    │
│     начинается *с дневника.*     │  │  · · · · •  │    │
│                                  │  ╰─────────────╯    │
│ lede: Тридцать с лишним...       │   caption italic    │
│                                  │                     │
│ [CTA primary]  [secondary text]  │                     │
└────────────────────────────────────────────────────────┘
```

Mobile (<lg): equity curve уходит ПОД CTA, занимает full-width, h-32.

### 5.2 Типографические решения

- H1: Fraunces variable, weight 350, size clamp(44px, 6vw, 88px), `font-variation-settings: "opsz" 144, "SOFT" 30`, line-height 0.94, letter-spacing -0.025em. **«с дневника»** italic, остальное roman.
- Lede: Fraunces italic, weight 300, size 18px, line-height 1.55, max-width 36ch, color `--ink-2`
- Eyebrow: JetBrains Mono, size 11px, letter-spacing 0.18em, uppercase, color `--ink-3`
- CTA primary: Inter 500, size 14px, padding 12px 22px, background `--ink`, color `--paper`
- CTA secondary: Inter 400, size 13px, color `--ink-2`, hover `--accent`

### 5.3 Mini equity curve

- Размер: 280×140px desktop, full-width × 128px mobile
- Data: 60 точек cohort-anonymous, нормализованных к 0..100
- Stroke: 1.4px, color `--ink`, terminal dot `--accent` (r=3)
- Filled gradient под кривой: from `--ink` 18% → 0% opacity
- Caption под кривой: «cohort · 60 закрытых сделок · апрель 2026» — Fraunces italic 11px `--ink-3`
- Без анимации reveal (editorial-чистота)

---

## 6. Three live moments (anti-mertvost contract)

| # | Где | Что | Технология | Fallback |
|---|---|---|---|---|
| 1 | LiveTicker (секция 2) | Real MOEX prices, пульс на 1-м тикере | TanStack Query 60s refetch + `/api/landing/ticker` | Static prices из `ticker-fallback.ts`, без пульса |
| 2 | InteractiveCandleChart (секция 7) | Hover на свечу → tooltip с MAE/MFE точками | SVG + `<title>` + onMouseMove | Static state визуала, tooltip скрыт |
| 3 | TradeReplayWidget (секция 8) | Slider по таймлайну, маркеры entry/exit/stop/take перемещаются | `<input type="range">` + reactive SVG | Static screenshot на mobile (slider hidden) |

**Что не делаем (out of scope для live):**
- scroll-triggered animations (`framer-motion` в секциях)
- card reveal на scroll
- typewriter / counter-up на цифрах
- parallax
- cursor-follow

Микро-анимации только на link hover (underline draw 150ms) и CTA hover (subtle press translate 1px).

`prefers-reduced-motion: reduce` — пульс выключается, slider остаётся (это контрол, не декор).

---

## 7. Палитра tokens (cream)

Добавляются в `frontend/src/app/globals.css` в `:root`:

```css
/* МААТТ Editorial Cream — landing palette */
--paper:           #FAF8F2;
--ink:             #14110B;
--ink-2:           rgba(20, 17, 11, 0.62);
--ink-3:           rgba(20, 17, 11, 0.40);
--rule:            rgba(20, 17, 11, 0.08);
--rule-strong:     rgba(20, 17, 11, 0.20);
--accent:          #B58A2F;
--accent-hover:    #9B7424;
--accent-soft:     rgba(181, 138, 47, 0.10);
--profit:          #1F6A47;
--loss:            #A03A2A;
```

**Важно:** эти tokens действуют ТОЛЬКО на guest landing (`/` для unauthenticated). Auth dashboard сохраняет текущие `--background/--foreground/--accent` без изменений — это отдельный design system (см. ADR-0006 + `globals.css` структуру).

Реализация изоляции: `<Landing>` оборачивается в `<div data-theme="maatt-cream">`, который переопределяет токены через `[data-theme="maatt-cream"] { ... }`.

---

## 8. Типографика

### 8.1 Шрифты (Next.js `next/font`)

```ts
// src/app/layout.tsx
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";

const fraunces = Fraunces({
  subsets: ["latin", "cyrillic"],
  variable: "--font-serif",
  axes: ["opsz", "SOFT", "WONK"],
  weight: ["300", "400", "500"],
  style: ["normal", "italic"],
  display: "swap",
});
```

Inter и JetBrains Mono — без variable axes, standard weights `400`, `500`.

### 8.2 Variation patterns

| Контекст | font-variation-settings |
|---|---|
| H1 / Hero display | `"opsz" 144, "SOFT" 30` |
| H2 секционный | `"opsz" 96, "SOFT" 20` |
| Lede italic | default |
| Pull-quote | `"opsz" 144, "SOFT" 40, "WONK" 1` |
| Marginalia | default italic |

Это даёт визуально-разные «голоса» одного шрифта — основа editorial-feel.

---

## 9. Бренд МААТТ — distribution

| Где | Что | Notes |
|---|---|---|
| Header wordmark | «МААТТ» Fraunces italic 22px | Не emoji, не пиктограмма |
| Favicon | SVG-перо стилизованное, одна линия | `public/landing/favicon-feather.svg` |
| Manifest cut-in (секция 5) | «Каждая сделка измерена. Каждое решение взвешено.» | Pull-quote, Fraunces 48px |
| МААТТ-история (секция 11) | Большая SVG-перо + marginalia origin story | Единственное место со «сложной» иллюстрацией |
| OG image | МААТТ wordmark + tagline + перо | 1200×630, статика |
| Footer wordmark | «МААТТ» 20px italic | Контакты `hello@maatt.ru`, `support@maatt.ru` |

**НЕ используем:**
- emoji 𓆄 (вместо — кастомная SVG)
- иероглифы для UI / иконок
- золотую рамку вокруг всего
- gradient overlays «папируса» как текстуру (попахивает stock)

---

## 10. Реальные визуалы — production pipeline

| Asset | Источник | Подготовка |
|---|---|---|
| `og-image-maatt.png` | Дизайн в figma либо HTML→PNG | Скрипт `scripts/build-og-image.ts` через playwright headless |
| `favicon-feather.svg` | Авторская SVG | Inline, hand-tuned, 64×64 viewbox, 1-2 path |
| `ai-card-sber-screenshot.png` | Реальный `/trades/[id]` с тестовым trade | playwright capture, cohort-anonymized data |
| `sber-candles-2026-04-21.ts` | MOEX ISS API запрос | Скрипт `scripts/snapshot-moex-candles.ts`, snapshot SBER 1h за 21.04 |
| `trade-replay-sample.ts` | Same MOEX + manual entry/exit points | Конфиг trade + автогенерация |
| `hero-equity-snapshot.ts` | Cohort анонимная статистика | Скрипт берёт 60 случайных закрытых trades из dev DB, нормализует |

Все snapshot-скрипты — в `scripts/landing-assets/`, идемпотентные, запускаются вручную и коммитятся.

---

## 11. Перформанс, accessibility, responsive

### 11.1 Performance budgets

- **LCP** < 1.8s (Hero виден без блокирующего fetch — equity curve и Hero текст рендерятся как RSC)
- **CLS** < 0.05 (ticker reserves space, fonts via `font-display: swap` + Next.js preload)
- **TBT** < 200ms (нет тяжёлого JS в SSR; client-компоненты lazy-loaded)
- Bundle delta для лендинга: <30KB gzip над текущим (только LiveTicker + 2 SVG-компонента)

### 11.2 Accessibility

- Ticker pulse уважает `prefers-reduced-motion`
- Slider Trade Replay имеет `aria-label`, `aria-valuetext`, keyboard nav (← →)
- Candle chart tooltip имеет focus-trap equivalent для keyboard юзеров
- Все CTA имеют видимый focus ring (`outline: 2px solid var(--accent)`)
- Контраст `--ink` на `--paper` = 16.2:1 (AAA), `--ink-2` на `--paper` = 9.8:1 (AAA)

### 11.3 Responsive breakpoints

- `<md` (mobile): ticker → horizontal scroll, hero equity → под CTA, Trade Replay → static PNG
- `md..lg`: те же, но шрифты на 1 ступень больше; equity curve справа от Hero text
- `≥lg`: полная композиция

---

## 12. Скоуп этой итерации

### IN scope

1. Перекомпонован `Landing.tsx` под новую IA (14 секций)
2. 7 новых компонентов в `src/components/landing/parts/`
3. Новый API endpoint `/api/landing/ticker` + cache layer
4. Cream-палитра tokens в `globals.css` (изолированно через `[data-theme]`)
5. Шрифты Fraunces (variable) + Inter + JetBrains Mono через `next/font`
6. Snapshot-скрипты для MOEX данных в `scripts/landing-assets/`
7. Public assets (OG image, favicon, AI screenshot)
8. Rebrand на МААТТ (wordmark в header/footer, email-домен, OG)
9. SEO meta из LANDING_COPY.md
10. Тесты:
    - Visual regression на Hero + 3 anchor секции (Playwright)
    - Unit: `LiveTicker` fallback path, `InteractiveCandleChart` tooltip, `TradeReplayWidget` slider
    - Backend: `landing.py` endpoint cache + 503 fallback

### OUT of scope (follow-ups)

- Темная тема (отдельный design exercise)
- Анимированный intro Hero (motion design отдельно)
- Видео-демо продукта
- `/manifesto` отдельная страница
- Реальные testimonials с фото и атрибуцией
- Замена `Eqio` на `МААТТ` ВНУТРИ дашборда (auth zone) — это шаг REBRAND фазы 2 (см. REBRAND.md)
- Регистрация доменов `maatt.ru` / OAuth callback на новый домен — фаза 0 ребрендинга

### Ассумпции

- BRAND.md и LANDING_COPY.md остаются каноном — копирайт не пересматривается
- Темная тема не нужна для launch (можно жить с light-only пока)
- Cohort-данные для Hero equity curve можно сгенерировать из dev DB
- MOEX ISS API доступен из production (как и сейчас для дашборда)
- `data-theme="maatt-cream"` не конфликтует с существующими scope-стилями

---

## 13. Тесты

### 13.1 Backend (pytest)

```python
# backend/tests/test_landing_router.py
def test_ticker_returns_5_symbols_on_happy_path(client):
    r = client.get("/api/landing/ticker")
    assert r.status_code == 200
    assert {"SBER", "GAZP", "LKOH", "YNDX", "IMOEX"} == {t["symbol"] for t in r.json()["tickers"]}
    assert r.json()["stale"] is False

def test_ticker_returns_stale_on_moex_failure(client, mock_moex_down):
    # первый вызов наполнил кэш
    client.get("/api/landing/ticker")
    # MOEX упал
    mock_moex_down.activate()
    r = client.get("/api/landing/ticker")
    assert r.status_code == 200
    assert r.json()["stale"] is True

def test_ticker_returns_503_on_cold_cache_failure(client, mock_moex_down):
    mock_moex_down.activate()
    r = client.get("/api/landing/ticker")
    assert r.status_code == 503
```

### 13.2 Frontend (Vitest + Testing Library)

```typescript
// src/components/landing/parts/__tests__/LiveTicker.test.tsx
it("shows fallback prices when API returns 503", async () => { ... });
it("displays pulse indicator on first symbol when not reduced-motion", () => { ... });
it("hides pulse when prefers-reduced-motion: reduce", () => { ... });

// src/components/landing/parts/__tests__/InteractiveCandleChart.test.tsx
it("renders MAE/MFE markers on hover", async () => { ... });
it("shows tooltip with correct R values", async () => { ... });

// src/components/landing/parts/__tests__/TradeReplayWidget.test.tsx
it("updates marker positions as slider moves", async () => { ... });
it("supports keyboard navigation (← →)", async () => { ... });
```

### 13.3 Visual regression (Playwright)

```typescript
// e2e/landing-visual.spec.ts
test("Hero matches snapshot @ 1440px", async ({ page }) => { ... });
test("MAE/MFE section matches snapshot @ 1440px", async ({ page }) => { ... });
test("Trade Replay section matches snapshot @ 1440px", async ({ page }) => { ... });
test("Full page matches snapshot @ 375px (mobile)", async ({ page }) => { ... });
```

---

## 14. Out-of-band риски

| Риск | Митигация |
|---|---|
| MOEX ISS rate-limit при наплыве трафика на ticker | 60s server cache + fallback на static при `429` |
| Fraunces variable cyrillic — не все glyphs доступны | Проверить «МААТТ», все Cyrillic в копирайте; fallback Georgia |
| `data-theme` isolation течёт в dashboard | Снапшот-тест на dashboard перед/после; добавить `eslint` правило что landing-компоненты не импортируются вне `/components/landing` |
| Trade Replay slider тормозит при быстром движении | Использовать `useDeferredValue`, target 60fps |
| Favicon SVG не работает в Safari < 15 | Дублировать `.png` fallback (16, 32, 192) |
| OG image скрипт ломается при изменении дизайна | Версионировать `og-image-maatt.png` в репо, не fetching на runtime |

---

## 15. Готовность

✅ Архитектура — approved
✅ Hero композиция — approved
✅ Палитра + типографика — approved
✅ Три live-момента — approved
✅ Бренд distribution — approved
✅ Реальные визуалы pipeline — approved
✅ Скоуп vs follow-ups — approved

**Next step:** invoke `superpowers:writing-plans` для создания implementation plan, где каждая из 14 секций + 7 компонентов получит отдельный шаг с TDD-разбивкой.

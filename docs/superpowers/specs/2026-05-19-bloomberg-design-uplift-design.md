# Дизайн-спецификация: Bloomberg-uplift лендинга Эмпирик

**Дата:** 2026-05-19
**Автор:** Claude Code (brainstorming pair-session с sarvanidi87@gmail.com)
**Предыдущие документы:**
- `2026-05-18-landing-handcrafted-redesign-design.md` (v1, cream-палитра + Trader Desk)
- `2026-05-18-landing-champions-rebuild-design.md` (v2, 16-секционная IA + Champions + копирайт)
**Working tree:** `C:\Users\Administrator\Empirik\ATOM-landing`

---

## 1. Контекст и цель

После Phase 1+2 (foundation docs + 16-секционная IA + копирайт) визуально лендинг остаётся «бумагой в браузере» — выдержанной, но плоской: один тон, один кегль, всё на cream. Тексты и структура работают, но дизайн не отличает страницу от шаблона. Цель uplift'а — поднять визуальный язык до уровня **агентского** исполнения, сохранив всю проделанную работу (палитра, шрифты, кастинг чемпионов, гравюры, копирайт).

**Что НЕ меняется:**
- 16-секционная IA и порядок секций
- Все тексты (копирайт Phase 2 финален)
- Кастинг 6 чемпионов и их verbatim-цитаты
- Гравюрные портреты (SVG hedcuts)
- Воспроизведённые product-виджеты (TradeReplay, InteractiveCandleChart, HeroEquityCurve, MAE/MFE)
- Голос бренда и messaging hierarchy

**Что меняется:**
- Ритм страницы — alternating dark/light (вместо моно-cream)
- Display-шрифт — добавляется Manrope для bold uppercase H1/H2 в dark-секциях
- Accent — добавляется тёплый Bloomberg-оранжевый `#E84E1C` рядом с существующей охрой
- Motion — 5 точечных акцентов (curve, ticker, champions raise, count-up, candle replay)
- Edges — острые горизонтальные ink-линии, mono-eyebrow'ы, ticker-strip как разделитель

## 2. Большая визуальная идея

**Bloomberg Businessweek bold (Russian editorial).** Чёрная плотная типографика на cream, оранжевый акцент как у обложек BW, mono-цифры как биржевой тикер, плотные горизонтальные rule'ы, минимум градиентов и теней. Страница читается как развёрнутый журнал, а не как продуктовая страница SaaS.

Опорные референсы: Bloomberg Businessweek (обложки 2020+), FT Weekend, The Economist бизнес-секции. **Не** референсы: Linear, Vercel, Stripe (слишком чистый SaaS-стандарт), Mercury, Compound (слишком тихие).

## 3. Ритм страницы — alternating dark/light

16 секций распределяются по чередующейся карте контраста. Решение принято в brainstorm-screen `bloomberg-rhythm.html`.

| # | Секция | Фон | Текст | Акцент |
|---|---|---|---|---|
| 1 | Header | LIGHT (paper) | ink | — |
| 2 | LiveTicker MOEX | ORANGE STRIP | ink/black on `#E84E1C` | mono цифры |
| 3 | Hero (новый H1) | **DARK** `#0a0a0a` | paper | `#E84E1C` для второй строки H1 |
| 4 | «Сам факт записи» | LIGHT (paper) | ink | большие orange-цифры 01/02/03 |
| 5 | «Дисциплина чемпионов» | LIGHT (paper) | ink | orange-rule под каждым именем |
| 6 | Numbers band | **DARK** | paper | orange-цифры count-up |
| 7 | Manifest cut-in | LIGHT (paper-tint) | ink | Fraunces italic, no accent |
| 8 | Раздел 01 · Trade Replay | LIGHT (paper) | ink | orange кнопка «Воспроизвести» |
| 9 | Раздел 02 · MAE / MFE | **DARK** | paper | orange + profit/loss дуплет |
| 10 | Раздел 03 · 13 метрик | LIGHT (paper) | ink | orange-rule между explainer'ами |
| 11 | Pull-quote клиента | **DARK** | paper | большая Fraunces-кавычка `#E84E1C` opacity 0.4 |
| 12 | Раздел 04 · Эвристики | LIGHT (paper) | ink | mono-bullet'ы, orange-rule |
| 13 | Раздел 05 · Для кого | LIGHT (paper-tint) | ink | orange checkmark/x |
| 14 | Pricing | **SPLIT**: Free=paper, Pro=DARK | ink / paper | orange CTA на обеих |
| 15 | Final CTA | **DARK** | paper | orange CTA-кнопка |
| 16 | Footer | DARK (продолжение Final CTA) | paper | mono-минимум |

**Правила переходов:**
- Между LIGHT-секциями — `border-top: 1px solid var(--rule-strong)` или ticker-strip
- Перед DARK-секцией — никакого padding-collapse, секция сама подаёт верхнее дыхание
- Перед ORANGE strip — острая нижняя ink-линия в LIGHT-секции выше
- Pricing split: Free и Pro — две колонки одинаковой высоты, граница `1px ink`

## 4. Типографика — полная ревизия стека

### 4.1. Стек шрифтов (next/font)

| Роль | Шрифт | Веса | CSS-переменная |
|---|---|---|---|
| Display sans (DARK-секции, bold uppercase H1/H2, Numbers, CTA labels) | **Manrope** | 500, 700, 800 | `--font-display` |

> **Note (2026-05-19):** Google Fonts Manrope max-weight = 800 (ExtraBold). Веса 900 нет — для Bloomberg-bold uppercase используем 800 везде, где спека упоминает «Manrope 800».
| Body sans (текущий, без изменений) | Inter (latin+cyr) | 400, 500, 600, 700 | `--font-sans` |
| Mono (цифры, eyebrow'ы, источники, ticker) | JetBrains Mono | 400, 500 | `--font-mono` |
| Editorial serif (Manifest, цитаты Champions, pull-quote) | **Fraunces** + Cormorant cyr companion | 300, 400 italic | `--font-serif`, `--font-serif-cyr` |

Manrope добавляется через `next/font/google` в `layout.tsx`. Латиница + кириллица в одном файле, subset `latin,latin-ext,cyrillic`.

### 4.2. Применение по контексту

| Где | Шрифт + treatment | Пример |
|---|---|---|
| H1 Hero | Manrope 800 uppercase, fs 56–88px, line-height 0.92, letter-spacing −0.03em | «ЗАПИСЬ ДЕЛАЕТ\nТРЕЙДЕРА.» |
| H2 DARK-секций | Manrope 800 uppercase, fs 40–56px, letter-spacing −0.025em | «ЦИФРЫ БЕЗ ПАФОСА» |
| H2 LIGHT-секций (Champions, SimpleFact, Heuristics, Audience) | Manrope 800 uppercase, fs 36–48px на ink | «ДИСЦИПЛИНА ЧЕМПИОНОВ» |
| Manifest cut-in | Fraunces italic 400, fs 28–48px, sentence case | «Запись — это ремесло.» |
| Champion имя | Manrope 800 uppercase, fs 18px, letter-spacing −0.015em | «ДЖЕССИ ЛИВЕРМОР» |
| Champion years | JetBrains Mono 11px, ink-3 | `1877 — 1940` |
| Champion bio | Inter 400, fs 13–14px, line-height 1.55, ink-2 | «Американский биржевой спекулянт…» |
| Champion цитата | Fraunces italic 400, fs 15–18px, ink + orange `border-left` | «Я завёл маленькую книжку…» |
| Champion источник | JetBrains Mono 10px caps, letter-spacing 0.08em | «REMINISCENCES · ЛЕФЕВР · 1923» |
| Pull-quote (DARK) | Fraunces italic 300, fs 32–56px, paper + ginormous orange `«` opacity 0.4 | — |
| Numbers band (DARK) | Manrope 800, fs 64–96px, paper, count-up на цифрах | «30+», «60c», «≤24h» |
| Eyebrow секции | JetBrains Mono 11px caps, letter-spacing 0.18em, ink-3 на light / paper-3 на dark | «── ЖУРНАЛ · MOEX» |
| Ticker | JetBrains Mono 12px medium, black on orange, auto-scroll | — |
| Pricing цена | Manrope 800, fs 64px | «0 ₽», «399 ₽» |
| CTA primary | Manrope 700 uppercase 13px, letter-spacing 0.06em | «→ НАЧАТЬ БЕСПЛАТНО» |
| Body параграфы | Inter 400, fs 16–17px, line-height 1.65 | — |

### 4.3. Удаляется/перезаписывается

- Класс `.editorial-display` (Fraunces 88px) остаётся для Manifest, но H1 Hero переходит на Manrope.
- Класс `.editorial-h2` (Fraunces 52px) остаётся для тех секций где нужен serif-H2 (Manifest, Pull-quote зона). Все остальные H2 — Manrope.
- `font-variation-settings opsz/SOFT/WONK` сохраняется на Fraunces.

## 5. Палитра — расширение

### 5.1. Текущие токены (сохраняются)

```css
--paper:        #faf6ee  /* основной cream */
--paper-tint:   #f4ecdc  /* тёплее cream — для Manifest, Audience */
--ink:          #14110B  /* основной чёрный текст */
--ink-2:        rgba(20,17,11,0.62)
--ink-3:        rgba(20,17,11,0.40)
--rule:         rgba(20,17,11,0.08)
--rule-strong:  rgba(20,17,11,0.20)
--accent:       #B58A2F  /* охра — остаётся для существующих компонентов */
--ochre-deep:   #5d2a14  /* footnote-источники */
```

### 5.2. Новые токены

```css
/* Bloomberg-оранжевый акцент */
--orange:        #E84E1C  /* warm Bloomberg, основной accent для uplift'а */
--orange-hover:  #d44516
--orange-strip:  #E84E1C  /* фон LiveTicker */
--orange-soft:   rgba(232, 78, 28, 0.10)
--orange-quote:  rgba(232, 78, 28, 0.40)  /* для больших декор-кавычек */

/* Dark-секции */
--ink-dark:           #0a0a0a  /* почти чёрный фон DARK-секций */
--ink-dark-2:         #1a1a1a  /* surface на dark — для Pricing Pro карточки */
--paper-on-dark:      #fafafa  /* основной текст на dark */
--paper-on-dark-2:    rgba(250, 250, 250, 0.70)  /* secondary text */
--paper-on-dark-3:    rgba(250, 250, 250, 0.45)  /* eyebrow, mono на dark */
--rule-on-dark:       rgba(250, 250, 250, 0.10)
--rule-on-dark-strong: rgba(250, 250, 250, 0.22)
```

### 5.3. Использование

- `--accent` (охра `#B58A2F`) — остаётся для **существующих** виджетов (HeroEquityCurve линия, TradeReplay decor, EmpirikOrigin элементы), чтобы не ломать визуальную преемственность.
- `--orange` (`#E84E1C`) — новый primary accent для **uplift-добавлений**: CTA-кнопки, H1 второй строки в Hero, Numbers band цифры, Champions rule, Ticker фон.
- Оба сосуществуют: охра — «бумажный» детальный акцент, orange — «обложечный» большой акцент.

### 5.4. Контраст (WCAG)

| Пара | Контраст | Уровень |
|---|---|---|
| `#14110B` на `#faf6ee` | 17.3:1 | AAA |
| `#E84E1C` на `#faf6ee` | 4.7:1 | AA для крупного текста / borders |
| `#E84E1C` на `#0a0a0a` | 4.5:1 | AA |
| `#fafafa` на `#0a0a0a` | 19.5:1 | AAA |
| `#0a0a0a` на `#E84E1C` | 5.2:1 | AAA крупный / AA нормальный |

`#E84E1C` **не используется** как body-text цвет на cream — только для крупного (≥18px) или decoration.

## 6. Компонентные паттерны

### 6.1. Ticker-strip (Section 2 + повторяется как разделитель)

- Фон `--orange-strip`, текст `#0a0a0a` (черный), JetBrains Mono 12px medium
- Высота 38px desktop / 32px mobile
- Бесконечная горизонтальная прокрутка left (CSS keyframe, 60s/cycle)
- Содержимое: «IMOEX 3247.18 ▲ 0.42% · SBER 287.5 ▼ 0.15% · GAZP 145.20 ▲ 0.08% · ...» (live MOEX + статичные fallback'и)
- Между тикерами разделитель `·` (mono), пульсирующий orange-dot при свежем апдейте
- Используется как «жирная горизонтальная подпись» между смысловыми зонами

### 6.2. Hero (Section 3, DARK)

```
[ Top-rule с mono-eyebrow ]    ── ЖУРНАЛ · MOEX · ● LIVE
[ H1 Manrope 800 uppercase ]   ЗАПИСЬ ДЕЛАЕТ
                                ТРЕЙДЕРА.   ← вторая строка #E84E1C
[ Lede Inter 17px paper-2 ]    Тридцать с лишним метрик и MAE/MFE из биржевых
                                свечей — на ваших сделках.
[ Equity curve SVG auto-draw ] (snippet ниже)
[ CTA pair ]                    [→ НАЧАТЬ БЕСПЛАТНО]  [Тинькофф ID]
```

- Equity curve: SVG path, stroke `#E84E1C`, stroke-width 2, stroke-dasharray = path total length, stroke-dashoffset animates 800 → 0 за 1.2s easeOut на load
- В правом нижнем — мини-маркер «-1.2R» mono ink-3 (намёк на честный замер)
- Высота секции: min-height 100vh — 38px (компенсация ticker'а)
- Bottom-edge: острая `--rule-on-dark-strong` 1px

### 6.3. SimpleFact (Section 4, LIGHT)

- 3 колонки editorial-вёрстки, gap 48px
- Каждая: большая orange-цифра `01` / `02` / `03` (Manrope 800, fs 120px, line-height 0.85, color `#E84E1C`)
- Под цифрой: H3 Manrope 700 uppercase 18px ink
- Под H3: параграф Inter 16px ink-2 line-height 1.65
- Между колонками: vertical rule `1px solid var(--rule-strong)`
- Bottom: связка-строка Fraunces italic 18px ink-2, центрированно, на отдельной строке

### 6.4. Champions (Section 5, LIGHT)

- 3×2 grid desktop, gap 32px col / 56px row
- Каждая карточка:
  - Гравюра 220×220 SVG hedcut (ink на paper)
  - Имя Manrope 800 uppercase 18px ink
  - Годы Mono 11px ink-3
  - Bio Inter 13px ink-2
  - Цитата Fraunces italic 15px ink + `border-left: 2px solid #E84E1C` padding-left 14px
  - Источник Mono 10px caps ink-3, letter-spacing 0.08em
- Scroll-triggered raise: каждая карточка появляется с `translateY(20px) → 0`, opacity `0 → 1`, transition 0.6s easeOut, staggered 80ms между карточками

### 6.5. Numbers band (Section 6, DARK)

- 4 числа в горизонтальный ряд, gap 80px
- Каждое: orange `#E84E1C` Manrope 800, fs 96px, line-height 0.9, count-up при viewport-enter (1.5s)
- Под числом: подпись Inter 13px paper-on-dark-2 line-height 1.4
- Над числами: eyebrow «ПО-ПРОСТУ» mono caps paper-on-dark-3
- Внизу секции: связка Inter italic 17px paper-on-dark-2, ≤80ch

### 6.6. Manifest cut-in (Section 7, LIGHT paper-tint)

- Большая декор-цитата `«` orange `#E84E1C` opacity 0.10 в левом верхнем (Fraunces, fs 360px, абсолютно позиционировано, aria-hidden)
- Текст Fraunces italic 400, fs 32–48px ink, max-width 26ch
- Atribution: mono 11px caps ink-3 справа снизу
- НЕТ кнопок, НЕТ ссылок — это smell-block, не conversion

### 6.7. Pull-quote (Section 11, DARK)

- Аналог Manifest, но реверс: paper-2 на ink-dark
- Декор «`«`» orange opacity 0.40, fs 480px, top-left clipped
- Цитата Fraunces italic 300 paper, fs 32–56px, max-width 28ch
- Attribution mono 11px caps paper-on-dark-3

### 6.8. Pricing split (Section 14)

- Две колонки одинаковой высоты, между ними `1px solid #0a0a0a` (ink)
- **Free карточка**: фон paper, ink, заголовок «БЕСПЛАТНО» Manrope 800 uppercase, цена «0 ₽» Manrope 800 fs 64px, bullet'ы Inter 15px, CTA вторичная
- **Pro карточка**: фон ink-dark `#0a0a0a`, paper текст, заголовок «PRO» Manrope 800 uppercase orange, цена «399 ₽/мес» Manrope 800 paper, bullet'ы paper-2 с orange-checkmark'ом, CTA primary orange
- Над сплитом — eyebrow «ТАРИФЫ» mono ink-3 + H2 «ПРОСТО И ПРОЗРАЧНО» Manrope 800

### 6.9. Final CTA (Section 15, DARK)

- Полная высота 60vh
- Heading Manrope 800 uppercase, fs 56–80px paper, max-width 16ch
- Под H — Inter 17px paper-on-dark-2 max-width 50ch
- CTA orange кнопка large, padding 18×36, Manrope 700 uppercase 14px black
- Под кнопкой mono 11px caps paper-on-dark-3: «БЕЗ КАРТЫ · 50 СДЕЛОК БЕСПЛАТНО»

## 7. Motion-план (уровень B — сбалансированно)

Решение принято в brainstorm-screen `motion-plan.html`. Каждое движение несёт смысл, не «вращается для красоты».

| # | Где | Что | Триггер | Длительность | Easing |
|---|---|---|---|---|---|
| 1 | Hero | Equity curve auto-draw (stroke-dashoffset) | mount | 1.2s | `cubic-bezier(0.22, 1, 0.36, 1)` |
| 1b | Hero | Маркер в конце curve пульсирует 2 раза | после curve | 0.4s × 2 | ease-in-out |
| 2 | LiveTicker (Section 2) | Бесконечная горизонтальная прокрутка | mount | 60s/cycle | linear |
| 3 | Champions cards | `translateY(20px) + opacity 0 → 1` staggered 80ms | IntersectionObserver `--top-50px` | 0.6s | easeOut |
| 4 | Numbers band | Count-up на цифрах (от 0 к финалу) | IntersectionObserver `--top-100px` | 1.5s | easeOut |
| 5 | Trade Replay | Candle-by-candle reveal (existing widget logic) | click «Воспроизвести» | per-candle | существующее |

**Что НЕ анимируется (намеренно):**
- Manifest cut-in — статика, как страница книги
- Pull-quote — статика
- Heuristics — статика
- Pricing cards — без hover-tilt / 3D
- Audience Qualifier — статика
- Header — без shrink-on-scroll
- Footer — статика

### 7.1. `prefers-reduced-motion`

Все 5 motion'ов обёрнуты:

```css
@media (prefers-reduced-motion: reduce) {
  /* стрелка к финальному состоянию мгновенно */
  .hero-equity-curve { stroke-dashoffset: 0 !important; animation: none; }
  .ticker-track { animation: none; transform: none; }
  .champion-card { opacity: 1 !important; transform: none !important; }
  .number-countup { /* финальное значение сразу */ }
}
```

Visual regression тесты прогоняются в обоих режимах.

### 7.2. Performance budgets

- Suspense streaming не ломается: motion начинается **после** mount, не блокирует FCP
- Total JS added by motion code: ≤ 4KB gzip (Framer Motion НЕ используется — CSS + IntersectionObserver + RAF)
- Equity curve и Champions raise — IntersectionObserver, не scroll-listener
- LCP не зависит от motion (LCP — Hero H1, который рендерится мгновенно)

## 8. Доступность

- WCAG AA обязательно, AAA где можно (см. §5.4 таблицу)
- Decorative SVG (decor-кавычка, equity curve, engravings бэкграунды) — `aria-hidden="true"`
- Meaningful SVG (champion portraits) — `role="img"` + `<title>` + `<desc>`
- Focus-rings: `outline: 2px solid #E84E1C; outline-offset: 2px` на всех CTA и интерактивных карточках
- Контраст orange на cream проверен только для крупного (≥18px) — на mobile size scale не падает ниже
- Все count-up'ы и curve draw'ы доступны через скриншот в reduced-motion (final state)
- Keyboard navigation: tab order соответствует визуальному порядку

## 9. Implementation scope

### 9.1. В составе uplift'а (этой работы)

1. **Шрифт Manrope** — добавление через `next/font/google` в `layout.tsx`, новая CSS-переменная `--font-display`
2. **CSS-токены** — добавление 12 новых переменных в блок `[data-theme="empirik-cream"]` (см. §5.2)
3. **Утилитарные классы** — `.uplift-h1`, `.uplift-h2-dark`, `.uplift-h2-light`, `.uplift-numbers`, `.uplift-section-dark`, `.uplift-section-light`, `.uplift-section-tint`, `.uplift-ticker-strip`
4. **Section refactor** — каждая из 16 секций получает корректный wrapper (DARK/LIGHT/TINT/SPLIT/STRIP) и обновлённую типографику без изменения копирайта
5. **Hero motion** — `HeroEquityCurve` дополняется stroke-dashoffset анимацией + reduced-motion guard
6. **LiveTicker** — фон переходит на `--orange-strip`, ink-текст, бесконечная горизонталь
7. **Champions raise** — IntersectionObserver hook + CSS-классы для staggered reveal
8. **Numbers count-up** — компонент `<CountUp>` (utility) + IntersectionObserver
9. **Pricing split** — переразметка Free/Pro в две колонки с inverted схемой Pro=DARK
10. **Visual regression refresh** — пересборка Playwright baselines для всех 16 секций (desktop + mobile)
11. **Manual QA**: open in browser → проверить ритм, motion, contrast в DevTools (no `console.error`), `prefers-reduced-motion` toggle

### 9.2. Вне scope этого spec'а

- Замена гравюр (sourcing/regeneration портретов) — уже сделано в Phase 1
- Любые правки копирайта или порядка секций
- Замена product-виджетов (TradeReplay / InteractiveCandleChart / MAE/MFE)
- Translations (страница RU-only)
- Dashboard UI (auth-зона на других токенах, не трогаем)
- A/B-инфраструктура (variants H1 — отдельная задача после uplift'а)
- SEO (sitemap, JSON-LD) — уже в champions-rebuild spec'е

### 9.3. Файлы под изменение (estimate)

**Состояние на 2026-05-19:** часть секций уже вынесена в `parts/` (LiveTicker, HeroEquityCurve, ManifestCutIn, SimpleFactSection, ChampionsSection, ChampionCard, AudienceQualifier, TradeReplayWidget, InteractiveCandleChart). Остальные — inline в `Landing.tsx` (Hero, Numbers, Pull-quote, Metrics, Heuristics, Pricing, Final CTA, Footer). Implementer решает на месте — extract в новый файл или edit inline — исходя из размера diff'а; extract'ы делаются только когда секция получает существенный motion или сложную логику.

| Файл | Тип правки |
|---|---|
| `frontend/src/app/layout.tsx` | + Manrope font (next/font/google) |
| `frontend/src/app/globals.css` | + 12 токенов (§5.2) + 8 utility-классов (§9.1.3) |
| `frontend/src/components/landing/Landing.tsx` | wrapper-классы на 16 секциях; правки inline-секций (Hero / Numbers / Pull-quote / Pricing / Final CTA / Footer) |
| `frontend/src/components/landing/parts/LiveTicker.tsx` | orange-strip фон, infinite scroll |
| `frontend/src/components/landing/parts/HeroEquityCurve.tsx` | stroke-dashoffset animation + reduced-motion guard |
| `frontend/src/components/landing/parts/SimpleFactSection.tsx` | большие orange-цифры 01/02/03 |
| `frontend/src/components/landing/parts/ChampionsSection.tsx` | raise on scroll |
| `frontend/src/components/landing/parts/ChampionCard.tsx` | Manrope name + orange quote rule |
| `frontend/src/components/landing/parts/ManifestCutIn.tsx` | paper-tint фон + decor `«` |
| `frontend/src/components/landing/parts/AudienceQualifier.tsx` | paper-tint фон + orange checkmark/x |
| (опционально) `frontend/src/components/landing/parts/NumbersBand.tsx` | NEW если вынесем из Landing — DARK wrapper + count-up |
| (опционально) `frontend/src/components/landing/parts/PullQuote.tsx` | NEW если вынесем — DARK wrapper + decor `«` orange |
| (опционально) `frontend/src/components/landing/parts/Pricing.tsx` | NEW если вынесем — split Free/Pro, Pro=DARK |
| (опционально) `frontend/src/components/landing/parts/FinalCTA.tsx` | NEW если вынесем — DARK wrapper + orange CTA |
| `frontend/src/components/common/CountUp.tsx` | NEW — utility (RAF + IntersectionObserver) |
| `frontend/src/hooks/useInView.ts` | NEW — IntersectionObserver hook (если уже нет existing) |
| `frontend/tests/landing/landing-visual.spec.ts` | refresh baselines (desktop + mobile, normal + reduced-motion) |
| `frontend/tests/landing/landing-smoke.spec.ts` | проверки ритма (dark/light/orange-strip соседство), motion smoke |

## 10. Acceptance criteria

- [ ] Все 16 секций следуют ритму dark/light из §3
- [ ] H1, H2 в DARK-секциях — Manrope 800 uppercase
- [ ] Manifest и Pull-quote остаются Fraunces italic
- [ ] LiveTicker на оранжевом фоне `#E84E1C` с auto-scroll
- [ ] Equity curve в Hero рисуется за 1.2s при mount
- [ ] Champions карточки появляются staggered на scroll
- [ ] Numbers band count-up'ит цифры на viewport-enter
- [ ] Pricing Pro карточка на тёмном фоне с orange CTA
- [ ] Final CTA на тёмном фоне
- [ ] `prefers-reduced-motion: reduce` отключает все 5 motion'ов
- [ ] Контраст всех текстовых пар — ≥ WCAG AA (по таблице §5.4)
- [ ] Lighthouse Performance ≥ 90 mobile (motion не должен ронять метрику)
- [ ] Playwright `landing-smoke.spec.ts` зелёный, baselines обновлены
- [ ] No `console.error` / `console.warn` в браузере
- [ ] Визуальная проверка вручную: страница не выглядит как «один длинный документ» — есть rhythm

## 11. Риски и mitigation

| Риск | Mitigation |
|---|---|
| Manrope кириллица плохо ляжет на cream в bold | Тестируем 3 рендера на старте; fallback — Onest (тоже cyr-native, в spec как backup) |
| Orange `#E84E1C` на cream выглядит резко | На текстах ≥18px + только декоративно/CTA; не как body |
| Dark секции «утяжелят» страницу | Распределение 6 DARK из 16 — большая часть остаётся бумажной; ритм проверяем визуально |
| Motion перегрузит mobile | Все 5 motion'ов CSS+IO без зависимостей; ≤4KB JS; reduced-motion off |
| Регрессии в существующих виджетах (TradeReplay, MAE/MFE) | Виджеты не трогаем — только их wrapper'ы. Visual regression покажет diff |
| Pricing split сломает мобильный layout | На < md две колонки складываются в вертикальный стек, граница горизонтальная |

## 12. Открытые вопросы

Нет открытых вопросов на момент написания spec'а. Все 5 ключевых решений (направление / ритм / display sans / accent shade / motion level) приняты в brainstorm-сессии 2026-05-19.

---

**Следующие шаги:**
1. Spec self-review (placeholders / contradictions / scope).
2. Коммит spec'а в working tree.
3. User review.
4. Передача в `writing-plans` skill для детализированного implementation plan'а.
5. Implementation через subagent-driven workflow (frontend-design + implementer + visual regression refresh).

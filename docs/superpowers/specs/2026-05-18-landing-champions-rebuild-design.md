# Дизайн-спецификация: пересборка лендинга МААТТ v2 (Champions)

**Дата:** 2026-05-18
**Автор:** Claude Code (brainstorming pair-session с sarvanidi87@gmail.com)
**Связанные документы:** `2026-05-18-landing-handcrafted-redesign-design.md` (v1, базовая cream-палитра + Trader Desk характер)
**Working tree:** `C:\Users\Administrator\Eqio\ATOM-landing`

---

## 1. Контекст и цель

Лендинг МААТТ в текущем виде (16 секций после v1, см. `Landing.tsx`) технически фокусируется на «системной торговле» и продуктовых фичах (MAE/MFE, 30+ метрик, Trade Replay). Конверсия упирается в то, что новый посетитель не понимает **ценности дневника как такового** — до всякой автоматики.

Пересборка добавляет два новых смысловых блока ниже Hero и переписывает все 14 существующих секций через маркетинг-агентов и копирайтеров — чтобы лендинг рассказывал:

1. **Что даёт сам факт ведения дневника** (до всяких метрик/ИИ).
2. **Кто и как вёл дневник из великих** (Ливермор, Дарвас, Минервини, Дракенмиллер, Элдер, Найман).
3. **Что МААТТ автоматизирует этот дневник** для трейдера MOEX.

## 2. Большая идея

Спокойный H1 в духе **«запись = edge»** (вариант C из brainstorming Q1): сам факт регулярной записи сделок отделяет трейдера от игрока — до всяких метрик и ИИ. Сразу под Hero — отдельный блок **«Дисциплина чемпионов»** с цитатами знаменитых трейдеров.

Tone-shift с «техническая платформа» → «спокойное утверждение о ремесле».

## 3. Информационная архитектура (16 секций)

| # | Секция | Статус | Цель |
|---|---|---|---|
| 1 | Header | keep | Навигация |
| 2 | Live Ticker MOEX | keep | «Биржа живая» |
| 3 | Hero (новый H1) | rewrite | Спокойное утверждение ценности дневника |
| 4 | **«Сам факт записи»** | NEW | 3 подпункта: *видишь / признаёшь / сравниваешь* |
| 5 | **«Дисциплина чемпионов»** | NEW | 6 имён × гравюра × цитата с источником |
| 6 | Numbers band | rewrite | Мост к продукту: 4 числа без пафоса |
| 7 | Manifest cut-in | rewrite | Афоризм под big idea |
| 8 | Раздел 01 · Trade Replay | rewrite copy | Виджет тот же |
| 9 | Раздел 02 · MAE / MFE | rewrite + glossary | Inline-словарик |
| 10 | Раздел 03 · Метрики (все 13) | expand explainers | Сейчас 4 → раскрыть все 13 |
| 11 | Pull-quote клиента | rewrite | Сменить цитату под big idea |
| 12 | Раздел 04 · Эвристики | reframe | Бейдж «AI-разбор · скоро» (мелким), основной фрейм — детерминированные правила |
| 13 | Раздел 05 · Для кого МААТТ | rewrite через CRO | Уточнение объекций |
| 14 | Pricing teaser | rewrite | Anchor pricing проверка |
| 15 | Final CTA | rewrite | Короткий, под big idea |
| 16 | Footer | minimal tweak | Tagline пересмотр |

### 3.1. Новая секция 4 — «Сам факт записи»

Три колонки, editorial-вёрстка с крупными цифрами 01/02/03 или буквицами. Без иконок.

| 01 — Ты видишь сделки | 02 — Ты признаёшь ошибки | 03 — Ты сравниваешь себя с собой |
|---|---|---|
| Не помнишь — видишь. Память врёт. Запись — нет. | Не оправдываешь — признаёшь. Цифра не спорит. | Не с рынком — с собой. Квартал к кварталу. |

Под колонками 1 строка-связка: *«Это всё, что нужно. Метрики и алгоритмы — уже сверху.»*

Copywriter перепишет через `mkt-copywriting` skill — текущий черновик не финален.

### 3.2. Новая секция 5 — «Дисциплина чемпионов»

Кастинг (финален после Q3-Q4 brainstorming + Checkpoint 1 решений):

| # | Имя | Годы | Источник цитаты |
|---|---|---|---|
| 1 | Джесси Ливермор | 1877–1940 | «Воспоминания биржевого спекулянта», Лефевр (1923) |
| 2 | Николас Дарвас | 1920–1977 | «Как я заработал $2,000,000 на бирже» (1960) |
| 3 | Марк Минервини | р. 1965 | «Думай как чемпион биржи», CMT Association profile |
| 4 | Пол Тюдор Джонс | р. 1954 | «Market Wizards», Schwager (1989) + «Trader» (PBS, 1987) |
| 5 | Александр Элдер | р. 1950 | «Как играть и выигрывать на бирже» (Trading for a Living, 1993) |
| 6 | Линда Брэдфорд Рашке | р. 1959 | «Trading Sardines» (2018) + «Street Smarts» (Connors & Raschke, 1995) |

**Изменения от первоначального кастинга (Checkpoint 1, 2026-05-18):**
- Эрик Найман → Линда Брэдфорд Рашке (verifiable journaling quote не найдена у Наймана; Раш ke — daily review + post-trade analysis discipline, единственная женщина в касте)
- Стэнли Дракенмиллер → Пол Тюдор Джонс (у Дракенмиллера thesis memos, не journal; PTJ — canonical legal-pad practice)
- Александр Элдер: р. 1932 → р. 1950 (фактическая ошибка по Wikidata)

**Layout:** 3×2 grid desktop / 2×3 tablet / 1×6 mobile.

**Анатомия карточки:**
- Гравюра 220×220 (stipple/hatch SVG, ч/б на cream)
- Имя — Fraunces italic 26pt
- Годы — JetBrains Mono 12pt ink-3
- Биография 1–2 предложения, ≤60 слов
- Цитата verbatim — Fraunces italic 15pt
- Источник — JetBrains Mono 11pt caps

**Constraint для research-агента:** verbatim-цитаты с прямой ссылкой на источник (книга/страница/интервью/таймкод). Если verifiable нет — флаг, заменяем человека. Не выдумывать.

## 4. Голос бренда

Архетипы: **Sage + Craftsman + Mentor**.

### 4.1. Восемь правил голоса

1. Утверждение, не призыв.
2. Цифры обнажены.
3. Метафоры из книг и спорта, не из ИТ.
4. Короткие предложения. Точек больше, чем запятых.
5. Не объясняем известное (R, FIFO, win rate).
6. Объясняем неочевидное (Optimal f, SQN, MAE/MFE).
7. Никаких emoji, "!", "🚀", "✨". Hyphen у нас — «—».
8. Безличный или 2-й pl («вы»). «Я» — никогда. «Ты» — только в pull-quote.

### 4.2. Анти-словарь (запретные слова)

«революционно», «прорыв», «инновация», «no-brainer», «game-changer», «уникальный», «революция», «meta», «vibes», «нейросеть», «AI-powered», «next-gen».

### 4.3. Любимые слова

«измерить», «запись», «факт», «фиксация», «свидетельство», «ремесло», «партитура», «учёт», «дисциплина», «edge».

### 4.4. Прочие constraints

- Все тексты на русском, без англицизмов где есть русский эквивалент.
- Технические термины (R, FIFO, MAE, MFE, Optimal f, SQN) не переводим.
- Имена иностранных авторов — оригинал + транскрипция в первом упоминании.
- Цифры писать цифрами (399, не «триста девяносто девять»).
- Стремимся к 30–40 знаков в lede для editorial-вёрстки.
- A/B-готовность: 2 варианта H1 и 2 варианта Final CTA.

## 5. SEO

### 5.1. Keyword cluster

| Тип | Ключ | Где |
|---|---|---|
| Primary | дневник трейдера | H1, Title, OG |
| Primary | журнал сделок MOEX | Eyebrow, Title |
| Secondary | автоматический журнал сделок | Section 01 |
| Secondary | MAE MFE расчёт | Section 02 |
| Secondary | статистика сделок Тинькофф | Hero lede, Numbers |
| Long-tail | как вести дневник трейдера | Section 4 |
| Long-tail | Optimal f калькулятор | Section 03 explainer |
| Long-tail | Ливермор дневник + ... | Section 5 |
| Long-tail | бесплатный журнал сделок | Pricing |
| Brand | МААТТ | Везде |

### 5.2. Meta tags

```
<title>МААТТ · Журнал сделок MOEX — дневник трейдера с автостатистикой</title>
<meta description>
   Автоматический журнал сделок для трейдера MOEX: 30+ метрик
   (Optimal f, SQN, MAE/MFE), синхронизация с Тинькофф API,
   разбор каждой сделки. Бесплатно до 50 сделок в месяц.
</meta>
<link rel="canonical" href="https://maatt.ru/" />
```

### 5.3. JSON-LD структурированные данные

| Schema | Зачем | Где |
|---|---|---|
| Organization | МААТТ как компания | global (`layout.tsx`) |
| SoftwareApplication | category=FinanceApplication, offers={Free, Pro 399₽} | landing |
| FAQPage | 3 Q→A из «Сам факт» + 2–3 объекции из «Для кого» | landing |
| Person × 6 | name, birthDate, deathDate, sameAs (Wikipedia), subjectOf (цитата) | landing |

### 5.4. Semantic HTML

- H1 ровно один (Hero)
- H2 у каждой содержательной секции
- H3 внутри Pricing и Champions
- `<article>`, `<section>`, `<aside>` на корректных границах
- `alt` для всех `<img>` включая гравюры
- `<picture>` AVIF/WebP для гравюр

### 5.5. Технический SEO

- `app/sitemap.ts` пересборка с новыми anchor-URL
- `app/robots.ts` Disallow `/api/landing/ticker`
- Core Web Vitals: Lighthouse ≥ 95 mobile
- `hreflang="ru"` + `x-default`
- Yandex Metrika + Webmaster sitemap submit (ручная задача)
- Google Search Console (если есть)

### 5.6. Что НЕ делаем

- Doorway pages, микро-сайты по keyword'у, Yandex.Turbo, AMP, закупка backlink'ов.

## 6. Дизайн-полировка

### 6.1. Гравюры × 6 — production

**Стратегия A (целевая):** SVG-стипл через AI + ручная коррекция (Midjourney/DALL-E "stipple engraving portrait, WSJ-style hedcut" → Image-to-vector trace → unify line density → single-color #26221c → `/public/landing/champions/{slug}.svg`, ≤25 KB).

**Стратегия B (fallback):** public-domain фото + CSS filter цепочка (grayscale → contrast → sepia → SVG hatch overlay).

Решение A vs B принимаем на Фазе 3 после теста 1-2 портретов. Не блокируемся: возможен временный placeholder.

### 6.2. Типографика — ревизия

| Точка | Правка |
|---|---|
| H1 max | 96 → 88px |
| H2 секций | унифицировать вокруг 42px |
| Eyebrow разделитель | `·` → `—` |
| Numbers band spacing | 40 → 56px |
| Биография чемпиона | 14px / 1.55 Inter |
| Цитата чемпиона | 15px italic Fraunces + Cormorant cyr |
| Источник цитаты | 11px mono caps, letter-spacing 0.08em |

### 6.3. Палитра — adjustments

Добавляем:
- `--ochre-deep: #5d2a14` — для footnote-источников
- `--paper-tint: #f4ecdc` — фон для «Сам факт»
- `--quote-mark: rgba(38,34,28,0.08)` — декор больших кавычек

WCAG AA контраст обязателен, AAA где можно.

### 6.4. Виджеты — точечная полировка

| Компонент | Что подкрутить |
|---|---|
| LiveTicker | Pulse 1.5s → 2.0s, фон paper-tint |
| HeroEquityCurve | Eyebrow «-1.2R» снизу, убрать grid |
| TradeReplayWidget | Бордюр rule-strong → ink-3, тени мягче |
| InteractiveCandleChart | Tooltip с paper-tint фоном, mono шрифт цифр |
| MaattOrigin → AudienceQualifier | Rename символа |

### 6.5. Новые компоненты

| Файл | Ответственность |
|---|---|
| `components/landing/parts/SimpleFactSection.tsx` | 3 колонки editorial |
| `components/landing/parts/ChampionsSection.tsx` | 3×2 grid |
| `components/landing/parts/ChampionCard.tsx` | Презентационная карточка |
| `components/landing/data/champions.ts` | Type-safe 6 персон |
| `components/landing/data/simple-fact.ts` | Type-safe 3 утверждения |
| `app/structured-data/index.ts` | 4 JSON-LD блока |

### 6.6. Доступность

- WCAG AA обязательно
- Клавиатурная навигация по всем CTA
- Decorative SVG `aria-hidden="true"`
- Meaningful SVG `role="img"` + `<title>` + `<desc>`
- `prefers-reduced-motion` отключает transitions > 200ms
- Focus-rings — sienna outline 2px offset 2px

### 6.7. Visual regression

Текущие Playwright тесты расширяем:
- Champions section desktop + mobile
- SimpleFact section desktop + mobile
- 13 metric explainers (раскрытые)
- Footer rebuild

## 7. Оркестрация работ — 4 фазы

### Фаза 1 · Foundation + Research (read-only)

| Шаг | Инструмент | Деливерабл |
|---|---|---|
| Продуктовый контекст | `mkt-product-marketing` skill | `.agents/product-marketing.md` |
| Голос бренда | `brand-voice-designer` subagent | `docs/brand/voice.md` |
| Иерархия сообщений | `messaging-architect` subagent | `docs/brand/messaging.md` |
| Исследование чемпионов | `general-purpose` subagent (research) | `docs/landing/champions-research.md` |
| CRO-аудит | `mkt-cro` skill + `conversion-optimizer` subagent | `docs/landing/cro-audit.md` |

**Контрольная точка 1:** ревью 5 документов перед Фазой 2.

### Фаза 2 · Copy + IA

| Шаг | Инструмент | Деливерабл |
|---|---|---|
| Реструктура IA | редакт `Landing.tsx` | 16 секций в новом порядке, 2 новые stubs |
| Копирайт секций | `copywriter-specialist` + `mkt-copywriting` skill | Новые тексты для всех 16 секций |
| Контент SimpleFact | `copywriter-specialist` | `SimpleFactSection.tsx` |
| Контент Champions | `copywriter-specialist` | `champions-data.ts` + `ChampionsSection.tsx` |
| Финальный редакт | `content-editor` subagent | Вычитка консистентности |

**Контрольная точка 2:** проверка в браузере, читаемость, ритм.

### Фаза 3 · Design + visuals

| Шаг | Инструмент | Деливерабл |
|---|---|---|
| Гравюры × 6 | AI generator + frontend-design | 6 SVG в `/public/landing/champions/` |
| Дизайн-полировка | `frontend-design` skill | Типографика, палитра, виджеты |
| Champions компонент | `shadcn-ui` или `21st-dev-magic` | Финальный layout |
| SimpleFact компонент | `frontend-design` | Three-column editorial |

**Контрольная точка 3:** визуал-ревью + Playwright visual regression.

### Фаза 4 · SEO

| Шаг | Инструмент | Деливерабл |
|---|---|---|
| Meta + structured data | implementer | `metadata` в `layout.tsx`, 4 JSON-LD блока |
| Контент-оптимизация | `mkt-seo` (если есть) | Keyword mapping, semantic HTML |
| Sitemap + robots | implementer | Пересборка `sitemap.ts`, `robots.ts` |
| OG-image | reuse playwright pipeline | Обновлённая картинка |
| Final review | `code-reviewer` + `security-reviewer` | Pre-merge gate |

**Контрольная точка 4:** Lighthouse, OG-preview, Yandex Webmaster — готово к merge.

### Оркестрация — диаграмма

```
brainstorming(текущая)
  → writing-plans(skill)
  → Phase 1 (параллельно: 5 subagents/skills, read-only)
  → Phase 2 (последовательно: IA → copy → SimpleFact → Champions → edit)
  → Phase 3 (последовательно: portraits → polish → components)
  → Phase 4 (параллельно: meta+SD, content opt, sitemap → final review)
```

Все коммиты атомарные, отдельная feature-ветка в worktree.

## 8. Артефакты и хранение

| Артефакт | Путь |
|---|---|
| Spec (этот документ) | `docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md` |
| Implementation plan | `docs/superpowers/plans/2026-05-18-landing-champions-rebuild.md` (создаст writing-plans) |
| Product context | `.agents/product-marketing.md` |
| Brand voice | `docs/brand/voice.md` |
| Messaging | `docs/brand/messaging.md` |
| Champions research | `docs/landing/champions-research.md` |
| CRO audit | `docs/landing/cro-audit.md` |
| SEO checklist | `docs/landing/seo-checklist.md` |
| Гравюры | `frontend/public/landing/champions/*.svg` |
| Новые компоненты | `frontend/src/components/landing/parts/{SimpleFactSection,ChampionsSection,ChampionCard}.tsx` |
| Новые данные | `frontend/src/components/landing/data/{champions,simple-fact}.ts` |
| Structured data | `frontend/src/app/structured-data/index.ts` |

## 9. Out of scope

- Контент-cluster /blog статей под explainer'ы — отдельная Фаза 5+
- Dark theme
- EN-локализация
- AMP / Yandex.Turbo
- Doorway pages / микросайты
- Закупка backlink'ов
- Замена палитры или Fraunces (cream остаётся)

## 10. Готовность к writing-plans

Spec покрывает что строим (IA, новые секции, копи-направление, голос, SEO, дизайн) и как организуем работу (4 фазы, агенты/скиллы по шагам, контрольные точки). `writing-plans` skill следующим шагом превращает это в task-by-task implementation plan с конкретными файлами, командами агентов, тест-стратегией.

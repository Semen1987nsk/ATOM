# Дизайн-система Eqio — v3 (Editorial Financial)

> Источник истины. Любое новое UI-решение проверяется отсюда.
> Реализация в коде: `frontend/src/app/globals.css`.
>
> **Версия 3** (2026-05-17). Полная переработка через [ADR-0006](../tech/decisions/0006-editorial-financial-rebrand.md). Предыдущие версии:
> — v1 «Bloomberg-meets-cyberpunk» (отброшена)
> — v2 «Linear/Stripe-стиль» (07.05.2026 — 17.05.2026, supersede)

## Концепция

**Editorial Financial.** Уровень FT.com / Stripe Press / Bloomberg Markets. Не SaaS-template, не consumer product — финансовая пресса в digital-form.

Из «Linear/Stripe-стиля» v2 сознательно отказались (см. ADR-0006): этот стиль стал статистическим центром LLM-генерации в 2025–2026 и перестал нести сигнал «премиум». Editorial-financial занимает свободную визуальную нишу — для трейдеров MOEX это читается как «настоящий профессиональный инструмент», не «ещё один AI-vibecoded стартап».

**Аксиомы:**
- Типографика — главное выразительное средство. Serif headlines + sans body + mono digits.
- Hairline rules вместо карточек-боксов.
- Один acid accent (ochre), не палитра.
- Semantic P&L colors — desaturated print-tones, не neon.
- Asymmetric editorial grid вместо симметричного bento.

## Цвета (CSS variables)

### Тёмная тема (default — трейдеры работают в темноте)

| Токен | HEX | Где используется |
| --- | --- | --- |
| `--paper-base` | `#14110d` | Основной фон (warm near-black) |
| `--paper-sunken` | `#100e0a` | Подложка под крупные секции |
| `--paper-raised` | `#1a1714` | Карточки 1-го уровня |
| `--paper-overlay` | `#25221d` | Модалки, hover-overlay |
| `--ink` | `#f5f1e8` | Основной текст (warm off-white) |
| `--ink-2` | `#b8b1a0` | Подписи |
| `--ink-3` | `#847d6e` | Мета-инфо, eyebrows |
| `--ink-4` | `#5a5347` | Disabled, placeholders |
| `--rule` | `rgba(245,241,232,0.10)` | Hairline rules между секциями/строками |
| `--rule-strong` | `rgba(245,241,232,0.22)` | Усиленные hairlines (header/footer, dividers) |
| `--accent` | `#d4a13a` | Ochre acid. Единственный brand-цвет, CTA-кнопки, активные ссылки |
| `--accent-hover` | `#e2b455` | Hover-состояние |
| `--accent-active` | `#b5871f` | Pressed |
| `--accent-soft` | `rgba(212,161,58,0.14)` | Soft-фон для accent badges |
| `--profit` / `--success` | `#2c8c5c` | Прибыль (PnL > 0), forest green |
| `--loss` / `--danger` | `#b94731` | Убыток (PnL < 0), brick red |
| `--warning` | `#c98e1f` | Предупреждения, tea ochre |
| `--info` | `var(--ink-2)` | Info — приглушённый text, не отдельный цвет |

Aliases для back-compat: `--background → --paper-base`, `--surface-1 → --paper-raised`, `--foreground → --ink`, `--border → --rule`.

### Светлая тема (через `data-theme="light"`)

FT pink-paper стиль:

| Токен | HEX | Заметка |
| --- | --- | --- |
| `--paper-base` | `#faf7f0` | Cream warm paper |
| `--paper-sunken` | `#f4f0e6` | Подложка |
| `--paper-raised` | `#ffffff` | Карточки |
| `--ink` | `#1f1d1a` | Текст |
| `--accent` | `#b5871f` | Темнее для контраста на cream |
| `--profit` | `#1e7a4e` | Forest green darker |
| `--loss` | `#a53c25` | Brick red darker |

## Семантика цвета

- **`--profit` / `--success`** = прибыль, успех, выполнено. Используется на equity-curve, в StatTile-значениях с PnL > 0, в success-badges. **Не для CTA.**
- **`--loss` / `--danger`** = убыток, ошибка, удаление. PnL < 0, error-state, delete-confirm. **Не для предупреждений.**
- **`--accent` (ochre)** = brand. Кнопки CTA, активные ссылки nav, выделение featured-plan, IMOEX-overlay на графике (dashed). **Не путать с warning.**
- **`--warning` (tea ochre)** = предупреждения, trial-countdown. Отличается от accent оттенком и менее насыщенный.
- **Все остальные числа** — `var(--ink)` warm-white. Никаких «пёстрых цветов для разных метрик» — это AI-tell.

## Типографика

| Сценарий | Шрифт | Параметры |
| --- | --- | --- |
| Display / Hero | Fraunces (variable serif) | weight 300, italic, optical-size axis, clamp(56px, 8vw, 112px) |
| H1 — section title | Fraunces | weight 400, normal, clamp(40px, 5vw, 72px) |
| H2 — subsection | Fraunces | weight 400, clamp(28px, 3vw, 44px) |
| H3+ — UI heading | Geist Sans | weight 600, 19–22px |
| Body | Geist Sans | weight 400, 16px, line-height 1.55 |
| Lede / Pull-quote | Fraunces | weight 400, italic, clamp(20px, 2vw, 26px) |
| Eyebrow | Geist Sans | weight 500, 11px uppercase letter-spacing 0.14em, color `--ink-3` |
| Все цифры | Geist Mono | tabular-nums lining-nums (`font-feature-settings: "tnum","lnum"`) |
| Inline code | Geist Mono | 14px |

**Шрифты (закрытое множество):**
- Geist Sans — `next/font/google` с `subsets: ["latin", "cyrillic"]`
- Geist Mono — `next/font/google` с `subsets: ["latin"]`
- Fraunces — `next/font/google` с `subsets: ["latin", "cyrillic"]`, `axes: ["opsz","SOFT"]`, weights 300/400/500/600, styles normal+italic

**Никаких новых шрифтов без ADR.** В частности — **не использовать** Inter, Roboto, Arial, Cormorant, Source Serif, Spectral, Tiempos (платный).

## Радиусы

| Токен | Значение | Где |
| --- | --- | --- |
| `--radius-xs` | 2px | Бейджи, чипы |
| `--radius-sm` | 3px | Inputs мелкие |
| `--radius-md` | 4px | Buttons (rectangle), inputs |
| `--radius-lg` | 6px | Карточки, модалки |
| `--radius-xl` | 8px | Хотим больших радиусов — это потолок (back-compat alias) |
| `--radius-pill` | 9999px | **ТОЛЬКО** для filter chips. Не для primary CTA. |

**Запрещено:** `border-radius > 8px` на любом элементе. Pill-buttons как primary action — анти-паттерн.

## Тени

Удалены по умолчанию. Карточка отделена hairline border (`1px solid var(--rule)`), не box-shadow.

- `--shadow-sm / md / lg` = `none` (oставлены как aliases для back-compat)
- `--shadow-xl` = `0 12px 40px rgba(0,0,0,0.50)` — **только модалки**

**Запрещены:** neon-glow, coloured shadow, `blur > 12px` на любом box-shadow, любые pulse-glow эффекты.

## Анимации

| Токен | Длительность | Easing |
| --- | --- | --- |
| `--transition-fast` | 0.12s | cubic-bezier(0.22, 1, 0.36, 1) |
| `--transition-base` | 0.20s | cubic-bezier(0.22, 1, 0.36, 1) |

Допустимы: `fadeIn` (0.25s), `scaleIn` (0.25s), skeleton-shimmer (1.5s linear).

**Запрещены:** `pulse`, `glow`, `float`, любая бесконечно повторяющаяся анимация на элементе кроме skeleton-loader. Hover-scale > 1.02. Hover-translate > 2px.

## Отступы

Шкала по 4: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 96 / 128.

- Между секциями лендинга — 96–128px (editorial breathing room)
- Между секциями дашборда — 24px (mobile) / 32px (desktop) — плотность важнее воздуха
- Внутри карточки — 16–24px

## Плотность (контекстно)

**Лендинг** — editorial-air. Большие отступы между секциями, asymmetric grid, серьёзная типографика, много whitespace.

**Дашборд / app** — плотность важнее воздуха ([`ux-laws.md`](ux-laws.md) §3). Трейдер хочет видеть много метрик одновременно:
- Карточка-плитка: ширина 280–360px, высота 100–140px
- В строке метрик: 4 на desktop, 2 на tablet, 1 на mobile
- Таблицы: сжатые (row-height 36–40px)

Это намеренное напряжение между контекстами. Лендинг продаёт спокойствие профессионального инструмента, дашборд — даёт плотную работу.

## Компонентные паттерны

| Компонент | CSS-класс | Назначение |
| --- | --- | --- |
| Card | `.cyber-card` | Hairline-border (1px var(--rule)), без shadow, radius 6px. (Имя legacy — оставлено для back-compat.) |
| Primary CTA | `.btn-primary` | Rectangle (4px radius), ochre fill, ink text |
| Secondary CTA | `.btn-secondary` | Rectangle, transparent fill, ink border |
| Outline link | `.btn-outline` | Rectangle, transparent fill, currentColor border. Для nav и tertiary CTA. |
| Ghost icon | `.btn-icon` | Square 36×36, transparent, currentColor |
| Danger | `.btn-danger` | Rectangle, loss-red fill, ink text |
| Badge | `.badge` | 2px radius, variants: accent / success / danger / warning / neutral |
| Skeleton | `.skeleton-shimmer` | Linear-gradient shimmer 1.5s |
| Stat tile | `.stat-tile` / `<StatTile>` | Mono-цифра (28px), eyebrow-label (11px uppercase), hairline-border, no shadow |
| Editorial tile | `.tile` color="neutral" \| "inverse" | Hairline-border tile для маркетинговых секций. **БЕЗ цветных вариантов** — `tile-indigo/violet/emerald/rose/amber/sky` удалены. |

## Лендинг-классы (Editorial Financial)

Только для маркетинговых страниц (`/`, `/pricing`, `/manual`). Не использовать в продукт-UI.

### Editorial type scale

| Класс | Параметры | Назначение |
| --- | --- | --- |
| `.editorial-display` | Fraunces 300 italic, clamp(56px, 8vw, 112px) | Hero h1 |
| `.editorial-h1` | Fraunces 400, clamp(40px, 5vw, 72px) | Section h1 |
| `.editorial-h2` | Fraunces 400, clamp(28px, 3vw, 44px) | Section h2 |
| `.editorial-lede` | Fraunces 400 italic, clamp(20px, 2vw, 26px) | Subtitle под hero, pull-quote |
| `.editorial-eyebrow` | Geist 500, 11px uppercase letter-spacing 0.14em | Надзаголовки секций |
| `.num` / `td.num` / `.stat-value` | Geist Mono + tabular-nums | Все числа |

### Section composition

| Класс | Назначение |
| --- | --- |
| `.rule` | `border-top: 1px solid var(--rule)` |
| `.rule-strong` | `border-top: 1px solid var(--rule-strong)` |
| `.editorial-grid-asymmetric` | 12-col grid с asymmetric (5/7, 7/5, 9/3) |
| `.editorial-numbers-band` | 4 hairline-separated columns с mono-числами |
| `.editorial-pullquote` | Центрированный serif-italic между двумя rule-strong |
| `.editorial-table` | Dense data-table с sticky header, hairline rows, mono-cells |

### Tile варианты (только нейтральные)

| Класс | Что |
| --- | --- |
| `.tile` (`color="neutral"`) | Прозрачный с hairline border, ink text |
| `.tile-inverse` | Ink fill, paper text — для featured-блока (≤1 на секцию) |

**Удалены:** `tile-indigo`, `tile-violet`, `tile-emerald`, `tile-rose`, `tile-amber`, `tile-sky`. Их использование = code-smell.

### Decor

**Нет декоративных элементов.** Никаких `KonturCurve`, абстрактных SVG-форм, blur-orbs, mesh-gradients, sparkle-иконок. Hairline rules — единственное визуальное разделение.

## Анти-паттерны (никогда не делать)

### Цвета и градиенты

- ❌ Indigo (`#6366f1`, `#818cf8`, `#4f46e5`), Violet (`#8b5cf6`, `#7c3aed`) — старая бренд-палитра, теперь запрещена
- ❌ Tailwind utility-классы: `from-purple-*`, `to-pink-*`, `from-cyan-*`, `from-violet-*`, `from-fuchsia-*`, `from-indigo-*`, `to-teal-*`
- ❌ Любые `linear-gradient` / `radial-gradient` на фонах кнопок, карточек, badges
- ❌ `bg-clip-text` gradient headings (`.text-gradient`, `.text-neon` — удалены)
- ❌ Discord-стиль accent (фиолетово-розовые градиенты в МAEMFE/PostExit карточках)
- ❌ Tailwind `text-green-500` / `text-red-500` хардкодом для PnL — только `var(--profit)` / `var(--loss)`

### Композиция

- ❌ Bento Grid с 6 цветными tiles (Kontur-style v2) — заменён editorial-table или editorial-grid-asymmetric
- ❌ 3-колоночные feature-grid с иконкой-в-цветном-круге сверху
- ❌ Симметричный bento (4/4/4 col-span) для маркетинговых блоков
- ❌ Backdrop-blur translucent панели поверх hero
- ❌ Centered hero с двумя CTA-кнопками stacked
- ❌ KonturCurve декоративные S-кривые

### Типографика — анти-паттерны

- ❌ Inter, Roboto, Arial, system-ui (повторим — это AI-tells)
- ❌ Cormorant, Source Serif, Spectral, Tiempos (платный)
- ❌ Эмодзи в кнопках/заголовках (кроме design-точек: уже зафиксированные иконки настроения 🚀😊😐😟😤 — допустимы только в журнале сделок)
- ❌ UPPERCASE везде кроме `.editorial-eyebrow`
- ❌ Прыгающие proportional-числа в таблицах (требуется `tabular-nums`)

### Геометрия и эффекты

- ❌ `border-radius > 8px` на любом элементе
- ❌ Pill-buttons (`--radius-pill: 9999px`) как primary CTA — pill только для filter chips
- ❌ Neon shadows, glow effects, coloured box-shadow
- ❌ `pulse-glow`, `animate-pulse` на статус-индикаторах
- ❌ Hover-scale > 1.02, hover-translateY > 2px

### Поведение

- ❌ Glassmorphism (заявлен в спеке v1, отброшен)
- ❌ Анимация при каждом hover на карточку
- ❌ Кастомные курсоры
- ❌ Random иконки lucide без проверки (используем устоявшийся набор)
- ❌ Sparkles / AI-magic иконки в hero — generic AI-aesthetic

## Что копировать в новые виджеты

1. **Card structure:** `cyber-card` (hairline border, no shadow) + 16–24px padding + 12–16px gap внутри
2. **Header в карточке:** title (editorial-eyebrow 11px uppercase letter-spacing 0.14em) + иконка справа + "?" tooltip
3. **Числовое значение:** Geist Mono, 24–28px, tabular-nums, цвет по семантике (`var(--profit)` / `var(--loss)` / `var(--ink)`)
4. **Подзаголовок:** 12–13px `var(--ink-2)` Geist Sans
5. **Hover:** легчайший контраст границы (`var(--rule)` → `var(--rule-strong)`), без scale, без shadow-апгрейда

## Reference

- Editorial composition: ft.com, stripe.com/press, bloomberg.com/markets, wsj.com
- Type pairing: Stripe Press (Söhne + Tiempos), Pitch.com (Fraunces + Inter — у нас Fraunces + Geist)
- Palette: FT pink-paper background, Bloomberg amber accent
- ADR с обоснованием: [ADR-0006](../tech/decisions/0006-editorial-financial-rebrand.md)

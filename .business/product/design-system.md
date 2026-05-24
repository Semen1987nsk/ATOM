# Дизайн-система Empirik

> Источник истины. Любое новое UI-решение проверяется отсюда.
> Реализация в коде: `frontend/src/app/globals.css`.

## Концепция

**Спокойный профессиональный продукт-UI.** Уровень Linear / Vercel / Stripe. Без шума, без свечения, без неона.

Из изначального видения «Bloomberg meets Cyberpunk» сознательно отказались (см. ADR-NNNN при необходимости). Трейдеры долго смотрят в экран — нужна нейтральность.

## Цвета (CSS variables)

### Тёмная тема (default)

| Токен | HEX | Где используется |
| --- | --- | --- |
| `--background` | `#0a0a0b` | Основной фон |
| `--surface-1` | `#141416` | Карточки 1-го уровня |
| `--surface-2` | `#1c1c20` | Карточки 2-го уровня (модалки) |
| `--surface-3` | `#26262c` | Hover, отдельные элементы |
| `--foreground` | `#fafafa` | Основной текст |
| `--text-secondary` | `#a1a1aa` | Подписи |
| `--text-tertiary` | `#71717a` | Мета-инфо |
| `--accent` | `#6366F1` | Indigo. Кнопки, активные элементы |
| `--accent-hover` | `#818cf8` | Hover-состояние |
| `--accent-active` | `#4f46e5` | Pressed |
| `--success` | `#10b981` | Прибыль (PnL > 0) |
| `--danger` | `#f43f5e` | Убыток (PnL < 0) |
| `--warning` | `#f59e0b` | Предупреждения |
| `--info` | `#3b82f6` | Информационные подсказки |
| `--border` | `~rgba(255,255,255,0.08)` | Все границы |

### Светлая тема (через `data-theme="light"`)

Инвертированы surface/text, accent темнее для контраста. Реализована, но второстепенна — наша аудитория торгует в темноте.

## Семантика цвета

- **Зелёный** = прибыль, успех, выполнено. **НЕ использовать для CTA** (CTA это accent indigo).
- **Красный** = убыток, ошибка, удаление. **НЕ для предупреждений** (это warning amber).
- **Indigo** = акцент бренда, единственный цвет CTA-кнопок.

## Типографика

| Сценарий | Шрифт | Откуда |
| --- | --- | --- |
| Основной текст | Geist Sans | next/font/google |
| Цифры в таблицах | Geist Mono | next/font/google + `tabular-nums` |
| Заголовки | Geist Sans, weight 600-700 | — |

**НЕ использовать:** Inter, Roboto, Arial, system-ui (см. `frontend-design` skill).

## Радиусы

| Токен | Значение | Где |
| --- | --- | --- |
| `--radius-sm` | 6px | Чипы, бейджи, малые кнопки |
| `--radius-md` | 10px | Inputs, обычные кнопки |
| `--radius-lg` | 14px | Карточки |
| `--radius-xl` | 20px | Модалки |
| `--radius-pill` | 9999px | Pill-кнопки (primary CTA) |

## Тени

Тихие, едва видимые:
- `0 1px 2px rgba(0,0,0,0.4)` — карточки в покое
- `0 4px 12px rgba(0,0,0,0.5)` — модалки, dropdowns
- **НЕ использовать** свечения, neon-shadow, blur > 12px

## Анимации

| Токен | Длительность | Easing |
| --- | --- | --- |
| `--transition-fast` | 0.15s | ease-out |
| `--transition-base` | 0.25s | cubic-bezier(0.16, 1, 0.3, 1) |

**НЕ использовать:** float, pulse, glow, scale > 1.05.

## Отступы

Шкала по 4: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64. Между секциями — 24px (mobile) / 32px (desktop). Внутри карточки — 16-20px.

## Плотность

Дашборд — **высокая плотность**, но не клаустрофобия:
- Карточка-плитка: ширина 280-360px, высота 100-140px
- В строке метрик: 4 на desktop, 2 на tablet, 1 на mobile
- Таблицы: сжатые (row-height 36-40px)

## Компонентные паттерны

| Компонент | CSS-класс | Назначение |
| --- | --- | --- |
| `.cyber-card` | карточка | Основной контейнер виджета |
| `.btn-primary` | indigo pill | Главное действие (всегда один на экране) |
| `.btn-secondary` | outline | Альтернативное действие |
| `.btn-ghost` | без фона | Иконочные/малоприоритетные |
| `.btn-danger` | красный | Удаление |
| `.btn-icon` | квадратная | Иконочные кнопки в header |
| `.badge` | бейдж | accent / success / danger / warning / neutral |
| `.skeleton-shimmer` | shimmer | Loading-state |
| `.tile` с градиентами | плитка | Главная страница (indigo / violet / emerald / rose / amber / sky) |

## Лендинг-классы (kontur-style редизайн)

Только для маркетинговых страниц (`/`, `/pricing`, `/manual`). Не использовать в продукт-UI.

### Headline-типографика

| Класс | Размер (clamp) | Назначение |
| --- | --- | --- |
| `.headline-2xl` | 48–96px | Hero h1 |
| `.headline-xl` | 40–72px | Final CTA, большие плакаты |
| `.headline-lg` | 32–56px | Section h2 |
| `.eyebrow` | 13px uppercase accent | Надзаголовки секций |
| `.number-fact` | 56–80px black | Огромные цифры в Numbers Band |

### Section backgrounds (контрастный ритм)

| Класс | Что | Когда |
| --- | --- | --- |
| `.section-dark` | `--background` (#0a0a0b) | Основа лендинга, hero |
| `.section-surface` | `--surface-1` (#141416) | Промежуточная (split MAE/MFE) |
| `.section-light` | #fafafa + чёрный текст | Контрастная белая (Numbers, How-it-works) |
| `.section-accent` | `--accent` indigo | Final CTA |

### Tile варианты

| Класс | Что |
| --- | --- |
| `.tile`, `.tile-{indigo\|violet\|emerald\|rose\|amber}` | Цветная заливка (existing) |
| `.tile-outline` | Прозрачная плитка с border `currentColor` + ↗ |
| `.tile-text` | Только текст с `border-top` (kontur-приём) |

### Кнопки

- `.btn-pill-outline` — outline pill для header («Войти в сервис») и tertiary CTA
- `.btn-pill-inverted` — белая на indigo фоне (для Final CTA на accent-секции)

### Декор

- `<KonturCurve variant="tr|br|bl|tl" color opacity />` — единственный декор-компонент. Тонкая S-кривая в углу секции. Использовать ≤1 раз на секцию.

## Анти-паттерны (никогда не делать)

- ⚠️ Bento Grid с разными размерами плиток — **разрешён** на маркетинговых страницах (`/`, `/pricing`, `/manual`) при условии: 12-column grid, ≤6 плиток в одном блоке, контраст типов (text-only / colored / outlined). **Запрещён** в продукт-UI (дашборд, analysis-страницы) — там равномерная плотность.
- ❌ Glassmorphism (заявлен в спеке, но решено не использовать)
- ❌ Neon shadows / glow effects
- ❌ Анимация при каждом hover на карточку
- ❌ Discord-стиль accent (фиолетово-розовые градиенты)
- ❌ Эмодзи в кнопках/заголовках
- ❌ Random иконки lucide без проверки (используем устоявшийся набор)
- ❌ Пёстрые цвета для разных метрик (все белые/светлые на dark, цвет — только для PnL)
- ❌ Кастомные курсоры
- ❌ Стандартные шрифты (Inter, Arial, Roboto)

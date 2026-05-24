# Эталон №1 — Главный дашборд

**Скриншот:** `eqio-final-dashboard.png` + `eqio-dashboard-final.png` (empty-state)
**Код:** `frontend/src/app/page.tsx` (Client) + `frontend/src/app/dashboard-demo/page.tsx` (Server-вариант)

## Layout

```
┌─────────┬─────────────────────────────────────────────┐
│ Sidebar │ Header (Cmd+K, notifications, user menu)    │
│ 240px   ├─────────────────────────────────────────────┤
│         │                                             │
│ — нав.  │  Title + filters (период / тег / сделки)   │
│ — счёт  │                                             │
│ — CTA   │  Tabs: Обзор / Продвинутая / Сравнение     │
│         │                                             │
│         │  ┌───────────────────────────────────────┐ │
│         │  │  Equity Curve (главная карта)         │ │
│         │  │  + IMOEX overlay                      │ │
│         │  └───────────────────────────────────────┘ │
│         │                                             │
│         │  Stats Grid: 4 колонки на desktop          │
│         │  PnL | WinRate | Optimal f | SQN          │
│         │  Z-Score | PF | R-Exp | Recovery          │
│         │  ...                                        │
│         │                                             │
└─────────┴─────────────────────────────────────────────┘
```

## Иерархия плиток (порядок важности)

1. **Equity Curve** — главная карта, всегда первая. Линия PnL + IMOEX-бенчмарк.
2. **Stats Grid** — 4×N сетка. Самые ценные метрики первыми:
   - Общий PnL → Винрейт → Optimal f → SQN
   - Z-Score → Profit-Фактор → R-Ожидание → Фактор Восстановления
   - ROI → Потенц. GHPR → Коэфф. Сортино → Макс. Просадка
   - Текущая Просадка → Tail Ratio → Серия Побед → Серия Убытков
3. **Каждая плитка** имеет:
   - Заголовок мелким caps (uppercase 11px, slate-400)
   - Иконку справа сверху (lucide, `--accent`-цвет, размер 16px)
   - "?" tooltip-trigger для объяснения метрики (новички ↔ профи)
   - Большое значение (24-28px, mono для чисел)
   - Подпись внизу (12px slate, опционально trend-стрелка)

## Семантика цвета на дашборде

> Обновлено через [ADR-0006](../../tech/decisions/0006-editorial-financial-rebrand.md) — desaturated editorial-print цвета вместо неоновых.

- PnL > 0 — `var(--profit)` / `var(--success)` (`#2c8c5c` forest green; в light — `#1e7a4e`)
- PnL < 0 — `var(--loss)` / `var(--danger)` (`#b94731` brick red; в light — `#a53c25`)
- Все остальные числа — `var(--ink)` warm-white на dark, без «пёстрых цветов для разных метрик»
- Sparkline / линия equity — `var(--profit)` если в плюсе, `var(--loss)` если в минусе
- IMOEX overlay — приглушённый ochre `var(--accent)`, dashed line

## Filters bar

- Период: «всё время / неделя / месяц / 3 мес / год / custom»
- Теги: мульти-select с поиском
- Тип сделок: «все / лонг / шорт»

## Empty-state

См. `eqio-dashboard-final.png` — карточка с CTA «Начните вести журнал сделок» + 2 кнопки «Импортировать сделки» / «Добавить вручную». Под ней — все плитки видны, но с пустыми значениями (`—`) и приглушены.

## Loading-state

`<Skeleton.DashboardSkeleton />` — но **только для секций**, не глобально. Каждая плитка скелетится независимо (если использовать Server Components — Suspense вокруг каждой).

## Mobile

- Sidebar превращается в drawer (off-canvas, swipe close)
- Stats Grid: 1 колонка
- Tabs: scrollable horizontal
- Charts: full-width, высота 200-280px

## Что копировать в новые виджеты

1. **Card structure**: `cyber-card` + 16-20px padding + 12-16px gap внутри
2. **Header в карточке**: title (uppercase 11px) + иконка справа + "?" tooltip
3. **Числовое значение**: 24-28px Geist Mono, tabular-nums, цвет по семантике
4. **Подзаголовок**: 12px slate-400
5. **Hover**: легчайший тень-апгрейд (`0 1px 2px` → `0 4px 12px`), без scale

## Что не делать

- ❌ Не добавлять новые плитки на главный дашборд без согласования (информационный шум)
- ❌ Не использовать цветные плитки (как `.tile` с градиентами) — они для landing, не для дашборда
- ❌ Не показывать графики внутри маленьких плиток (sparkline только если он реально читаемый)
- ❌ Не переставлять иерархию (PnL всегда первый)

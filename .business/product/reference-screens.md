# Карта референсных скриншотов

В корне репозитория `C:\Users\Administrator\Eqio\ATOM\` лежит ~60 PNG-файлов с истории дизайна. Не все актуальны.

## ✅ Актуальные эталоны (использовать)

| Файл | Что | Эталон чего |
|---|---|---|
| `eqio-final-dashboard.png` | Главный дашборд (текущий) | Layout, плотность, equity-кривая, табы |
| `eqio-dashboard-final.png` | Дашборд с пустым state | Empty-state паттерн, табы фильтров |
| `eqio-mae-mfe-page.png` | MAE/MFE анализ | Фильтры периода/тегов, таблица группировок |
| `eqio-replay-realistic.png` | Trade Replay | Свечи MOEX + маркеры stop/take/вход/выход |
| `eqio-history-polish.png` | Дневник сделок | Таблица 2-line layout (вход + выход) |
| `eqio-pricing.png` | Тарифы | 3-плана layout, выделение Pro как «Популярный» |
| `eqio-mobile-home.png` | Mobile-главная | Адаптивная вёрстка sidebar→drawer |
| `eqio-final-cmdk.png` | Cmd+K Command Palette | Группировка пунктов, fuzzy search |
| `eqio-final-usermenu.png` | User menu | Account switcher, theme/language toggles |
| `eqio-landing-final.png` | Лендинг (hero) | Заголовок, подзаголовок, CTA |

## 🟡 Внешние референсы (для вдохновения, не копирования 1:1)

| Файл | Источник | Что почерпнуть |
|---|---|---|
| `ref-linear-method.png` | Linear | Тон, типографика, спокойствие |
| `ref-stripe-dashboard.png` | Stripe | Плотность, цвет PnL, числа в моно |
| `ref-tradezella-landing.png` | TradeZella | Hero-формулировки, social proof |
| `ref-tradervue.png` | Tradervue | Чего НЕ делать (visual clutter) |
| `kontur-hero.png` | Контур | РФ-стайл серьёзного финтеха |

## 🔴 Устаревшие (не использовать как образец)

| Файл | Почему устарел |
|---|---|
| `eqio-dashboard-overview-tab.png` | Старый layout табов |
| `eqio-dashboard-stripped.png` | Промежуточное состояние |
| `eqio-equity-chart.png` | Старая палитра |
| `eqio-empty-state-fixed.png` / `eqio-empty-state-v2.png` | Промежуточные empty-states |
| `eqio-launch-current.png` | Старый landing |
| `eqio-login.png` / `eqio-login-v2.png` | До текущего login (используй `eqio-login-final.png`) |
| `eqio-replay-lkoh.png` / `eqio-replay-lkoh-v2.png` / `eqio-replay-lkoh-1h.png` | Промежуточные итерации Replay (теперь `eqio-replay-realistic.png`) |
| `eqio-history.png` / `eqio-history-mobile.png` / `eqio-history-mobile-with-ai.png` | Старые версии (теперь `eqio-history-polish.png`) |

## 🟢 Состояния которые надо сделать (нет эталонов пока)

- Календарь P&L (видна в меню как SOON)
- Открытые позиции
- Отчёты
- Психология (психо-трекер)
- Заметки
- Сетапы
- Импорт сделок (preview)
- Брокеры (BrokerConnectModal — есть только модалка, нет страницы)
- AI-инсайты страница (есть карточка, нет полной)
- Daily Review

## Как использовать

1. **Перед новой фичей** — найди в этом списке ближайший актуальный эталон
2. **Прочитай feature-canon/** соответствующий файл (если есть)
3. **Открой PNG** и посмотри: layout, плотность, тон, расстояния
4. **Если эталона нет** — создай новый по образцу 01/02/03

## Как обновлять

Когда:
- Поменяли визуал в коде → пересоздай скриншот → обнови этот файл
- Добавили новую фичу → положи скриншот → добавь в раздел «Актуальные»
- Старый PNG больше не отражает реальность → переведи в «Устаревшие»

**НЕ удалять PNG-файлы из репозитория** — это исторический контекст для будущих переделок.

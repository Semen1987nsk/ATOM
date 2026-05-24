# Карта референсных скриншотов

В корне репозитория `C:\Users\Administrator\Empirik\ATOM\` лежит ~60 PNG-файлов с истории дизайна. Не все актуальны.

## ✅ Актуальные эталоны (использовать)

| Файл | Что | Эталон чего |
|---|---|---|
| `empirik-final-dashboard.png` | Главный дашборд (текущий) | Layout, плотность, equity-кривая, табы |
| `empirik-dashboard-final.png` | Дашборд с пустым state | Empty-state паттерн, табы фильтров |
| `empirik-mae-mfe-page.png` | MAE/MFE анализ | Фильтры периода/тегов, таблица группировок |
| `empirik-replay-realistic.png` | Trade Replay | Свечи MOEX + маркеры stop/take/вход/выход |
| `empirik-history-polish.png` | Дневник сделок | Таблица 2-line layout (вход + выход) |
| `empirik-pricing.png` | Тарифы | 3-плана layout, выделение Pro как «Популярный» |
| `empirik-mobile-home.png` | Mobile-главная | Адаптивная вёрстка sidebar→drawer |
| `empirik-final-cmdk.png` | Cmd+K Command Palette | Группировка пунктов, fuzzy search |
| `empirik-final-usermenu.png` | User menu | Account switcher, theme/language toggles |
| `empirik-landing-final.png` | Лендинг (hero) | Заголовок, подзаголовок, CTA |

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
| `empirik-dashboard-overview-tab.png` | Старый layout табов |
| `empirik-dashboard-stripped.png` | Промежуточное состояние |
| `empirik-equity-chart.png` | Старая палитра |
| `empirik-empty-state-fixed.png` / `empirik-empty-state-v2.png` | Промежуточные empty-states |
| `empirik-launch-current.png` | Старый landing |
| `empirik-login.png` / `empirik-login-v2.png` | До текущего login (используй `empirik-login-final.png`) |
| `empirik-replay-lkoh.png` / `empirik-replay-lkoh-v2.png` / `empirik-replay-lkoh-1h.png` | Промежуточные итерации Replay (теперь `empirik-replay-realistic.png`) |
| `empirik-history.png` / `empirik-history-mobile.png` / `empirik-history-mobile-with-ai.png` | Старые версии (теперь `empirik-history-polish.png`) |

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

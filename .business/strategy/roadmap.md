# Roadmap Empirik

> Скелет. Заполнять по мере появления данных и решений.

## Q2 2026 (текущий)

**Тема квартала: «Юридический и платёжный фундамент + Reverse-Trial»**

- [x] PR1: 152-ФЗ согласие + удаление + политика
- [x] Решение о тарифной модели: Reverse-Trial 21d + Free+ + Pro 399₽ ([ADR-0005](../tech/decisions/0005-reverse-trial-model.md), 2026-05-14)
- [ ] ЮKassa интеграция (рекуррент + чеки 54-ФЗ) — **блокер для запуска Reverse-Trial**
- [ ] Backend: Subscription статусы `trial_active` / `free_plus`, downgrade-job D+21
- [ ] Backend: фильтрация `sync_enabled` в `sync_scheduler.py` (Free+ не sync)
- [ ] Backend: email/push-flow D-7/D-3/D-1/D+7
- [ ] Frontend: перерисовка `/pricing` (Trial / Free+ / Pro) + компонент `<FrozenFeatureBadge />`
- [ ] Frontend: D+21 экран «Подарок за trial» с PDF
- [ ] Policy v2: параграф про хранение API-токена на Free+
- [ ] Финам импорт (через Excel)
- [ ] БКС импорт
- [ ] Закрыть «SOON»: Календарь P&L, Сетапы, Отчёты
- [ ] РКН-уведомление подано
- [ ] Перенос на Yandex Cloud

**KPI:** готовность к платному запуску с Reverse-Trial-моделью.

## Q3 2026

**Тема: «Платный запуск + рост»**

- [ ] Запуск платного Pro
- [ ] A/B 399₽ vs 590₽
- [ ] Контент-маркетинг: Smart-Lab, YouTube
- [ ] Цель: **1000 платных подписчиков**
- [ ] Альфа/Сбер импорт

**KPI:** MRR ≈ 400-500k₽.

## Q4 2026

**Тема: «AI и Corporate»**

- [ ] AI-инсайты до уровня TradeZella (12 эвристик → 30+ ML-паттернов)
- [ ] Запуск Corporate (multi-account, white-label отчёты)
- [ ] PWA + Service Worker
- [ ] Цель: **3000 платных**

## Q1 2027

**Тема: «Расширение»**

- [ ] Возможно: добавить инвесторов как сегмент (не только трейдеры)
- [ ] Mentor mode (как у TradeZella)
- [ ] Партнёрская программа

## Backlog (когда-нибудь)

- Native mobile (iOS/Android) — после PWA
- Опционы / структурные продукты
- Алготрейдинг / backtest
- **Fincept-derived фичи** (slippage-vs-VWAP, дисциплинарные уведомления, карта концентрации риска и др.) — запарковано, см. [fincept-derived-backlog.md](./fincept-derived-backlog.md). В MVP не берём.

## Не делаем (закрыто)

- Криптобиржи в integrations
- Forex-инструменты
- Bento Grid в UI
- Глассморфизм

## Как обновлять

- Завершили крупную фичу → отметить ✅
- Поменялась тема квартала → новая запись + старая остаётся
- Решили не делать что-то — переносим в «Не делаем» с причиной

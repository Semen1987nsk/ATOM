# ADR-0005: Reverse-Trial 21 день + Free+ + Pro 399₽

**Статус:** Принято (2026-05-14). Реализация запланирована в Q2 2026.
**Supersedes:** раздел «Не тестируем» в [`sales/pricing.md`](../../sales/pricing.md) — правило «никаких 7-дневных trials» сохраняется, но reverse-trial теперь явно допустим. Гипотеза B (Lite-план 199₽) — снята.
**Связанное:** [`ADR-0002`](0002-pd-consent-versioning.md) (двухфазное удаление, поведение API-токена при удалении аккаунта).

## Контекст

Текущая freemium-модель `Free 50 сделок/мес FIFO → Pro 399₽` (зафиксирована в pricing.md v1) — это де-факто **trial, замаскированный под freemium**. Primary persona (активный РФ-трейдер, 30-200 сделок/мес — см. [`personas.md`](../../product/personas.md)) исчерпывает лимит за 1-2 недели и:

- либо платит без понимания ценности Pro-фич (AI, MAE/MFE, Optimal f) — высокий early churn,
- либо уходит и не возвращается — нулевая виральность.

Цель Q3 2026 — 1000 платных подписчиков ([`roadmap.md`](../../strategy/roadmap.md)). При гипотетической конверсии 3-5% это требует ~20-30k регистраций, что нереалистично для текущего CAC-бюджета.

**Освобождная категория в нише:** ни один прямой конкурент в trading-журналах не делает настоящий freemium (TradeZella — 7-day trial + карта, Edgewonk — 14-day, Tradervue — 30 trades, TraderMake/Tradary — платные с пробным периодом). См. [`competitive-landscape.md`](../../strategy/competitive-landscape.md).

## Решение

**Reverse-Trial 21 день → Free+ (навсегда) → Pro 399₽**, по модели Notion/Vercel/Linear.

### Схема

1. **При регистрации:** юзер автоматически получает 21 день полного Pro без карты. Привязка trial к `user_id + email + cookie` — повторная регистрация не выдаёт новый trial.
2. **На D-7 / D-3 / D-1 до конца trial:** email + push «через N дней trial → Free+, история сохранится».
3. **На D+21:** автоматический downgrade в Free+. Вся накопленная история сохраняется, Pro-фичи «замораживаются» (видны как архив, помечены `🧊 Pro`-бейджем, inline-CTA на upgrade). См. [`feature-canon/04-downgrade-experience.md`](../../product/feature-canon/04-downgrade-experience.md).
4. **D+21 + D+28:** email с PDF-отчётом trial-периода + re-engagement.

### Длительность 21 день — обоснование

- **14 дней мало.** Активный РФ-трейдер делает 15-20 сделок за 2 недели. Этого недостаточно для статистически значимых AI-инсайтов и Optimal f (нужно ~30 сделок). Notion 14d-trial оправдан, потому что B2B-онбординг быстрее.
- **30 дней много.** COGS Anthropic API на trial-юзере растёт линейно. При конверсии 3% и trial 30 дней маржа Pro съедается за первые 2 месяца. Психологический шок при downgrade тоже больше.
- **21 день — оптимум.** ~3 рабочих недели MOEX, юзер успевает накопить 15-30 сделок и увидеть 1-2 AI-инсайта.

### Защита Pro-ценности

**Главный depth-gate — API-синхронизация Тинькофф.** В Free+ она остановлена (sync_enabled=False), но зашифрованный токен остаётся в БД. При upgrade на Pro sync включается мгновенно без повторного ввода токена — снижает friction upgrade в 3-4×. См. compliance-аспект в [`152-fz-status.md`](../../compliance/152-fz-status.md) и Policy v2 в [`policy-versions.md`](../../compliance/policy-versions.md).

**«Замороженные» фичи на Free+:**

- Расширенные метрики (Sharpe, Sortino, Calmar, Ulcer, K-Ratio) — заморожены на дату downgrade
- MAE/MFE из MOEX — только архив trial-периода
- AI-инсайты — 2 последних видимы, новые не генерируются
- Optimal f / SQN / Monte Carlo — финальный PDF-отчёт trial доступен навсегда
- Trade Replay — read-only для сделок trial-периода

«Заморожено» = визуально присутствует с `🧊 Pro`-бейджем + inline-CTA «Возобновить → Pro 399₽». Никаких всплывающих модалок (тон Empirik, см. [`marketing/positioning.md`](../../marketing/positioning.md)).

### Карта не запрашивается при старте trial

Критично. Анти-паттерн TradeZella (7 дней + карта обязательна) провоцирует отписки на D+5. Reverse-trial без карты = юзер не воспринимает регистрацию как покупку, а downgrade — как мягкое продолжение, не как «отказ платить».

## Технические следствия

### Backend (`backend/`)

1. **Модель `Subscription`:** добавить статусы `trial_active`, `trial_expired`, `free_plus` (в дополнение к существующим `free`, `pro`, `corporate`). Миграция Alembic.
2. **Поле `account.sync_enabled: bool`** — фильтрация в `services/sync_scheduler.py`. Free+ юзеры пропускаются.
3. **Поле `trade.created_during_trial: bool`** — для read-only Trade Replay на Free+.
4. **Поле `trade.mae_mfe_archived: bool`** — отличие архивных MAE/MFE от live.
5. **Job `services/subscription_service.expire_trials()`** — раз в час, переводит `trial_active → free_plus` при `trial_ended_at < now()`. Сохраняет токен брокера, выключает `sync_enabled`.
6. **Email-flow** D-7/D-3/D-1/D+7/D+21/D+28 через существующий уведомлятор.
7. **Cap Anthropic API в trial:** ≤30 запросов за 21 день (запись в `ai_request_log`, проверка перед вызовом).

### Frontend (`frontend/`)

1. `frontend/src/app/pricing/page.tsx` — три колонки Trial / Free+ / Pro.
2. Компонент `<FrozenFeatureBadge variant="pro" />` — единый бейдж для замороженных виджетов.
3. Баннер trial-countdown в `/dashboard` для дней D-7/D-3/D-1.
4. In-app экран D+21 «Подарок за trial» с PDF-download.

### Compliance (`compliance/`)

- Policy v2 — раздел про хранение API-токена на Free+ (см. [`policy-versions.md`](../../compliance/policy-versions.md)).
- При запросе на удаление аккаунта (`DELETE /auth/me`, Phase 1) — токен отзывается СРАЗУ, как в ADR-0002. Reverse-trial не меняет это поведение.

### Feature-flag

`reverse_trial_v1_enabled` (per-user). Позволяет откатить модель в случае падения конверсии ниже 2% или роста COGS на trial выше 100₽.

## Последствия

### Плюсы

- **Расширение воронки:** регистрация без барьера → больше Free+ юзеров → больше виральности (sharable trade cards, K-фактор ≥0.4).
- **Loss aversion → конверсия 7-10%** (бенчмарк Kyle Poyar reverse-trials, подтверждено Notion 17→25% B2B). Цель 1000 платных к Q3 2026 достижима с ~10-14k регистраций вместо ~20-30k.
- **Снижение friction upgrade:** API-токен в БД при downgrade → один клик для возврата на Pro.
- **Decay архивных метрик во времени:** Optimal f / Sharpe / SQN чувствительны к меняющемуся капиталу. Через 2-3 месяца после downgrade «Optimal f = 0.18 на дату X» теряет актуальность — юзер видит дату и осознаёт потребность в live-расчёте. Естественный, ненавязчивый триггер.

> **Замечание про НДФЛ.** В РФ брокер — налоговый агент, удерживает НДФЛ автоматически. Декларация (3-НДФЛ) актуальна только для узких кейсов (перенос убытков прошлых лет, мульти-брокерская консолидация, иностранные брокеры). Это **не главный upgrade-триггер** для primary persona — затрагивает <10% активных трейдеров. Помощник 3-НДФЛ — на roadmap как Pro-фича, но не в Q2/Q3 2026.

### Минусы / риски

1. **COGS на trial-юзере (~80₽)** — допустим только при конверсии ≥3%. Митигация: hard cap 30 AI-запросов; кэш MOEX-свечей; on-demand рендеринг Replay. См. [`finance/unit-economics.md`](../../finance/unit-economics.md).
2. **Каннибализация Pro фейк-аккаунтами** — низкий риск (399₽/мес не та сумма, ради которой возиться). Митигация: привязка trial к email + cookie + IP.
3. **Юзер забыл про trial → шок downgrade** — главный UX-риск. Митигация: 4 уведомления (D-7/D-3/D-1/D+21 с PDF-подарком). См. [`feature-canon/04-downgrade-experience.md`](../../product/feature-canon/04-downgrade-experience.md).
4. **Compliance:** хранение токена на Free+ — новая цель обработки, требует Policy v2 и юриста.

## Поведенческие правила

1. **Никогда не запрашиваем карту при старте trial.** Это превратит reverse-trial в classic-trial, потеряем главное отличие.
2. **Free+ навсегда не закрываем.** История сохраняется. Лимит «50 сделок» больше не существует.
3. **Замороженные виджеты не скрываем.** Видны как архив с inline-CTA. Скрытие = ощущение «обмана».
4. **При upgrade Pro:** sync включается мгновенно без повторного ввода токена. Если переспросить токен — теряем 3-4× в конверсии upgrade.
5. **A/B-тест длительности (14 vs 21 vs 30 дней)** — не раньше чем через 2 месяца после запуска и при наборе ≥3000 trial-юзеров.

## Связанное

- [`sales/pricing.md`](../../sales/pricing.md) — действующая сетка
- [`finance/unit-economics.md`](../../finance/unit-economics.md) — COGS/payback расчёты
- [`product/feature-canon/04-downgrade-experience.md`](../../product/feature-canon/04-downgrade-experience.md) — UX эталон замороженных виджетов
- [`compliance/policy-versions.md`](../../compliance/policy-versions.md) — Policy v2
- [`ADR-0002`](0002-pd-consent-versioning.md) — поведение токена при удалении аккаунта
- [`strategy/roadmap.md`](../../strategy/roadmap.md) — Q2 2026 пункты реализации

## Источники

- [Kyle Poyar / Growth Unhinged — Guide to Reverse Trials](https://www.growthunhinged.com/p/your-guide-to-reverse-trials)
- [OpenView — Freemium vs Free Trial](https://openviewpartners.com/blog/freemium-vs-free-trial/)
- [Notion paid plan trials](https://www.notion.com/help/paid-plan-trials)
- [Lenny Rachitsky — What is good free-to-paid conversion](https://www.lennysnewsletter.com/p/what-is-a-good-free-to-paid-conversion)

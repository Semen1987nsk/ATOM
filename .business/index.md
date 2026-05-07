# Карта базы знаний Eqio

База разбита на 9 доменов. Каждая папка — отдельный домен с собственным `CLAUDE.md` (что в папке + когда читать).

## Когда что читать

| Если задача про… | Читай в первую очередь |
|---|---|
| Видение, стратегия, рынок РФ, конкуренты | [`strategy/`](strategy/) |
| Дизайн, UX, новый виджет, эталон фичи | [`product/`](product/), особенно `product/feature-canon/` |
| Лендинг, посты, SEO, тон голоса | [`marketing/`](marketing/) |
| Цена, тарифы, возражения, партнёрка | [`sales/`](sales/) |
| 152-ФЗ, политика, удаление аккаунта, РКН | [`compliance/`](compliance/) — **обязательно** |
| Архитектура, рефакторинг, аудит, стек | [`tech/`](tech/) |
| Деплой, мониторинг, инциденты | [`operations/`](operations/) |
| Юнит-экономика, бюджет | [`finance/`](finance/) |
| Что было в прошлых сессиях, накопленный опыт | [`history/`](history/) |

## Карта файлов

### strategy/
- [`vision.md`](strategy/vision.md) — миссия, позиционирование, цель на 12 мес
- [`roadmap.md`](strategy/roadmap.md) — дорожная карта по кварталам
- [`competitive-landscape.md`](strategy/competitive-landscape.md) — TraderMake / Tradary / TradeZella + где Eqio выигрывает

### product/
- [`personas.md`](product/personas.md) — кто пользуется (активный РФ-трейдер, проп-фонд)
- [`design-system.md`](product/design-system.md) — цвета, шрифты, токены, анти-паттерны
- [`reference-screens.md`](product/reference-screens.md) — карта 60+ скриншотов в корне репозитория
- [`ux-laws.md`](product/ux-laws.md) — поведенческие принципы (плотность, скорость, скепсис трейдера)
- [`feature-canon/`](product/feature-canon/) — **эталоны для копирования стиля**:
  - [`01-dashboard.md`](product/feature-canon/01-dashboard.md) — эталон №1 (главный дашборд)
  - [`02-mae-mfe.md`](product/feature-canon/02-mae-mfe.md) — эталон №2 (автоанализ MOEX)
  - [`03-trade-replay.md`](product/feature-canon/03-trade-replay.md) — эталон №3 (свечи + маркеры)

### marketing/
- [`positioning.md`](marketing/positioning.md) — «MOEX-нативный AI-журнал» (по итогам аудита)
- [`messaging.md`](marketing/messaging.md) — тон голоса и ключевые сообщения
- [`content-plan.md`](marketing/content-plan.md) — каналы (Smart-Lab, YouTube, Telegram)
- [`seo-keywords.md`](marketing/seo-keywords.md) — ядро запросов для РФ

### sales/
- [`pricing.md`](sales/pricing.md) — текущие и тестируемые тарифы
- [`tariff-comparison.md`](sales/tariff-comparison.md) — сравнение с конкурентами в рублях
- [`objection-handling.md`](sales/objection-handling.md) — возражения трейдеров
- [`partner-program.md`](sales/partner-program.md) — партнёрка

### compliance/
- [`152-fz-status.md`](compliance/152-fz-status.md) — **статус 7 пунктов чеклиста**
- [`policy-versions.md`](compliance/policy-versions.md) — версии политики конфиденциальности
- [`rkn-notification.md`](compliance/rkn-notification.md) — уведомление по форме Н-152
- [`data-retention.md`](compliance/data-retention.md) — сроки хранения по 152-ФЗ vs 402-ФЗ

### tech/
- [`architecture.md`](tech/architecture.md) — backend + frontend + интеграции
- [`audit-report.md`](tech/audit-report.md) — **независимый аудит на 33 метрики (07.05.2026)**
- [`stack.md`](tech/stack.md) — MCP-серверы / скиллы / VS Code расширения
- [`api-contracts.md`](tech/api-contracts.md) — ключевые ендпоинты
- [`decisions/`](tech/decisions/) — ADR (architecture decision records):
  - [`0001-sqlite-as-dev-db.md`](tech/decisions/0001-sqlite-as-dev-db.md)
  - [`0002-pd-consent-versioning.md`](tech/decisions/0002-pd-consent-versioning.md)
  - [`0003-server-components-strategy.md`](tech/decisions/0003-server-components-strategy.md)
  - [`0004-moex-rate-limit.md`](tech/decisions/0004-moex-rate-limit.md)

### operations/
- [`deployment.md`](operations/deployment.md) — как и куда деплоим
- [`monitoring.md`](operations/monitoring.md) — Sentry, метрики, алерты
- [`incident-runbook.md`](operations/incident-runbook.md) — что делать когда упало

### finance/
- [`unit-economics.md`](finance/unit-economics.md) — CAC / LTV / break-even
- [`budget.md`](finance/budget.md) — текущий бюджет и буфер

### history/
- [`2026-05-07-audit-and-stack-up.md`](history/2026-05-07-audit-and-stack-up.md) — стартовая сессия: аудит, скиллы, 4 PR, база знаний

## Триггеры на чтение конкретных файлов

| Слово в задаче | Что Claude обязан прочитать **до** ответа |
|---|---|
| `152-ФЗ`, `ПД`, `согласие`, `удаление аккаунта`, `РКН` | `compliance/152-fz-status.md` + `compliance/policy-versions.md` |
| `MOEX`, `ISS`, `свечи`, `котировки`, `MAE`, `MFE` | `tech/decisions/0004-moex-rate-limit.md` + skill `moex-iss-api-patterns` |
| `новый виджет`, `новая страница`, `дашборд`, `вёрстка` | `product/design-system.md` + `product/feature-canon/01-dashboard.md` |
| `тариф`, `цена`, `пейволл`, `pro-план` | `sales/pricing.md` + `sales/tariff-comparison.md` |
| `конкурент`, `TraderMake`, `Tradary`, `TradeZella` | `strategy/competitive-landscape.md` |
| `деплой`, `прод`, `staging` | `operations/deployment.md` |
| `аудит`, `чек-лист готовности` | `tech/audit-report.md` |

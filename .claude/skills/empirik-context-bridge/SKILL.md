---
name: empirik-context-bridge
description: Use when working on the Empirik trading journal project (`C:\Users\Administrator\Empirik\ATOM`). Forces consultation of `.business/` knowledge base before answering. Triggers on broad project vocabulary — "Empirik", "дашборд", "трейдер", "MOEX", "Тинькофф", "152-ФЗ", "тариф", "Pro план", "MAE", "MFE", "Trade Replay", "Optimal f", "SQN", "конкурент", "TraderMake", "Tradary", "TradeZella", "feature canon", "design system", "канон", "эталон", "позиционирование", "стратегия", "compliance", "deployment", "ADR", "audit", "RKN", "YooKassa".
---

# Empirik Context Bridge

Этот скилл срабатывает на широкий набор слов проекта Empirik и **перенаправляет тебя в базу знаний** до того, как начнёшь писать код или план.

## Что делать при срабатывании

### Шаг 1 — открой карту базы знаний

```
Read: C:\Users\Administrator\Empirik\ATOM\.business\index.md
```

Там карта 9 доменов и таблица «Триггеры на чтение конкретных файлов».

### Шаг 2 — найди свой домен по таблице триггеров

| Слово/тема в задаче | Куда идти |
|---|---|
| `152-ФЗ`, `ПД`, `согласие`, `удаление аккаунта`, `РКН`, `политика конфиденциальности` | `compliance/152-fz-status.md` + `compliance/policy-versions.md` |
| `MOEX`, `ISS`, `свечи`, `котировки`, `MAE`, `MFE`, `IMOEX` | `tech/decisions/0004-moex-rate-limit.md` + skill `moex-iss-api-patterns` |
| `новый виджет`, `новая страница`, `дашборд`, `вёрстка`, `UI`, `визуал` | `product/design-system.md` + `product/feature-canon/01-dashboard.md` |
| `Trade Replay`, `свечи на графике` | `product/feature-canon/03-trade-replay.md` |
| `MAE/MFE анализ`, `группировка по тегам` | `product/feature-canon/02-mae-mfe.md` |
| `тариф`, `цена`, `пейволл`, `Pro план`, `подписка` | `sales/pricing.md` + `sales/tariff-comparison.md` |
| `возражение`, `почему так дорого`, `почему 399` | `sales/objection-handling.md` |
| `конкурент`, `TraderMake`, `Tradary`, `TradeZella`, `Edgewonk` | `strategy/competitive-landscape.md` |
| `позиционирование`, `tagline`, `hero`, `лендинг` | `marketing/positioning.md` |
| `тон`, `messaging`, `как писать` | `marketing/messaging.md` |
| `SEO`, `ключевые слова`, `Wordstat` | `marketing/seo-keywords.md` |
| `деплой`, `прод`, `staging`, `Yandex Cloud` | `operations/deployment.md` |
| `мониторинг`, `Sentry`, `алерты` | `operations/monitoring.md` |
| `инцидент`, `упало`, `5xx` | `operations/incident-runbook.md` |
| `аудит`, `чек-лист готовности`, `33 метрики` | `tech/audit-report.md` |
| `архитектура`, `как устроено` | `tech/architecture.md` + `tech/decisions/` |
| `новый роутер`, `миграция БД`, `Alembic`, `N+1` | skill `fastapi-sqlalchemy-patterns` + `tech/architecture.md` |
| `Server Component`, `Suspense`, `dashboard-demo`, `serverApiClient` | skill `nextjs-react19-server-patterns` + `tech/decisions/0003-server-components-strategy.md` |
| `MCP`, `скилл`, `VS Code расширение`, `новая среда` | `tech/stack.md` |
| `cohort`, `unit-economics`, `LTV`, `CAC`, `runway` | `finance/unit-economics.md` |
| `roadmap`, `Q2`, `Q3`, `когда сделаем` | `strategy/roadmap.md` |
| `видение`, `миссия`, `зачем мы это делаем` | `strategy/vision.md` |
| `персона`, `ЦА`, `кто наш юзер` | `product/personas.md` |

### Шаг 3 — прочитай профильный CLAUDE.md в подпапке

В каждой подпапке (`strategy/`, `product/`, `marketing/`, …) есть свой `CLAUDE.md` с локальными правилами и картой файлов. Это ~5-15 строк, но они задают принципы.

### Шаг 4 — прочитай 1-2 ключевых файла

Не нужно загружать всю папку. Прочитай **только то**, что необходимо для текущей задачи. Если задача узкая (например, «обнови чекбокс согласия на регистрации») — достаточно `compliance/152-fz-status.md` и одного ADR.

### Шаг 5 — теперь действуй

Только после этого пиши план/код. В ответе пользователю сошлись на конкретные файлы базы, чтобы было видно — ты её прочитал.

## Когда НЕ срабатывать (false positives)

- Тривиальные правки (опечатка, переименование переменной, форматирование)
- Вопросы про работу самого Claude Code, не про Empirik
- Общие программистские вопросы без проектного контекста

## Принципы

1. **База — точка истины, не справочник.** Если в коде одно, а в базе другое — либо база устарела (обнови), либо код не соответствует канону (исправь, после согласования).
2. **Эталоны не переписываются.** Если фича изменилась — обновляй документ эталона, не его архитектуру.
3. **ADR — append-only.** При смене решения — новый ADR со ссылкой `Supersedes`.
4. **Если узнал что-то ценное — фиксируй**:
   - Кратковременное (под текущую сессию) → `history/YYYY-MM-DD-*.md`
   - Долговременное (паттерн / решение) → ADR в `tech/decisions/`
   - Бизнес-факт → соответствующий домен (`strategy/`, `product/`, …)

## Главный принцип

**Перед задачей — открыть `.business/index.md`.** Это занимает 30 секунд. Это исключает 80% ошибок «не знал, что у нас уже было решение / эталон / правило».

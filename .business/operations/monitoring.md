# Monitoring

> Скелет. Активировать после поднятия prod.

## Что мониторим

### Application

- **Sentry** (self-hosted): ошибки backend + frontend, performance
- Логи через `logger.py` (JSON в проде, ротация 5×5MB)
- request_id correlation через ContextVar — для трассировки

### Инфраструктура

- CPU / RAM / диск — Yandex Cloud Monitoring (встроено)
- БД: connections, slow queries, replication lag
- Redis: hit rate, eviction
- Network: latency from РФ-регионов

## Алерты (must-have)

| Метрика | Порог | Куда |
|---|---|---|
| 5xx error rate > 1% | 5 минут | Telegram (DPO + dev) |
| `/health` падает | 30 сек | Telegram + SMS |
| DB connection pool > 80% | 5 минут | Telegram |
| Disk usage > 85% | 1 час | Telegram |
| Sentry: новый тип ошибки | мгновенно | Telegram |
| Tinkoff API rate-limited | 5 минут | Telegram (warn) |

## Бизнес-метрики (через 6 мес)

- DAU / WAU / MAU
- Конверсия Free → Pro
- Churn rate
- MRR
- LTV / CAC

## Что НЕ делаем

- ❌ Sentry.io (нельзя для РФ-данных по 152-ФЗ)
- ❌ Datadog / New Relic (тоже за рубежом)
- ❌ Google Analytics (приватность + санкции)
- ✅ Вместо: Yandex Metrika (если нужна аналитика поведения)

## Связанное

- `tech/architecture.md` § Безопасность
- `tech/stack.md` § MCP-серверы (Sentry MCP self-hosted)

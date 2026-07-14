# Deployment

> Скелет. Заполнить после переноса на Yandex Cloud.

## Текущее состояние (07.05.2026)

- **Локально:** SQLite + uvicorn / npm dev
- **Docker Compose:** есть в `docker-compose.yml`, но Docker не установлен на dev-машине
- **Production:** **отсутствует** (см. `tech/audit-report.md` C2/C3)

## Целевая архитектура (Q2 2026)

| Компонент | Где | Зачем |
|---|---|---|
| Backend (FastAPI) | Yandex Cloud Compute Cloud | Близко к РФ-юзерам |
| PostgreSQL | Yandex Managed PostgreSQL | Бэкапы, репликация |
| Redis | Yandex Managed Redis | Кэш, rate-limit |
| Frontend (Next.js) | Yandex Cloud Compute или Vercel-РФ-аналог | SSR требует runtime |
| Object Storage | Yandex Object Storage (S3-совместимый) | Скриншоты сделок |
| Sentry | Self-hosted в Yandex Cloud | 152-ФЗ — нельзя слать в sentry.io |

## Прод-требования: БД и Redis (Sprint 1A)

- **DATABASE_URL** — ОБЯЗАТЕЛЬНО PostgreSQL (`postgresql://...`). SQLite в проде
  запрещён кодом (`database._assert_db_safe_for_env`: DEBUG=false + sqlite →
  fail-fast). Причина: single-writer → `database is locked` под нагрузкой.
- **Пул соединений** (env, дефолты в `database.py`): `DB_POOL_SIZE=5`,
  `DB_MAX_OVERFLOW=10`, `DB_POOL_TIMEOUT=30`, `DB_POOL_RECYCLE=1800`, pre-ping on.
  На 500 пользователей при N gunicorn-воркерах суммарные коннекты =
  N × (pool_size + max_overflow). Postgres `max_connections` должен это покрывать
  ЛИБО ставим **PgBouncer** (transaction pooling) — рекомендуется при N×15 > ~100.
- **REDIS_URL** — ОБЯЗАТЕЛЕН в проде: rate-limiter fail-fast без Redis
  (`rate_limiter.py`), а stats-cache без Redis деградирует в per-process
  (¼ hit-rate под N воркерами). Один Redis обслуживает rate-limit и stats
  (ключи stats префиксованы `stats:`).
- **Redis-down:** старт приложения требует Redis (rate-limit fail-fast) —
  осознанный trade-off (безопасность > доступность для brute-force). Stats-cache
  при рантайм-сбое Redis молча пересчитывает (не падает). Старт без Redis —
  только явный `RATE_LIMIT_ENABLED=false` (НЕ рекомендуется).
- **Singleton-воркер:** на N>1 воркерах задать `IS_SCHEDULER_WORKER=false` на
  всех, кроме одного (scheduler + stream-consumers + nightly P&L health —
  синглтоны). Стартовый лог `🩺 Readiness:` печатает db/redis/scheduler_worker.

## Прод-требования: gRPC-резилентность (Sprint 1B)

- **REDIS_URL** теперь обслуживает ещё и **общий per-token rate-limit** к T-Bank
  gRPC (SYNC-02). Без Redis каждый воркер держит свой бакет → эффективный лимит
  = N_workers × `TINKOFF_RATE_LIMIT_PER_MIN`, что пробивает потолок T-Bank
  200/min и ведёт к IP-cooldown. **На N>1 воркерах Redis ОБЯЗАТЕЛЕН** для sync.
- **Глобальный IP-cooldown gate** (SYNC-05) живёт в том же Redis (ключ
  `tinkoff:ip_cooldown`). При IP-уровневом RESOURCE_EXHAUSTED оркестратор
  пропускает прогоны с эскалирующим backoff (`TINKOFF_IP_COOLDOWN_BASE_SECONDS`
  → ×2 → cap `TINKOFF_IP_COOLDOWN_MAX_SECONDS`). Триггер — ≥
  `TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS` различных подключений за один
  прогон (один токен global gate НЕ открывает — для него per-connection circuit).
- **Новые env (дефолты в config.py):**
  `TINKOFF_LIMITER_MAX_WAIT_SECONDS=60`, `TINKOFF_GRPC_CALL_TIMEOUT_SECONDS=30`,
  `TINKOFF_IP_COOLDOWN_BASE_SECONDS=60`, `TINKOFF_IP_COOLDOWN_MAX_SECONDS=600`,
  `TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS=2`.
- **Redis-down degrade (осознанно):** sync-лимитер падает на in-process
  (degraded N×rate, НЕ fail-open — ∞ = бан T-Bank); IP-cooldown gate падает на
  per-process (теряется cross-worker координация, но per-token лимитер и
  per-connection circuit остаются). Старт приложения Redis-сбой sync-слоя НЕ
  блокирует (в отличие от HTTP rate-limiter, который fail-fast).
- **gRPC call-deadline:** каждый RPC ограничен `TINKOFF_GRPC_CALL_TIMEOUT_SECONDS`
  (зависший вызов иначе держит лимитер-токен + семафор). Таймаут → BrokerUnavailable
  (retryable, штатная tenacity-цепь).

## CI/CD (план)

*[добавить когда подключим: GitHub Actions / GitLab CI / Yandex Container Registry]*

## Чеклист перед первым проддеплоем

- [ ] РКН-уведомление подано и одобрено
- [ ] DPO email активен
- [ ] Юрист утвердил `policy-versions.md` v1
- [ ] SECRET_KEY и REFRESH_SECRET_KEY сгенерированы и сохранены в Yandex Lockbox
- [ ] TLS-сертификаты выпущены (Let's Encrypt через certbot)
- [ ] Sentry DSN прописан, PII-фильтр работает
- [ ] Бэкап-план PostgreSQL (раз в сутки + WAL)
- [ ] Мониторинг доступности (`/health` / `/ready`)
- [ ] Smoke-тесты на стейджинге зелёные
- [ ] DNS direct → балансировщик
- [ ] Юкасса в продовом режиме

## Связанное

- `tech/audit-report.md` — блокеры C2/C7/C8
- `monitoring.md` — что смотрим после деплоя

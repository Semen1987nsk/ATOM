# Production-Readiness — дизайн и план по спринтам

**Дата:** 2026-05-23
**Автор:** аудит 7 параллельных доменных проверок + синтез
**Статус:** согласован (дизайн), готов к разворачиванию в implementation-plan

## Решения по scope (согласовано с основателем)

- **Scope:** всё для запуска — инженерия + не-инженерные блокеры (152-ФЗ: РКН, хостинг ПД в РФ, DPO; YooKassa рекуррент + 54-ФЗ). Не-инженерные пункты идут параллельным треком с пометкой «нужно решение основателя/юрист».
- **Темп:** спринт = 2 недели. Исполнение: основатель + Claude (TDD + субагенты), ревью/коммиты — за основателем.
- **Стратегия:** комплексный harden ДО запуска (закрываем большинство High до go-live, включая NET/GROSS-математику, тесты аналитики, фронт-ошибки, a11y). Запуск позже, но зрелее.
- **Масштаб:** right-size под ~500 одновременных пользователей, архитектура — под дальнейший рост (предпочитать Managed-сервисы самодельному HA).

## Контекст и текущее состояние

Eqio/ATOM — SaaS-журнал сделок для ритейл-трейдеров MOEX. Stack: FastAPI + SQLAlchemy 2.0 + Next.js 16/React 19 + Tailwind v4; интеграции Tinkoff/T-Bank gRPC + MOEX ISS; P&L-движок (FIFO, futures varmargin, bonds, options) с cash-anchored reconciliation (ADR-0007/0008).

**Прод ещё НЕ развёрнут** (SQLite локально, нет TLS, нет CD, Sentry/metrics не настроены). То есть это **pre-launch hardening**, не починка живого прода.

**Сильные стороны (не трогаем без причины):** доменная P&L-математика хорошо покрыта тестами; auth-ядро (JWT/bcrypt rounds=14/CSRF double-submit/revocation) солидное; account-scoping консистентен (IDOR не найдено); есть RUNBOOK/ADR/observability-каркас; backend ~61 тест-файл.

## Goals / Non-goals

**Goals:** безопасный, наблюдаемый, нагрузочно-проверенный прод на 500 пользователей; корректные финансовые метрики; устойчивый фронт; автоматический zero-downtime деплой; юридическая готовность к РФ; работающий платный путь.

**Non-goals (в этом плане):** нативный мобайл, доп. брокеры (Финам/БКС/Альфа/Сбер), опционы/структурные, алго/бэктест, AI-инсайты «до уровня TradeZella» — остаются в backlog roadmap. PWA — после запуска.

## Принципы и Definition of Done

- Каждый спринт завершается зелёным и деплоебельным: CI green, миграции roundtrip up/down, smoke на песочнице.
- TDD для логики (math, payments, auth); субагент-ревью (`code-reviewer`/`security-reviewer`) на edge/race для рискового.
- DoD спринта: все задачи закрыты + exit-критерий проверен **объективно** (тест/нагрузка/скрипт/скриншот), не «должно работать».
- Без оверинжиниринга (CLAUDE.md): не плодить абстракции/обработку невозможных случаев; правка по причине, не по симптому.

---

## Реестр находок (аудит) — что нужно доделать

Severity: 🔴 Blocker (гейтит запуск) · 🟠 High · 🟡 Medium · ⚪ Low. Каждой находке присвоен ID для трассировки в implementation-plan. Колонка «Спринт» — где закрываем.

### API & Auth
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| API-01 | 🟠 | `/market/prices`, `/market/futures-specs` без auth и без rate-limit (бесплатный MOEX-прокси, abuse) | `routers/market.py:17,36` | S2 |
| API-02 | 🟠 | `CORS_ORIGIN_REGEX` по умолчанию доверяет всем `*.app.github.dev` | `config.py:220` | S2 |
| API-03 | 🟠 | Нет rate-limit на read-эндпойнтах; `@limiter` только на части | `routers/*` | S2 |
| API-04 | 🟠 | Нет верхней границы `limit` на `/trades/`, `/trades/positions` → memory-DoS | `routers/trades.py:521,539` | S2 |
| API-05 | 🟡 | Refresh-токен не отзывается при использовании (нет ротации) | `auth_service.py:306-324` | S2 |
| API-06 | 🟡 | Политика пароля рассинхрон: reset/change 6, регистрация 12 | `schemas.py:199`, `routers/auth.py:635` | S2 |
| API-07 | 🟡 | Password reset не отзывает активные JWT | `routers/auth.py:648` | S2 |
| API-08 | 🟡 | OAuth `redirect_uri` без server-side allowlist | `routers/auth.py:667` | S2 |
| API-09 | 🟡 | admin `sort_by` через `getattr` без whitelist | `admin_service.py:52` | S2 |
| API-10 | 🟠 | `RATE_LIMIT_ENABLED` без Redis крашит старт (SPOF) | `rate_limiter.py:88-93` | S1 |
| API-11 | 🟡 | Brute-force: только IP 5/min, нет account-lockout | `rate_limiter.py:142` | S2 |
| API-12 | 🟠 | `DEBUG=true` отдаёт traceback; нужен прод-гард старта | `main.py:236` | S2 |
| API-13 | 🟡 | `str(exc)` в ответе (onboarding/import) — утечка внутренней детали | `routers/onboarding.py:91`, `trades.py:432` | S2 |
| API-14 | ⚪ | `/db-check` без auth (дублирует `/ready`) | `main.py:439` | S2 |
| API-15 | 🟡 | `regex=` (deprecated) вместо `pattern=` | `trades.py:537`, `admin.py:1471` | S0 |

### P&L / индикаторы (math)
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| MATH-01 | 🟠 | GROSS вместо NET в 5+ аналитических эндпойнтах (win_rate/profit_factor/RR/setup/symbol/period/psycho) | `stats.py:1153,1562,892`, `stats_advanced.py:63-133` | S4 |
| MATH-02 | 🟠 | `analytics/` без unit-тестов (Sharpe/Sortino/Calmar/Optimal f/SQN/RoR/Kelly/drawdown/MAE-MFE) | `analytics/*` | S4 |
| MATH-03 | 🟠 | MAE/MFE coverage=0 — пайплайн свечей не наполняет данные | `analytics/mae_mfe.py:84` | S4 |
| MATH-04 | 🟠 | RoR — нестандартная формула, игнорит payoff ratio, хардкод 2% | `analytics/risk.py:332-351` | S4 |
| MATH-05 | 🟡 | profit_factor=0 при всех выигрышах (должно UNDEFINED) | `stats.py:1200` | S4 |
| MATH-06 | 🟡 | Sharpe/Sortino на per-trade PnL без нормировки/лейбла | `analytics/risk.py:84-116` | S4 |
| MATH-07 | 🟡 | Calmar: два источника CAGR расходятся (initial_balance vs deposits) | `stats.py:529`, `stats_advanced.py:77-82` | S4 |
| MATH-08 | 🟡 | MAE/MFE «profit left» для futures использует cached PV (риск ×1000) | `analytics/mae_mfe.py:139-150` | S4 |
| MATH-09 | 🟡 | Reconcile-tool пороги (1%) не совпадают с ADR-0008 (5/25%) | `tools/reconcile_journal_vs_cash.py:328-336` | S4 |
| MATH-10 | 🟡 | `PRIMARY_ORDER`=TRADE, но не в FIFO `_BUY/_SELL_TYPES` (тихий divergence) | `cash_flow_classification.py:174`, `fifo_matching.py:78-79` | S4 |
| MATH-11 | 🟡 | Empirical PV из первого слайса (scaled-in futures bias) | `futures.py:213-218` | S4 |

### Синхронизация (Tinkoff/MOEX)
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| SYNC-01 | 🔴 | `stream_manager` стартует на всех воркерах (нет IS_SCHEDULER_WORKER) → IP-cooldown T-Bank | `main.py:127` | S0 |
| SYNC-02 | 🟠 | Межтокенный rate-limit сломан под мульти-воркером (per-process aiolimiter) → 3-4× лимита | `client_factory.py:92-101` | S1 |
| SYNC-03 | 🟠 | gRPC вызовы без call-level timeout (зависший вызов держит lock+semaphore) | `client_factory.py:169`, `operations_client.py:115` | S1 |
| SYNC-04 | 🟠 | Синхронный `httpx.Client` в `moex_service` блокирует event-loop | `moex_service.py:119` | S3 |
| SYNC-05 | 🟠 | Нет глобального backoff на IP-cooldown → retry-шторм продлевает outage | `orchestrator.py`, `client_factory.py` | S1 |
| SYNC-06 | 🟡 | Advisory-lock connection leak при `CancelledError` на shutdown | `sync_scheduler.py:379-388` | S1 |
| SYNC-07 | 🟡 | Stream rate-limiter: 1 токен на весь стрим (обход лимита на push-событиях) | `operations_stream_client.py:129-137` | S1 |
| SYNC-08 | 🟡 | Курсор сохраняется до завершения FIFO/positions (stale после crash) | `pipeline.py:671-701` | S3 |
| SYNC-09 | 🟡 | `_replace_positions_from_live` DELETE-then-INSERT без savepoint | `pipeline.py:1079-1083` | S3 |
| SYNC-10 | 🟡 | N+1 в `_select_due_connection_ids` | `orchestrator.py:239-245` | S3 |
| SYNC-11 | ⚪ | Утечки per-process: limiters/account_locks никогда не чистятся | `client_factory.py`, `stream_manager.py:151` | S3 |

### Безопасность & Compliance
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| SEC-01 | 🔴 | Нет TLS в nginx (cleartext креды, Secure-куки не уйдут) | `nginx/nginx.conf:45` | S2 |
| SEC-02 | 🔴 | РКН-уведомление не подано | `.business/compliance/rkn-notification.md` | Легал |
| SEC-03 | 🔴 | ПД не хостится в РФ (локализация ст.18 ч.5) | `.business/compliance/152-fz-status.md:15` | Легал |
| SEC-04 | 🟠 | `.env.local.bak` не в `.gitignore` (риск утечки секретов) | `.gitignore`, `backend/.env.local.bak` | S0 |
| SEC-05 | 🟠 | `python-jose` (заброшен, CVE-класс) → PyJWT | `requirements.lock:133` | S2 |
| SEC-06 | 🟠 | `requirements.lock` fastapi 0.114 vs `requirements.txt` 0.136 | `requirements.lock:53` | S0 |
| SEC-07 | 🟡 | Excel-импорт без magic-byte/декомпресс-лимита (zip-bomb) | `routers/trades.py:244` | S2 |
| SEC-08 | 🟡 | JWT в теле ответа (помимо куки) — лишняя поверхность | `routers/auth.py:99,135` | S2 |
| SEC-09 | 🟡 | Reset-токен в GET-URL (логи/история/Referer) | `routers/auth.py:596` | S2 |
| SEC-10 | 🟡 | Email (PII) в логах INFO | `routers/auth.py:57,97,133` | S2 |
| SEC-11 | 🟡 | Cookie-consent только в localStorage, не server-side | `CookieConsent.tsx` | Легал |
| SEC-12 | 🟡 | Policy SHA-256 не посчитан; юрист не утвердил | `.business/compliance/policy-versions.md:7` | Легал |
| SEC-13 | ⚪ | Ticker без allowlist в MOEX-URL | `market_service.py:385` | S2 |
| SEC-14 | ⚪ | CSP `unsafe-inline` в script-src | `middleware.py:66` | S5 |
| SEC-15 | 🔴 | DPO/`privacy@eqio.ru`/юрлицо отсутствуют | `.business/compliance/152-fz-status.md:10` | Легал |

### Производительность / БД / нагрузка
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| PERF-01 | 🔴 | SQLite в проде (single writer, нет WAL) → `database is locked` | `config.py:207`, `database.py:32-43` | S1 |
| PERF-02 | 🟠 | Пул БД мал (5+10 на воркер); нужен PgBouncer | `database.py:50-51` | S1 |
| PERF-03 | 🔴 | Синхронный `db.commit()` access-log в async-middleware блокирует loop | `middleware.py:190-203` | S3 |
| PERF-04 | 🟠 | Синхронный `requests.get` в `/market/prices` блокирует loop | `routers/market.py:29` | S3 |
| PERF-05 | 🟠 | Кэш per-process (stats/market) под 4 воркерами → ¼ эффективности | `services/stats_cache.py:113` | S1 |
| PERF-06 | 🟠 | N+1 в `/trades/positions` (PositionORM на каждую позицию) | `routers/trades.py:615-623` | S3 |
| PERF-07 | 🟠 | `/stats/` грузит все трейды и пересчитывает всё на каждый запрос | `stats.py:132-785` | S3 |
| PERF-08 | 🟡 | Отсутствуют composite-индексы (operations type+state, access_log, tags GIN) | `models.py` | S3 |
| PERF-09 | 🟡 | Безграничный рост access_log/revoked_tokens/sync_events (нет TTL) | `models.py` | S3 |
| PERF-10 | 🟡 | Нет пагинации `/trades/positions`; equity_curve без downsample | `trades.py:538`, `stats.py` | S3 |
| PERF-11 | 🟡 | Nightly P&L health на всех воркерах (если IS_SCHEDULER_WORKER не задан) | `sync_scheduler.py:260-280` | S1 |

### Frontend
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| FE-01 | 🟠 | Дашборд глотает ошибки fetch как «нет данных» | `app/page.tsx:254-258` | S5 |
| FE-02 | 🟠 | 5 analysis-страниц: ошибка = пустое состояние | `analysis/calendar`,`setups`,`review`,`screenshots`,`tags` | S5 |
| FE-03 | 🟠 | `api.generated.ts` — пустая заглушка (типы фиктивны) | `src/types/api.generated.ts` | S5 |
| FE-04 | 🟠 | Нет focus-visible на кнопках (WCAG 2.4.7 fail) | `app/globals.css` | S5 |
| FE-05 | 🟠 | Add/Edit модалки в обход `<Modal>` (нет role/aria/focus-trap/ESC) | `AddTradeModal.tsx`,`EditTradeModal.tsx` | S5 |
| FE-06 | 🟡 | Нет `error.tsx`/`loading.tsx` бандарей нигде | `src/app/` | S5 |
| FE-07 | 🟡 | TanStack Query настроен, но не используется (двойной data-слой) | `queries.ts` | S5 |
| FE-08 | 🟡 | 36/36 страниц `use client` (нет RSC); history/page.tsx 1838 строк | `src/app/**` | S5 |
| FE-09 | 🟡 | Recharts без lazy; `next/image` `unoptimized` | разные | S5 |
| FE-10 | 🟡 | Дубль-поллинг sync-status (2 компонента, независимые интервалы) | `BrokerStatusBadge.tsx`,`SyncStatusIndicator.tsx` | S5 |
| FE-11 | 🟡 | Design-system нарушения (blur-orbs в manual, text-neon, animate-pulse) | `manual/page.tsx`, модалки | S5 |
| FE-12 | 🟡 | Нет component/E2E тестов; критичная логика (apiClient 401-retry, AuthContext) непокрыта | — | S5 |

### Инфраструктура / Observability / CI-CD
| ID | Sev | Находка | Evidence | Спринт |
|----|-----|---------|----------|--------|
| INFRA-01 | 🔴 | CI ставит без `--extra-index-url` → брокерский слой не собирается/не тестится | `.github/workflows/ci.yml:60-61` | S0 |
| INFRA-02 | 🔴 | Sentry не настроен + нет `/metrics` + нет алертинга | `observability.py`, `config.py:232` | S6 |
| INFRA-03 | 🔴 | Нет CD; деплой = ручной `systemctl restart` (даунтайм) | `ci.yml`, `RUNBOOK.md` | S6 |
| INFRA-04 | 🟠 | Нет gzip в nginx | `nginx/nginx.conf` | S2 |
| INFRA-05 | 🟠 | Нет nginx-level rate-limit (defense-in-depth) | `nginx/nginx.conf` | S2 |
| INFRA-06 | 🟠 | Frontend не подключён к nginx (`return 404`) | `nginx/nginx.conf:76-79` | S6 |
| INFRA-07 | 🟠 | Секрет-менеджмент прода не реализован (Lockbox) | `deployment.md` | S6/Легал |
| INFRA-08 | 🟠 | Нет zero-downtime деплоя; SPOF на каждом контейнере | `RUNBOOK.md`, compose | S6 |
| INFRA-09 | 🟠 | Бэкап только локальный (S3 опционально); нет PITR | `backup_db.sh:49` | S6 |
| INFRA-10 | 🟡 | CI: vitest/tsc/mypy/ruff не гейтят; pip-audit soft-fail; ESLint soft-fail | `ci.yml` | S0 |
| INFRA-11 | 🟡 | `--forwarded-allow-ips "*"` доверяет всем XFF | `Dockerfile:82` | S2 |
| INFRA-12 | 🟡 | Backend coverage gate 40% (мало для финтеха) | `ci.yml:87` | S4/S5 |
| INFRA-13 | 🟡 | `AUTO_INIT_DB=true` в CI vs прод-гард Postgres | `ci.yml:81` | S0 |
| INFRA-14 | ⚪ | Base-образы не pinned по digest; нет SAST/Trivy | `Dockerfile`, `ci.yml` | S6 |
| INFRA-15 | 🟡 | `MASTER_KEY_B64` без hard-fail при пустом в проде | `config.py:298` | S0 |

---

## План по спринтам

### Sprint 0 — Stop-the-bleeding + правдивый CI (≈3–5 дней)
**Цель:** убрать foot-gun’ы и сделать CI честным (иначе остальные спринты не верифицируются).
**Состав:** SEC-04, SEC-06, SYNC-01, INFRA-01, INFRA-10, INFRA-13, INFRA-15, API-15.
**Exit:** CI собирает брокерский слой и гоняет фронт-тесты (vitest)+tsc; нет секретов в трекинге; мульти-воркер не плодит стримы; lockfile синхронен.

### Sprint 1 — Деплой-фундамент и мульти-воркер безопасность
**Цель:** платформа работает на Postgres+Redis в N воркеров без дублей и сломанного rate-limit.
**Состав:** PERF-01, PERF-02, PERF-05, PERF-11, SYNC-02, SYNC-03, SYNC-05, SYNC-06, SYNC-07, API-10.
**Exit:** приложение на Postgres+Redis, кэш и rate-limit общие; gRPC с таймаутами; worker-модель задокументирована в RUNBOOK; нагрузочный smoke без `database is locked`.

### Sprint 2 — Безопасность и API-hardening + TLS
**Цель:** HTTPS вживую, OWASP-топ закрыт, abuse-поверхность ограничена.
**Состав:** SEC-01, SEC-05, SEC-07, SEC-08, SEC-09, SEC-10, SEC-13, INFRA-04, INFRA-05, INFRA-11, API-01..09, API-11..14.
**Exit:** TLS+HSTS+gzip+nginx-rate-limit; `security-reviewer` субагент — без High; abuse-эндпойнты закрыты; PyJWT вместо jose.

### Sprint 3 — Производительность и нагрузка
**Цель:** держим 500 одновременных с запасом; event-loop не блокируется.
**Состав:** PERF-03, PERF-04, PERF-06, PERF-07, PERF-08, PERF-09, PERF-10, SYNC-04, SYNC-08, SYNC-09, SYNC-10, SYNC-11.
**Exit:** нагрузочный тест (k6/locust) 500 одновременных проходит, зафиксированы SLO (p95, error-rate, pool); индексы и cleanup-джобы в проде.

### Sprint 4 — Корректность P&L / индикаторов
**Цель:** каждая показываемая метрика корректна и покрыта тестом.
**Состав:** MATH-01..11, INFRA-12 (частично — coverage математики).
**Exit:** NET везде; `analytics/` тест-сьют зелёный; MAE/MFE coverage>0 + метрика; reconcile-tool как non-blocking CI-гейт по ADR-0008.

### Sprint 5 — Фронтенд: устойчивость, типы, a11y
**Цель:** нет тихого проглатывания ошибок; реальные типы; WCAG-базис.
**Состав:** FE-01..12, SEC-14.
**Exit:** error+retry на всех data-страницах + `error.tsx`/`loading.tsx`; `api.generated.ts` сгенерирован и используется; focus-ring и модалки-примитив; component-тесты для критичной логики; бандл легче (RSC/lazy Recharts).

### Sprint 6 — Обсервабилити, CD, надёжность
**Цель:** прод наблюдаем, деплой автоматический и zero-downtime, есть HA.
**Состав:** INFRA-02, INFRA-03, INFRA-06, INFRA-07, INFRA-08, INFRA-09, INFRA-14.
**Exit:** Sentry+`/metrics`+алерты+uptime; CD build→registry→rolling с health-gate; offsite-бэкап+PITR+restore-тест в CI; Managed PG/Redis + 2-я реплика backend; rollback по image-тегам.

### Sprint 7 — Платежи (YooKassa) + подписка
**Цель:** работающий платный путь e2e.
**Состав:** YooKassa рекуррент + 54-ФЗ чеки; вебхук-HMAC в прод; Subscription-статусы (trial_active/free_plus); downgrade-job D+21; `sync_enabled`-гейтинг Free+; reverse-trial флоу (email/push D-7/D-3/D-1/D+7), `/pricing`, `<FrozenFeatureBadge/>`.
**Exit:** оплата и рекуррент в песочнице→прод; downgrade проверен; чеки 54-ФЗ выставляются.

### Sprint 8 — Pre-launch валидация и go-live
**Цель:** все гейты зелёные → запуск.
**Состав:** полный security re-review (+опц. пентест); soak-тест 500; чеклист 152-ФЗ 100%; staged rollout (beta-когорта → 500); runbook-дрели (rollback/инцидент).
**Exit:** go-live.

### ⟂ Параллельный трек — Легал/152-ФЗ (владелец: основатель)
Идёт вдоль S1–S6, гейтит только запуск. Состав: SEC-02, SEC-03, SEC-11, SEC-12, SEC-15, INFRA-07 (Lockbox/хостинг РФ).
- Юрлицо (ИП/ООО) → назначить DPO → `privacy@eqio.ru`.
- РКН-уведомление (форма Н-152) подано.
- Хостинг ПД в РФ (Yandex Cloud/Selectel) — стыкуется с инфрой S1/S6.
- Юрист утверждает Privacy Policy v2; cookie-consent с категориями + server-side хранение; SHA-256 версии политики.

---

## Объём и тайминг
Sprint 0 (~неделя) + 8 спринтов × 2 недели ≈ **~17 недель** инженерии. Легал — параллельно. Запуск — после S6 + закрытого легал-трека; S7 (платежи) частично параллелится с S5/S6.

## Риски и митигации
- **T-Bank IP-cooldown при мульти-воркере** — закрываем в S0 (SYNC-01) до любого мульти-воркер деплоя.
- **Регрессии математики при NET-правке** — TDD-сьют (S4) до изменения формул; reconcile-гейт.
- **Легал блокирует запуск дольше инженерии** — стартует параллельно с S1, не в конце.
- **Managed-миграция (PG/Redis) ломает конфиги** — делаем в S6 за отдельный roundtrip с restore-тестом.

## Открытые допущения
- Целевой хостинг — Yandex Cloud (Managed PG/Redis, Lockbox, Container Registry, Monitoring) — по STACK.md; уточнить при S1/S6.
- Reverse-trial модель (ADR-0005) остаётся продуктовой основой платежей (S7).
- Доп. брокеры и PWA — вне scope этого плана (backlog roadmap).

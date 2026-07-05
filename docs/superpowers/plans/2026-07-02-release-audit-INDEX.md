# Полистата — Предрелизный аудит: МАСТЕР-ИНДЕКС и рабочий регламент

> **ЯКОРЬ ВОССТАНОВЛЕНИЯ ПОСЛЕ /compact.** Этот файл — единственный источник правды по прогрессу.
> Если контекст потерян: (1) прочитай файл целиком; (2) найди первую незакрытую задачу в реестре;
> (3) открой план соответствующего спринта; (4) продолжай с TDD-цикла этой задачи.

**Дата аудита:** 2026-07-02  
**Ветка:** `feat/rebrand-empirik` (якорь `89a1e33`; +13 незапушенных коммитов ADR-0010 + ~28 незакоммиченных файлов ребренда — НЕЗАВЕРШЁННАЯ работа, НЕ откатывать)  
**Оценка аудита:** 6/10 — не запускать без Спринтов 1–2; полный релиз-гейт после Спринта 4.  
**Всего находок (после дедупа):** 93 — 2 CRITICAL, 31 HIGH, 36 MEDIUM, 24 LOW.

---

## Как построена работа (прочитай ПЕРЕД первой задачей)

**Метод:** superpowers **subagent-driven-development** — свежий субагент на каждую задачу, между задачами двухстадийное ревью (code-reviewer + security-reviewer где помечено 🔐). Каждая задача = строгий **TDD red→green→refactor**.

**Почему так:** объём 4 спринта, контекст будет компактиться. Свежий субагент = чистый контекст без «срезания углов». Планы спринтов самодостаточны (zero-context) и переживают компакт.

### Порядок исполнения одной задачи
1. Открыть план спринта, найти задачу `SN-XX`.
2. Диспатчить субагента с полным текстом задачи (он видит только свою задачу).
3. Субагент: падающий тест → убедиться что падает → минимальный фикс → тест зелёный → коммит.
4. Diff → **code-reviewer**; для 🔐-задач дополнительно **security-reviewer**.
5. Прогнать гейт (ниже). Отметить `[x]` в реестре ЭТОГО файла.
6. Следующая задача.

### Гейты «done» по типу изменения
| Тип | Команда проверки |
|---|---|
| Backend-логика | `cd backend && C:/Python314/python.exe -m pytest tests/unit -q` + импорт `C:/Python314/python.exe -c "import main"` |
| Миграция БД | врем. БД: `DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head` + `downgrade base` + `alembic check`. **atom.db не трогать.** Перед релизом — реальный Postgres 16. |
| Frontend UI | `cd frontend && npx vitest run --maxWorkers=1` + `npx tsc --noEmit` + ручной проход в браузере |
| API endpoint | curl smoke на `http://localhost:8000` + 1 happy + 1 error unit-тест |
| E2E | backend :8000 + `npm run dev -- -p 3001`; при «Unable to acquire lock» убить залипшие `next dev` и удалить `frontend/.next/dev/lock` |

### Окружение (Windows-хост)
- **Python:** `C:/Python314/python.exe` (зависимости стоят там; системный python / Robot-venv НЕ подходят).
- **Backend** уже на `http://localhost:8000`. GET-смоук можно; мутации прод-данных нельзя.
- Тесты бэка — из `backend/`. Полный сьют ~27 мин → во время задач точечно `pytest .../test_X.py::test_Y -v`.
- **Флейк (не регрессия):** `test_debug_warning` + `test_market_service_async::test_get_client_returns_singleton` падают только в полном прогоне (importlib.reload), зелёные в изоляции.
- **Vitest** на этом хосте — только `--maxWorkers=1`.
- **atom.db не трогать**; миграционные тесты — на `_audit_tmp.db` (удалить после).

### Git-дисциплина
- Та же ветка `feat/rebrand-empirik`. Новый коммит на задачу (не amend). НЕ пушить/мержить без команды пользователя.
- Сообщение: `fix(<область>): <что> (SN-XX)`.
- Перед `git add` — не тащить `.env.local`/секреты/`_audit_tmp.db`.

### Сквозные инварианты (НЕ ломать)
- **ADR-0007** (8 P&L-инвариантов) + **ADR-0008/0010** (`clearing_adjustment = cash − journal`, inferred anchor). Читать перед P&L/anchor-задачами Спринта 2.
- **SYNC-08**: курсор коммитится только после успеха всех стадий.
- **MATH-01**: тег/агрегатные P&L — по `net_pnl`, не gross.
- После P&L-задач — reconcile-проверка (docs/PNL_PLAYBOOK.md).

---

## Порядок спринтов и зависимости

1. **Спринт 1** — первым, подряд. C1/C2 независимы (можно параллелить). Скриншоты: backend-эндпоинт уже есть → задача фронтовая + снять static-mount. Refund — две связанные задачи (idempotency + scope) делать вместе.
2. **Спринт 2** — после С1. `IS_SCHEDULER_WORKER` + пул соединений + async→threadpool трогают деплой-конфиг/`database.py`/`main.py` — координировать. Anchor-задачи — только после чтения ADR-0010.
3. **Спринт 3** — по файлам независим (frontend + analytics), можно параллельно после С1. Индикаторные фиксы требуют обновления их тестов.
4. **Спринт 4** — последним: починка CI + миграции против Postgres (релиз-гейт), регенерация `api.generated.ts` ПОСЛЕ всех backend-контрактных правок С1–С3, обновление e2e под ребренд + сид-юзер.

**Финальный релиз-гейт:** полный `pytest` + `alembic upgrade head` на чистой Postgres 16 + `alembic check` + `vitest`+`tsc` + e2e + ручной сквозной проход register→verify→login→onboarding→broker→sync→edit→close→delete→logout.

---

## РЕЕСТР НАХОДОК (чекбоксы = прогресс)

Детальные планы (реальный код + TDD-шаги):
- **Спринт 1 — Блокеры (CRITICAL + деньги + фиктивная 2FA + сломанный core-UX)** -> [`2026-07-02-sprint-1-blockers.md`](./2026-07-02-sprint-1-blockers.md) (13 задач: CRITx2, HIGHx10, MEDx1)
- **Спринт 2 — Синхронизация-крепость + прод-масштабирование** -> [`2026-07-02-sprint-2-sync-scaling.md`](./2026-07-02-sprint-2-sync-scaling.md) (17 задач: HIGHx9, MEDx5, LOWx3)
- **Спринт 3 — UX-надёжность (кнопки/ошибки) + корректность индикаторов** -> [`2026-07-02-sprint-3-ux-indicators.md`](./2026-07-02-sprint-3-ux-indicators.md) (28 задач: HIGHx9, MEDx14, LOWx5)
- **Спринт 4 — Релизная гигиена (CI/миграции/PII/полировка)** -> [`2026-07-02-sprint-4-release-hygiene.md`](./2026-07-02-sprint-4-release-hygiene.md) (35 задач: HIGHx3, MEDx16, LOWx16)


### Спринт 1 — Блокеры (CRITICAL + деньги + фиктивная 2FA + сломанный core-UX)

| ✔ | ID | Severity | Файл | Проблема |
|---|----|----------|------|----------|
| [ ] | S1-01 | CRIT | `backend/routers/trades.py:1037` | Arbitrary file deletion через DELETE /trades/{id}/screenshot (path traversa |
| [ ] | S1-02 | CRIT | `backend/alembic/versions/0023_position_authoritative_fields.py:24` | Revision id 0023 (34 символа) не влезает в alembic_version VARCHAR(32) — al |
| [ ] | S1-03 | HIGH | `backend/main.py:392` | Скриншоты сделок сломаны: static /uploads удалён, но фронт по-прежнему груз |
| [ ] | S1-04 | HIGH | `backend/routers/payments.py:297` | Refund больше не деактивирует подписку: новый idempotency-замок глотает ref |
| [ ] | S1-05 | HIGH | `backend/routers/broker.py:778` | 401 от broker-эндпоинтов при невалидном T-Bank токене принудительно разлоги |
| [ ] | S1-06 | HIGH | `backend/routers/auth.py:108` | 2FA (TOTP) включается, но никогда не проверяется при входе — защита фиктивн |
| [ ] | S1-07 | HIGH | `frontend/src/app/login/page.tsx:144` | Восстановление пароля — тупик: страницы /auth/reset-password не существует, |
| [ ] | S1-08 | HIGH | `backend/routers/broker.py:507` | POST /broker/connections/{id}/reset безвозвратно уничтожает пользовательски |
| [ ] | S1-09 | HIGH | `frontend/src/components/EditTradeModal.tsx:121` | Редактирование сделки падает 422: confidence='' для sync-сделок и слайдер 1 |
| [ ] | S1-10 | HIGH | `backend/routers/payments.py:374` | Refund-webhook помечает Payment REFUNDED глобально по external_id без скоуп |
| [ ] | S1-11 | HIGH | `backend/routers/payments.py:296` | Webhook refund.succeeded блокируется idempotency-замком — подписка не деакт |
| [ ] | S1-12 | HIGH | `backend/main.py:392` | Удалён static-mount /uploads, но фронт не переведён на новый эндпоинт — все |
| [ ] | S1-13 | MED | `backend/services/pd_export.py:75` | Self-service PD export leaks 2FA secret and verification token |

### Спринт 2 — Синхронизация-крепость + прод-масштабирование

| ✔ | ID | Severity | Файл | Проблема |
|---|----|----------|------|----------|
| [ ] | S2-01 | HIGH | `backend/routers/stats.py:264` | Синхронные DB-запросы и CPU-аналитика в async def блокируют event loop — p9 |
| [ ] | S2-02 | HIGH | `backend/database.py:63` | Пул соединений 8×(5+10)=120 превышает дефолтный max_connections=100 Postgre |
| [ ] | S2-03 | HIGH | `backend/main.py:149` | Singleton-гард IS_SCHEDULER_WORKER нереализуем в прод-топологии: stream con |
| [ ] | S2-04 | HIGH | `backend/application/sync/orchestrator.py:150` | Ручной sync обходит semaphore и per-connection guard оркестратора — 50 одно |
| [ ] | S2-05 | HIGH | `backend/services/opening_anchor_service.py:118` | source='manual' никогда не выставляется — авто-якорь перетирает ручной init |
| [ ] | S2-06 | HIGH | `backend/routers/stats.py:399` | Двойной счёт якоря в ROI-базе /stats/ — total_roi занижен ~вдвое на anchore |
| [ ] | S2-07 | HIGH | `backend/application/sync/pipeline.py:563` | Лимит enrich 50 инструментов/прогон: первый sync активного трейдера молча т |
| [ ] | S2-08 | HIGH | `backend/application/sync/pipeline.py:689` | Generic except в per-uid FIFO глотает ЛЮБУЮ ошибку — курсор коммитится, syn |
| [ ] | S2-09 | HIGH | `backend/market_service.py:306` | Лендинг-тикер живьём отдаёт 1 инструмент из 10 и кеширует это как stale=fal |
| [ ] | S2-10 | MED | `backend/routers/trades.py:587` | GET /trades/positions грузит ВСЕ сделки аккаунта в память на каждый запрос, |
| [ ] | S2-11 | MED | `backend/domain/pnl/opening_anchor.py:76` | G2-телескоп молча отключён для счетов без фьючерсов — якорь может поглотить |
| [ ] | S2-12 | MED | `backend/Dockerfile:91` | Мульти-воркер прод: IS_SCHEDULER_WORKER не задан ни в одном деплой-конфиге, |
| [ ] | S2-13 | MED | `backend/routers/broker.py:506` | Reset во время идущего sync: без account-lock БД остаётся полустёртой с про |
| [ ] | S2-14 | MED | `backend/application/sync/pipeline.py:489` | Stale-cursor детект срабатывает только если stale-батч уместился в одну стр |
| [ ] | S2-15 | LOW | `backend/auth_service.py:586` | get_current_user_optional не проверяет revocation, staleness и is_active |
| [ ] | S2-16 | LOW | `backend/sync_scheduler.py:219` | Orchestrator, TokenRepository и Redis-клиент IpCooldownGate пересоздаются к |
| [ ] | S2-17 | LOW | `backend/application/sync/pipeline.py:1335` | _replace_positions_from_live глотает ошибку вставки: sync репортит success  |

### Спринт 3 — UX-надёжность (кнопки/ошибки) + корректность индикаторов

| ✔ | ID | Severity | Файл | Проблема |
|---|----|----------|------|----------|
| [ ] | S3-01 | HIGH | `backend/routers/stats.py:1580` | 500 на /stats/mae-mfe-analysis: сравнение None >= 1.5 когда в группе нет уб |
| [ ] | S3-02 | HIGH | `backend/analytics/advanced.py:115` | Sterling Ratio: перевёрнутый знак 10%-буфера — завышение в 5-10 раз либо ве |
| [ ] | S3-03 | HIGH | `backend/services/stats_filtering.py:93` | Ulcer Index, dd_episodes (→Sterling) и K-Ratio считаются на кривой кумуляти |
| [ ] | S3-04 | HIGH | `frontend/src/components/ReconnectBanner.tsx:44` | После осознанного отключения брокера юзер навсегда получает ложный красный  |
| [ ] | S3-05 | HIGH | `frontend/src/app/history/page.tsx:194` | Ошибка закрытия сделки проглатывается: модалка закрылась, юзер уверен что п |
| [ ] | S3-06 | HIGH | `frontend/src/app/history/page.tsx:209` | Удаление sync-сделки: backend возвращает 409, фронт молчит — кнопка выгляди |
| [ ] | S3-07 | HIGH | `frontend/src/app/history/page.tsx:214` | «Удалить все» обрывается на первой sync-сделке: часть журнала удалена, оста |
| [ ] | S3-08 | HIGH | `frontend/src/components/PnLHealthBadge.tsx:244` | PnLHealthBadge маскирует бэкенд-статус 'investigate' (worst-of RED) зелёным |
| [ ] | S3-09 | HIGH | `frontend/src/app/DashboardHome.tsx:228` | Вкладки «Продвинутая» и «Сравнение» игнорируют FilterPanel (период/тег/точк |
| [ ] | S3-10 | MED | `frontend/src/app/history/_components/TradeRow.tsx:65` | Naive-UTC даты сериализуются без таймзоны — фронт парсит их как локальное в |
| [ ] | S3-11 | MED | `backend/routers/stats_advanced.py:225` | Benchmark: profit_factor и r_expectancy читаются из словарей, где этих ключ |
| [ ] | S3-12 | MED | `backend/analytics/advanced.py:344` | Часовая heatmap, time_patterns и календарный P&L считаются в UTC без конвер |
| [ ] | S3-13 | MED | `backend/routers/stats_advanced.py:228` | Benchmark сравнивает per-trade Sortino и полный sqrt(N)-SQN юзера с baselin |
| [ ] | S3-14 | MED | `backend/analytics/_common_baseline.py:108` | abs() на нетто-депозитах: ROI/drawdown-база ломается для счетов с чистым вы |
| [ ] | S3-15 | MED | `frontend/src/components/SyncStatusIndicator.tsx:146` | SyncStatusIndicator.triggerSync: ошибка sync молча уходит в console, а spin |
| [ ] | S3-16 | MED | `frontend/src/components/AddTradeModal.tsx:92` | Сбой загрузки скриншота после создания сделки: сделка создана, но модалка с |
| [ ] | S3-17 | MED | `frontend/src/components/AddTradeModal.tsx:199` | Формы сделки принимают отрицательные цену/объём/плечо и будущую дату — back |
| [ ] | S3-18 | MED | `frontend/src/components/CommandPalette.tsx:82` | CommandPalette: дублированный id пункта и 4 пункта-заглушки, ведущие на даш |
| [ ] | S3-19 | MED | `frontend/src/components/SetupManagerModal.tsx:77` | SetupManagerModal: все мутации молча глотают ошибки и нет защиты от double- |
| [ ] | S3-20 | MED | `frontend/src/lib/apiClient.ts:203` | 422-ошибка валидации показывается юзеру как «[object Object]» |
| [ ] | S3-21 | MED | `frontend/src/components/PositionJournalView.tsx:855` | Ошибка второстепенного действия затирает основную таблицу (журнал / открыты |
| [ ] | S3-22 | MED | `frontend/src/components/dashboard/EquityCurveCard.tsx:86` | IMOEX-оверлей нормируется на PnL первой сделки: отрицательное значение инве |
| [ ] | S3-23 | MED | `frontend/src/app/review/page.tsx:87` | Сохранение Daily Review без обработки ошибок — молчаливая потеря написанног |
| [ ] | S3-24 | LOW | `backend/routers/stats_tags.py:52` | /tags/ считает P&L по тегам GROSS (t.pnl), нарушая MATH-01 — цифры расходят |
| [ ] | S3-25 | LOW | `backend/analytics/aggregator.py:61` | analytics.calculate_stats (aggregator.py) падает NameError на любом непусто |
| [ ] | S3-26 | LOW | `backend/crypto_utils.py:80` | Unused legacy crypto_utils path deriving key from SECRET_KEY |
| [ ] | S3-27 | LOW | `backend/services/reconciliation_service.py:323` | Reconciliation: выводы средств не учитываются в net_cash_flow (тип 'out' вм |
| [ ] | S3-28 | LOW | `frontend/src/app/history/page.tsx:322` | Расчёт MAE/MFE молча глотает ошибку — кнопка крутится и «ничего не произошл |

### Спринт 4 — Релизная гигиена (CI/миграции/PII/полировка)

| ✔ | ID | Severity | Файл | Проблема |
|---|----|----------|------|----------|
| [ ] | S4-01 | HIGH | `backend/services/pd_deletion.py:146` | Trade screenshot files not deleted on account anonymization (152-FZ incompl |
| [ ] | S4-02 | HIGH | `frontend/src/lib/apiClient.ts:176` | Глобальный 15с таймаут apiClient обрубает первый sync и onboarding-reconcil |
| [ ] | S4-03 | HIGH | `.github/workflows/ci.yml:3` | CI мёртв с 2026-05-06 — миграции 0005–0029 никогда не проверялись против Po |
| [ ] | S4-04 | MED | `backend/routers/broker.py:788` | /broker/portfolio не отдаёт unrealized_pnl (top-level) и name позиций, кото |
| [ ] | S4-05 | MED | `backend/routers/stats.py:580` | Calmar на /stats/ аннуализирует доходность любой, даже недельной, истории ( |
| [ ] | S4-06 | MED | `backend/analytics/advanced.py:639` | tax_visibility использует устаревшую шкалу НДФЛ (13% до 5 млн) — с 2025 пор |
| [ ] | S4-07 | MED | `backend/routers/trades.py:1332` | POST /trades/calculate-mae-mfe force_all: неограниченный фан-аут в MOEX ISS |
| [ ] | S4-08 | MED | `nginx/conf.d/empirik.conf:110` | Новый /api/landing/ticker в проде получает 404 через nginx: location /api/  |
| [ ] | S4-09 | MED | `backend/services/invariants_service.py:341` | invariants_service обращается к несуществующим колонкам BalanceSnapshot — у |
| [ ] | S4-10 | MED | `backend/services/totp_service.py:50` | TOTP-код можно переиспользовать (replay) в пределах окна — нет счётчика las |
| [ ] | S4-11 | MED | `backend/routers/auth.py:57` | User enumeration на /auth/register: разный ответ для существующего и нового |
| [ ] | S4-12 | MED | `frontend/src/components/TrialEndedDialog.tsx:35` | Весь триал-UI (TrialEndedDialog, TrialCountdownBanner, SubscriptionProvider |
| [ ] | S4-13 | MED | `frontend/src/components/ReconciliationBanner.tsx:39` | Onboarding-визард /onboarding/reconcile недостижим из UI: единственная ссыл |
| [ ] | S4-14 | MED | `frontend/src/app/auth/verify-email/page.tsx:89` | Флоу верификации email оборван: /auth/me не отдаёт email_verified, resend-э |
| [ ] | S4-15 | MED | `frontend/src/app/profile/page.tsx:88` | Logout со страницы профиля — гонка: window.location.href сразу после fire-a |
| [ ] | S4-16 | MED | `backend/routers/admin.py:746` | impersonate-токен: нет запрета имперсонации админов, нет отзыва токена, нет |
| [ ] | S4-17 | MED | `frontend/src/app/layout.tsx:105` | Один глобальный ErrorBoundary на всё приложение — упавший виджет роняет вес |
| [ ] | S4-18 | MED | `backend/models.py:960` | Дрейф моделей: индексы ix_operations_state_type_executed и ix_access_log_st |
| [ ] | S4-19 | MED | `backend/models.py:338` | Обратный дрейф: ix_trades_account_entry_exit добавлен в models.py (коммит 8 |
| [ ] | S4-20 | LOW | `frontend/src/types/api.generated.ts:1` | api.generated.ts не перегенерирован после незакоммиченных правок роутеров — |
| [ ] | S4-21 | LOW | `frontend/src/components/OAuthButtons.tsx:107` | Raw fetch без таймаута в обход apiClient/fetchWithTimeout (4 места) |
| [ ] | S4-22 | LOW | `backend/moex_service.py:102` | _index_cache в MoexService — неограниченный рост словаря (ключ = произвольн |
| [ ] | S4-23 | LOW | `backend/routers/stats_advanced.py:166` | GET /stats/benchmark без кэша и без явного rate-limit — полная загрузка сде |
| [ ] | S4-24 | LOW | `backend/services/pd_deletion.py:169` | Anonymization does not clear totp_secret and email_verification_token |
| [ ] | S4-25 | LOW | `backend/routers/auth.py:600` | Timing-enumeration на /password-reset/request из-за синхронной отправки SMT |
| [ ] | S4-26 | LOW | `frontend/src/lib/userScopedStorage.ts:18` | Тема сбрасывается на тёмную при каждом логине/логауте: theme лежит в user-s |
| [ ] | S4-27 | LOW | `frontend/src/app/global-error.tsx:27` | global-error.tsx рендерит собственный <html>/<body> без CSS: экран критичес |
| [ ] | S4-28 | LOW | `frontend/src/app/help/page.tsx:167` | Контакты поддержки разъезжаются между доменами и старым брендом: support@em |
| [ ] | S4-29 | LOW | `backend/routers/admin.py:1544` | admin feature-flags PATCH принимает произвольные имена флагов без whitelist |
| [ ] | S4-30 | LOW | `frontend/src/components/PeriodSelector.tsx:16` | Мёртвый дубликат PeriodSelector.tsx с hardcoded русскими строками |
| [ ] | S4-31 | LOW | `frontend/src/components/ReconciliationBanner.tsx:81` | Три разных саппорт-адреса после ребренда: empirik.app, empirik.io, бренд «П |
| [ ] | S4-32 | LOW | `frontend/src/components/dashboard/RecentTrades.tsx:116` | Часть виджетов хардкодит «₽» и ru-RU-формат в обход настройки валюты |
| [ ] | S4-33 | LOW | `frontend/src/components/dashboard/ActivityCalendar.tsx:154` | Остатки dark-hardcode в светлой теме: text-green-300/red-300 и белые rgba в |
| [ ] | S4-34 | LOW | `backend/routers/trades.py:214` | Любой IntegrityError при создании сделки маскируется под 409 «дубликат» |
| [ ] | S4-35 | LOW | `backend/models.py:936` | password_reset_tokens / feature_flags / revoked_tokens.user_id без FK — сир |

---

## Протокол возобновления после /compact
1. Прочитать этот файл.
2. `git -C c:/Users/Administrator/Eqio/ATOM log --oneline -20` — какие `SN-XX` уже закоммичены.
3. Синхронизировать чекбоксы (закоммичено = `[x]`).
4. Открыть план текущего спринта, найти первую незакрытую задачу, продолжить TDD-цикл.
5. Память: `project_state_2026_07_02_release_audit_plan.md`.

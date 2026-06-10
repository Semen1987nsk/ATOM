# Sprint 6.5 — Correctness & Trust — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть критические находки production-аудита 2026-06-10 (общая оценка 4.9/10) до старта Sprint 7 (платежи): корректность MAE/MFE, рабочий manual-flow, деплоибельность alembic, сохранность пользовательских данных при re-sync, прозрачность sync-ошибок.

**Architecture:** Точечные фиксы по подтверждённым находкам аудита (workflow wzcg10qso, 32 агента + adversarial verify + live-проход). Полный JSON-реестр: Temp/tasks/wzcg10qso.output; выжимка в memory `project_state_2026_06_10_production_audit.md`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + alembic (backend), Next.js 16 + React 19 + TanStack Query (frontend), pytest + vitest.

**Глобальные правила:** `PYTHONUTF8=1 python -X utf8` для всех python-команд. TDD: сначала падающий тест. После P&L-правок — `tools/reconcile_journal_vs_cash.py`.

---

## Batch 1 — MAE/MFE timezone (MAE-01 critical, MAE-02, MAE-12)

**Корень:** в БД времена UTC-naive (trade_repo.py:137), но `MarketDataService._to_msk` (market_service.py:158-168) трактует naive как МСК → окно фильтра свечей сдвинуто на −3ч для всех путей, читающих сделку из БД (bulk endpoint, import-hook, nightly backfill). Соседний `calculate_post_exit_analysis` трактует naive противоположно (как UTC) — конвенции противоречат. Тесты `test_mae_mfe.py` подают naive=МСК и маскируют баг.

**Files:**
- Modify: `backend/market_service.py:158-168` (_to_msk → UTC-конвенция), `:501-508` (calculate_mae_mfe)
- Modify: `backend/routers/replay.py:90-92` (range в МСК для ISS + маркеры в одной шкале со свечами)
- Test: `backend/tests/unit/test_mae_mfe_timezone.py` (новый), правка `backend/tests/test_mae_mfe.py` (фикстуры naive-UTC)

**Steps:**
- [ ] Падающий тест: naive-UTC сделка 10:30-11:45 UTC (=13:30-14:45 МСК) + свечи МСК 13:30-14:45 → calculate_mae_mfe обязан их найти (сейчас вернёт None,None)
- [ ] Падающий тест: replay-эндпоинт отдаёт маркеры в той же шкале, что begin свечей
- [ ] Fix `_to_msk`: naive = UTC → `pytz.utc.localize(dt).astimezone(MSK_TZ)`; выровнять с post-exit конвенцией
- [ ] Fix replay.py: entry_at/exit_at → МСК перед запросом ISS; маркеры отдавать в МСК (или оба ISO+03:00)
- [ ] Прогнать все mae/replay/post-exit тесты; поправить фикстуры, подававшие naive=МСК
- [ ] Скрипт/команда force-пересчёта MAE/MFE всех сделок (использовать существующий POST calculate-mae-mfe?force_all + задокументировать в RUNBOOK миграционный шаг)
- [ ] Commit `fix(mae): treat naive datetimes as UTC in MAE/MFE window (MAE-01/02)`

## Batch 2 — Manual trade flow + error feedback (LIVE-01 critical, UX-01/09, A11Y-02)

**Корень:** `TradeCreate.account_id` обязателен (schemas.py:311), но `create_trade` его игнорирует — резолвит сервер-сайд (trades.py:82). Фронт поле не шлёт → 422 на каждый сабмит. Catch в Add/EditTradeModal — только console.error; toast-системы нет.

**Files:**
- Modify: `backend/schemas.py:310-311` — `account_id: Optional[int] = None` + комментарий что сервер резолвит активный счёт
- Create: `frontend/src/components/ui/Toast.tsx` + `frontend/src/contexts/ToastContext.tsx` (лёгкий, без зависимостей: useToast() → push({kind:'error'|'success', message}), aria-live="polite", автодисмисс 6с, стек справа-снизу)
- Modify: `frontend/src/app/layout.tsx` — ToastProvider
- Modify: `frontend/src/components/AddTradeModal.tsx:63-100`, `EditTradeModal.tsx:~132`, `CloseTradeModal.tsx` — catch → toast(ApiError.toUserMessage()), submit-кнопка disabled+spinner на время запроса (двойной клик)
- Test: `backend/tests/test_api.py` — POST /trades/ без account_id = 200; `frontend/src/components/ui/__tests__/Toast.test.tsx`

**Steps:**
- [ ] Падающий backend-тест: POST /trades/ без account_id → 200 (сейчас 422)
- [ ] Schema fix + прогон
- [ ] Toast-система + тесты (рендер, автодисмисс, aria-live)
- [ ] Wire в 3 модалки + disabled на submit
- [ ] Живая проверка: добавить сделку через UI рукой (playwright) — успех и видимый toast при ошибке
- [ ] Commit `fix(trades): manual add works again — optional account_id + toast error feedback`

## Batch 3 — deposits mojibake + PNL fixes (API-01, PNL-01, PNL-02)

**Files:**
- Modify: `backend/routers/deposits.py` — все строки-mojibake перекодировать (текущий текст.encode('utf-8')? нет: текст уже UTF-8-байты CP1251-прочтения; восстановление: s.encode('cp1251', errors)... проверить экспериментально: правильный раунд-трип `bad.encode('utf-8').decode('utf-8')`—нет; рабочий путь: `bad_str.encode('cp1251_от_обратного')` — фактически `bad.encode('utf-8').decode('cp1251')`?? НЕТ — корректно: mojibake возник как utf8-байты→cp1251-decode, значит восстановление = `bad.encode('cp1251').decode('utf-8')`. Проверить на «РђРєРєР°СѓРЅС‚»→«Аккаунт» до массовой правки!)
- Modify: `backend/routers/stats_advanced.py:205` — calmar: использовать `calculate_mar_ratio(cagr_pct, max_dd_pct)` или передавать список pnls (как stats.py:577)
- Modify: `backend/routers/stats_advanced.py:80,190` — initial_balance для drawdown_stats = `get_net_deposits_baseline_from_db` (уже импортирован) вместо equity[0]
- Test: `backend/tests/unit/test_deposits_encoding.py` (guard: нет mojibake-маркеров в .py), `backend/tests/integration/test_benchmark_endpoint.py` (история >90 дней → 200, не 500; MaxDD% совпадает с главной вкладкой)

**Steps:**
- [ ] Тест-guard mojibake + падающие тесты benchmark
- [ ] Перекодировка deposits.py (с ручной проверкой раунд-трипа на одной строке)
- [ ] Calmar + baseline фиксы
- [ ] `tools/reconcile_journal_vs_cash.py` прогон (P&L-правка!)
- [ ] Commit `fix(pnl,api): benchmark 500, MaxDD baseline, deposits mojibake`

## Batch 4 — Alembic deployable from scratch (DATA-01 critical)

**Files:**
- Modify: `backend/alembic/versions/0001_initial_baseline.py` — заменить create_all на замороженный статический снапшот схемы НА МОМЕНТ 0001 (autogenerate на чистой БД от models.py состояния 0001; практический путь: новая ревизия не нужна — переписать 0001 чтобы он создавал схему так, как ожидает 0002+, включая СТАРЫЙ uq_trades_dedup)
- Modify: `backend/alembic/versions/0006_pr7_trade_unique_with_exit.py` — inspect-guard: пропускать drop/create если uq_trades_dedup_v2 уже есть
- Modify: `.github/workflows/ci.yml` — джоб «alembic upgrade head на чистом postgres:16 + SQLite» (если нет)
- Test: `backend/tests/integration/test_alembic_from_scratch.py` — upgrade head на пустой SQLite in-memory проходит и даёт схему == create_all-схеме (сравнить имена таблиц/констрейнтов)

**Steps:**
- [ ] Падающий тест upgrade-from-scratch
- [ ] Заморозить 0001 (минимальный путь: 0001 создаёт через create_all, НО затем 0002-0028 должны быть идемпотентны → вместо переписывания 0001 сделать inspect-guard'ы в 0006/0007+; выбрать меньшее зло после теста)
- [ ] CI-джоб
- [ ] Commit `fix(alembic): clean-database upgrade head works (DATA-01)`

## Batch 5 — Re-sync сохраняет аннотации (DATA-02 critical)

**Files:**
- Modify: `backend/adapters/persistence/trade_repo.py:68-82` — replace_for_instrument: до DELETE снять map {natural_key → (notes, tags, mood, discipline, confidence, setup_id, screenshot_url)} c существующих строк, после INSERT перенести по match (entry_at, exit_at, direction, quantity)
- Test: `backend/tests/unit/test_trade_repo_annotations.py` — заметка переживает replace; częściowy match (изменился exit) → аннотация прикрепляется к ближайшей по entry_at
- Modify: `backend/routers/trades.py:1076-1090` — delete_trade: для data_source='tinkoff_v2' → 409 с объяснением (DATA-11)

**Steps:**
- [ ] Падающие тесты переноса
- [ ] Реализация map-переноса
- [ ] 409 на delete синк-сделок + тест
- [ ] Commit `fix(sync): preserve user annotations across FIFO rebuild (DATA-02)`

## Batch 6 — Sync-прозрачность (SYNC-01)

**Files:**
- Modify: `backend/routers/broker.py:392` — list_connections: возвращать и неактивные с полем `deactivation_reason` (или query-параметр include_inactive=true для фронта)
- Modify: `backend/application/sync/orchestrator.py:243-244` — _deactivate сохраняет reason ('token_invalid') в BrokerConnection.last_sync_error
- Frontend: `ReconnectBanner.tsx` — показывать по реальным данным
- Test: integration «деактивированное подключение видно с причиной»

**Steps:**
- [ ] Падающий тест list_connections с деактивированным
- [ ] Backend + frontend wiring
- [ ] Commit `fix(sync): revoked token surfaces ReconnectBanner with reason (SYNC-01)`

## Batch 7 — MAE/MFE page UX (жалоба основателя; MAE-05/08, UX)

**Files:**
- Modify: `frontend/src/components/dashboard/MAEMFEAnalysisPanel.tsx` — клик строки → разворачивание списка сделок группы (тикер, дата, PnL, MAE/MFE, ссылка → /trades/{id}/replay); тултипы на Edge («во сколько раз благоприятный ход больше неблагоприятного: MFE/MAE») и Score; заменить «экскурс» на «ход цены против/в пользу позиции»
- Modify: `backend/application/sync/pipeline.py` — после fifo-rebuild дёргать schedule_mae_mfe_backfill для затронутых закрытых сделок (MAE-05)
- Decide: MAEMFECard (мёртвый компонент с богатой аналитикой) — смонтировать overall-блок на /analysis/mae-mfe (фиксануть fetch: credentials+CSRF) ИЛИ удалить (решение по ходу)
- Test: vitest на разворачивание строки; backend-тест на backfill-hook

**Steps:**
- [ ] Backfill-hook из sync + тест
- [ ] Row-expand + ссылки на replay + тултипы
- [ ] Решение по MAEMFECard
- [ ] Живая проверка playwright
- [ ] Commit `feat(mae-ux): per-trade drill-down, replay links, plain-language tooltips`

## Хвост (по остатку времени, отдельные мелкие коммиты)
- UX-02/бренд: «Eqio»→«Эмпирик» в auth/sidebar (live-находка: лого Eq io)
- API-02: баннер «показаны последние N из M» в истории при len==limit
- DATA-03: cascade на broker_connections при удалении Account + тест
- DES-04: смок светлой темы на positions/модалках

## Verification gate (перед «готово»)
1. `pytest tests/unit tests/integration -q` зелёный
2. `npm test` зелёный
3. `tools/reconcile_journal_vs_cash.py` после P&L-батчей
4. Живой проход playwright: register → add trade (UI!) → dashboard → mae-mfe drill-down → replay
5. Коммиты по батчам, push после подтверждения

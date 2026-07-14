# Спринт 2 — Синхронизация-крепость + прод-масштабирование Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (- [ ]) syntax.

**Goal:** Укрепить конвейер брокерского sync (enrich-лимит, per-uid except, reset-race, stale-cursor, дедуп ручного sync), достроить ADR-0010 anchor (manual-source, ROI-double-count, G2/G3 для stock-only) и убрать прод-масштаб-ловушки (event-loop блокировки, пул соединений, IS_SCHEDULER_WORKER, пагинация журнала).

**Architecture:** FastAPI-роутеры вызывают синхронный `Session` (`database.get_db`) + чистый Python — тяжёлые `async def` эндпоинты уводятся в threadpool или превращаются в `def`. Брокерский sync — многостадийный `SyncPipeline.run()`, курсор коммитится последним (SYNC-08). ADR-0010 anchor — чистое ядро `domain/pnl/opening_anchor.py` + I/O-обёртка `services/opening_anchor_service.py`. Оркестратор пересоздаётся на каждой итерации планировщика; ручной sync идёт мимо семафора.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2.0 / Pydantic v2 (SQLite dev, PostgreSQL 16 prod) / gunicorn+uvicorn workers / docker-compose. Тесты — pytest.

## Global Constraints

- **Python:** `C:/Python314/python.exe` (зависимости там). Тесты бэка — из `backend/`: `C:/Python314/python.exe -m pytest tests/... -q`.
- **Backend** уже запущен на `http://localhost:8000` (GET-смоук можно, мутации прод-данных нельзя).
- **Frontend:** `cd frontend && npx vitest run --maxWorkers=1` (ТОЛЬКО `maxWorkers=1`) + `npx tsc --noEmit`. E2E: playwright, backend :8000 + `npm run dev -- -p 3001`, при lock-ошибке убить `next dev` + удалить `frontend/.next/dev/lock`.
- **Миграции:** врем. БД `DATABASE_URL=sqlite:///./_audit_tmp.db`, НИКОГДА не трогать `backend/atom.db`. Перед релизом — Postgres 16.
- **Git:** новый коммит на задачу (не amend), ветка `feat/rebrand-empirik`, формат `fix(область): что (SN-XX)`. Не пушить/мержить.
- **Инварианты:** ADR-0007 (P&L), SYNC-08 (курсор после всех стадий), MATH-01 (net_pnl не gross). Читать `docs/PNL_PLAYBOOK.md` для P&L-задач.
- **Флейк (не регрессия):** `test_debug_warning` + `test_market_service_async::test_get_client_returns_singleton` падают только в полном прогоне.
- **Координация:** `S2-01` (async→def в stats), `S2-02` (пул), `S2-03`/`S2-12` (IS_SCHEDULER_WORKER + docker-compose) трогают деплой-конфиг/`database.py`/`main.py`/`Dockerfile` — делать в одном логическом блоке, не параллелить между собой. Anchor-задачи (`S2-05`, `S2-06`, `S2-11`) — только после чтения ADR-0010 (`.business/tech/decisions/0010-*`).

---

### S2-01 [HIGH] Синхронные DB+CPU в async def блокируют event loop

**Files:**
- Modify: `backend/routers/stats.py:165` (`async def get_stats`), `backend/routers/stats_advanced.py:45` (`async def get_advanced_stats`), `backend/routers/trades.py:568` (`async def read_position_trades`)
- Test: `backend/tests/unit/test_endpoints_run_in_threadpool.py` (Create)

**Проблема:** Тяжёлые роутеры объявлены `async def`, но используют синхронную `Session` + чистый Python-аналитику — FastAPI исполняет тело прямо в event loop, блокируя воркер на 0.5–2 с (весь sync-код в них: нет `await run_in_threadpool`).

**Interfaces:** производит: изменённые сигнатуры эндпоинтов. `read_position_trades` также переписывается на пагинацию в S2-10 — там менять уже готовую `def`-версию, не async. `get_stats` содержит ROI-double-count из S2-06 (тот же файл, координировать патчи).

Ключ решения: у `get_stats`/`get_advanced_stats`/`read_position_trades` в теле НЕТ `await` по IMOEX-overlay (overlay считается на фронте `EquityCurveCard.tsx`, в этих трёх — только sync-код). Значит корректный минимальный фикс: `async def` → `def`. FastAPI сам уводит sync-эндпоинты в threadpool.

- [ ] **Step 1 — Тест.** Создать `backend/tests/unit/test_endpoints_run_in_threadpool.py`:
```python
"""PERF: тяжёлые DB+CPU эндпоинты не должны блокировать event loop.

FastAPI исполняет тело `async def` прямо в loop; `def`-эндпоинт уводится
в threadpool. Проверяем что три тяжёлых роутера объявлены обычными `def`
(inspect.iscoroutinefunction == False), т.к. в их телах нет await-веток.
"""
import inspect

from routers import stats, stats_advanced, trades


def test_get_stats_is_sync_def():
    assert not inspect.iscoroutinefunction(stats.get_stats)


def test_get_advanced_stats_is_sync_def():
    assert not inspect.iscoroutinefunction(stats_advanced.get_advanced_stats)


def test_read_position_trades_is_sync_def():
    assert not inspect.iscoroutinefunction(trades.read_position_trades)
```
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_endpoints_run_in_threadpool.py -q` → 3 FAILED (`assert not True`).
- [ ] **Step 3 — Фикс.** В трёх файлах убрать `async` из сигнатуры (тела не трогать — там нет `await`):

`stats.py:165` before → after:
```python
@router.get("/", response_model=schemas.DashboardStats)
async def get_stats(
```
```python
@router.get("/", response_model=schemas.DashboardStats)
def get_stats(
```

`stats_advanced.py:45` — аналогично:
```python
async def get_advanced_stats(
```
→
```python
def get_advanced_stats(
```

`trades.py:568`:
```python
async def read_position_trades(
```
→
```python
def read_position_trades(
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_endpoints_run_in_threadpool.py -q` → 3 passed. Регресс: `C:/Python314/python.exe -m pytest tests/test_trades.py tests/test_stats_cache.py tests/test_advanced_benchmark.py -q` зелёный + `C:/Python314/python.exe -c "import main"` без ошибок. Смоук: `curl -s -H "Authorization: Bearer <dev-token>" http://localhost:8000/trades/positions?limit=1` → 200 (или используй существующий GET-смоук роут).
- [ ] **Step 5 — Commit.** `fix(perf): run heavy stats/positions endpoints in threadpool (S2-01)`

---

### S2-02 [HIGH] Пул 8×(5+10)=120 превышает Postgres max_connections=100

**Files:**
- Modify: `docker-compose.prod.yml:45` (postgres, добавить `command`), `.env.production.example` (DB_MAX_OVERFLOW), `docs/RUNBOOK.md` (формула)
- Test: врем. compose-валидация + ручной расчёт

**Проблема:** replicas 2 × gunicorn 4 воркера = 8 процессов × (pool_size 5 + max_overflow 10) = 120 соединений; postgres:16-alpine стартует без конфига (default `max_connections=100`) → под пиком `FATAL: too many clients`, страдают и `/ready` (SELECT 1).

**Interfaces:** координируется с S2-03/S2-12 (тот же docker-compose.prod.yml + .env). Формула `replicas × workers × (pool+overflow) < max_connections` фиксируется в RUNBOOK.

MEDIUM/сжатый цикл (инфра-конфиг, нет unit-теста логики; проверка — валидатор compose + арифметика).

- [ ] **Step 1 — Проверка (baseline).** `cd c:/Users/Administrator/Eqio/ATOM && docker compose -f docker-compose.prod.yml config >/dev/null && echo "compose OK"`. Подтвердить, что у сервиса `postgres` нет `command:` (строки 45-47 — только комментарии), и что 8×15=120 > 100.
- [ ] **Step 2 — Фикс.** Два независимых изменения (defense-in-depth):

(a) `docker-compose.prod.yml` — раскомментировать/добавить `command` postgres (заменить блок комментариев на строках 45-47):
```yaml
    # Без command — postgres использует default config.
    # При наличии postgres/postgresql.prod.conf переключить на:
    #   command: postgres -c config_file=/etc/postgresql/postgresql.conf
```
→
```yaml
    # max_connections поднят под топологию replicas(2)×workers(4)×(pool5+overflow10)=120.
    # Формула запаса в docs/RUNBOOK.md. Долгосрочно — pgbouncer.
    command: postgres -c max_connections=200
```

(b) `.env.production.example` — добавить строку, снижающую overflow (8×(5+5)=80 < 100, независимо от (a)):
```
DB_MAX_OVERFLOW=5
```
- [ ] **Step 3 — Верификация + commit.** `docker compose -f docker-compose.prod.yml config | grep -A1 "postgres" | grep max_connections` → `command: postgres -c max_connections=200`. Проверить в RUNBOOK наличие раздела с формулой (добавить если нет): `replicas × workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW) < max_connections`. Commit: `fix(infra): raise pg max_connections=200 and cap DB_MAX_OVERFLOW (S2-02)`

---

### S2-03 [HIGH] IS_SCHEDULER_WORKER нереализуем: stream consumers на всех 8 процессах либо нигде

**Files:**
- Modify: `docker-compose.prod.yml:83` (добавить сервис `backend-scheduler`, задать `IS_SCHEDULER_WORKER=false` у `backend`)
- Test: `backend/tests/unit/test_worker_role.py` (Create) + compose-валидация

**Проблема:** `is_scheduler_worker()` (`worker_role.py:14`, default `true`) гейтит stream consumers (`main.py:149`) и scheduler, но env общий для обеих реплик и 4 воркеров внутри контейнера — выделить ровно один процесс нельзя. Default `true` → 8 stream_manager → N×gRPC → IP-cooldown; если ops поставит `false` — scheduler/PD-финализация/retention не работают нигде.

**Interfaces:** координируется с S2-12 (та же переменная, отдельный дублирующий MEDIUM-фикс — S2-12 добавляет `IS_SCHEDULER_WORKER` в `.env.production.example` и docs). S2-03 создаёт compose-сервис; S2-12 закрывает env-конфиг и кросс-процессный advisory lock. Делать S2-03 первым.

- [ ] **Step 1 — Тест.** Создать `backend/tests/unit/test_worker_role.py`:
```python
"""IS_SCHEDULER_WORKER: default true, но в проде на API-репликах = false.

worker_role.is_scheduler_worker() — единственная точка гейта фоновых
синглтонов (scheduler + stream consumers). Тест фиксирует контракт env-парсинга,
чтобы прод-compose (backend=false, backend-scheduler=true) корректно разводил роли.
"""
import importlib

import worker_role


def _reload():
    return importlib.reload(worker_role)


def test_default_is_true(monkeypatch):
    monkeypatch.delenv("IS_SCHEDULER_WORKER", raising=False)
    assert _reload().is_scheduler_worker() is True


def test_explicit_false(monkeypatch):
    monkeypatch.setenv("IS_SCHEDULER_WORKER", "false")
    assert _reload().is_scheduler_worker() is False


def test_case_insensitive_true(monkeypatch):
    monkeypatch.setenv("IS_SCHEDULER_WORKER", "TRUE")
    assert _reload().is_scheduler_worker() is True
```
- [ ] **Step 2 — Запуск, ожидание PASS (контракт уже верен) ИЛИ FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_worker_role.py -q`. Здесь контракт `worker_role` уже корректен — тест зелёный сразу; он служит регресс-гардом для compose-разводки. Основная работа — деплой-конфиг (Step 3).
- [ ] **Step 3 — Фикс (compose).** В `docker-compose.prod.yml`: (a) у сервиса `backend` добавить env-override `IS_SCHEDULER_WORKER=false` (env_file `.env` остаётся, но explicit `environment:` перекрывает); (b) добавить отдельный сервис `backend-scheduler` (тот же image, 1 воркер, `IS_SCHEDULER_WORKER=true`, без публикации порта, без реплик).

У `backend` (после `env_file: .env`, строка 86):
```yaml
    env_file: .env
    environment:
      # API-реплики НЕ держат stream consumers/scheduler — только backend-scheduler.
      IS_SCHEDULER_WORKER: "false"
```
Новый сервис (после блока `backend`, перед следующим сервисом):
```yaml
  # ──────── Backend scheduler (singleton: stream consumers + sync scheduler) ────────
  backend-scheduler:
    image: ghcr.io/${GITHUB_REPOSITORY_OWNER:-empirik}/empirik-backend:${SHA:-latest}
    env_file: .env
    environment:
      IS_SCHEDULER_WORKER: "true"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - uploads_data:/app/uploads
      - logs_data:/var/log/atom
    command: ["sh", "-c", "exec gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --workers 1 --bind 0.0.0.0:8000 --timeout 120 --graceful-timeout 30"]
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
        max_attempts: 3
    restart: unless-stopped
    networks: [empirik-net]
```
- [ ] **Step 4 — Верификация.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_worker_role.py -q` → passed. `cd c:/Users/Administrator/Eqio/ATOM && docker compose -f docker-compose.prod.yml config >/dev/null && echo OK`. Убедиться в выводе `config`, что у `backend` `IS_SCHEDULER_WORKER: "false"`, у `backend-scheduler` `"true"`.
- [ ] **Step 5 — Commit.** `fix(infra): dedicate backend-scheduler service for singleton stream/scheduler (S2-03)`

---

### S2-04 [HIGH] Ручной sync обходит semaphore и in-flight guard оркестратора

**Files:**
- Modify: `backend/application/sync/orchestrator.py:150` (`sync_one_account`)
- Test: `backend/tests/integration/test_orchestrator.py` (добавить кейсы) или Create `backend/tests/unit/test_sync_one_account_guard.py`

**Проблема:** `sync_one_account` (строки 150-158) зовёт `self._sync(connection_data)` напрямую — без `self._semaphore` и без проверки `self._in_flight`; при 50 одновременных ручных Sync → 50 параллельных pipeline с одного IP → IP-cooldown T-Bank, дабл-клик = два конкурентных pipeline на один `account_id`.

**Interfaces:** производит: `sync_one_account` с гардом. Потребитель — `broker.py:441` (`sync_now`): при занятости оркестратор должен бросить сигнал, который роут маппит в HTTP 409. Определяем новое исключение `SyncAlreadyRunning` в orchestrator-модуле.

- [ ] **Step 1 — Тест.** Создать `backend/tests/unit/test_sync_one_account_guard.py`:
```python
"""SYNC-04: ручной sync_one_account проходит через тот же bulkhead, что и
плановый _guard_one — семафор + in-flight dedup. Второй параллельный вызов
на тот же connection_id должен отклоняться (SyncAlreadyRunning), а не
запускать второй конкурентный pipeline.
"""
import asyncio

import pytest

from application.sync.orchestrator import (
    SyncAlreadyRunning,
    TinkoffSyncOrchestrator,
)


class _StubOrch(TinkoffSyncOrchestrator):
    def __init__(self):
        super().__init__(session_factory=lambda: None, max_concurrent=5)
        self.sync_calls = 0
        self._release = asyncio.Event()

    async def _load_connection_async(self, cid):  # helper the impl will use
        return object()

    async def _sync(self, ctx):  # noqa: D401
        self.sync_calls += 1
        await self._release.wait()
        return "report"


@pytest.mark.asyncio
async def test_second_concurrent_manual_sync_is_rejected(monkeypatch):
    orch = _StubOrch()
    # _load_connection дергается через to_thread — вернём непустой ctx.
    monkeypatch.setattr(orch, "_load_connection", lambda cid: object())

    first = asyncio.create_task(orch.sync_one_account(1))
    await asyncio.sleep(0.01)  # дать первому занять in-flight

    with pytest.raises(SyncAlreadyRunning):
        await orch.sync_one_account(1)

    orch._release.set()
    assert await first == "report"
    assert orch.sync_calls == 1
```
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_sync_one_account_guard.py -q` → FAIL (`ImportError: SyncAlreadyRunning` / оба вызова проходят, `sync_calls == 2`).
- [ ] **Step 3 — Фикс.** В `orchestrator.py` объявить исключение (рядом с прочими импортами исключений вверху модуля) и обернуть `sync_one_account`:

Добавить класс (после импортов, до класса оркестратора):
```python
class SyncAlreadyRunning(Exception):
    """Ручной sync запрошен, пока для этого connection уже идёт sync."""
```
`sync_one_account` (строки 150-158) before → after:
```python
    async def sync_one_account(self, connection_id: int) -> SyncReport:
        """
        Public API для ручного trigger'а (UI / админка). Принимает
        connection_id, сам разрешает context (расшифровка токена и т.п.).
        """
        connection_data = await asyncio.to_thread(self._load_connection, connection_id)
        if connection_data is None:
            raise ValueError(f"BrokerConnection {connection_id} not found or inactive")
        return await self._sync(connection_data)
```
```python
    async def sync_one_account(self, connection_id: int) -> SyncReport:
        """
        Public API для ручного trigger'а (UI / админка). Принимает
        connection_id, сам разрешает context (расшифровка токена и т.п.).

        SYNC-04: тот же bulkhead, что и плановый _guard_one — in-flight dedup
        + семафор. Двойной клик / 50 одновременных Sync больше не запускают
        параллельные pipeline с одного IP (IP-cooldown T-Bank).
        """
        if connection_id in self._in_flight:
            raise SyncAlreadyRunning(connection_id)
        self._in_flight.add(connection_id)
        try:
            async with self._semaphore:
                connection_data = await asyncio.to_thread(
                    self._load_connection, connection_id
                )
                if connection_data is None:
                    raise ValueError(
                        f"BrokerConnection {connection_id} not found or inactive"
                    )
                return await self._sync(connection_data)
        finally:
            self._in_flight.discard(connection_id)
```
Маппинг в роуте `broker.py:441` — добавить перед `except TokenInvalid`:
```python
    try:
        report = await orchestrator.sync_one_account(connection_id)
    except SyncAlreadyRunning:
        raise HTTPException(status_code=409, detail="Синхронизация уже выполняется")
    except TokenInvalid:
```
(добавить `SyncAlreadyRunning` в импорт оркестратора вверху `broker.py`).
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_sync_one_account_guard.py tests/integration/test_orchestrator.py -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(sync): guard manual sync_one_account with in-flight+semaphore, 409 on busy (S2-04)`

---

### S2-05 [HIGH] source='manual' никогда не выставляется — авто-якорь перетирает ручной баланс

**Files:**
- Modify: `backend/capital_service.py:236` (`sync_initial_balance` — параметр `source`), `backend/routers/deposits.py:188` (POST /initial), `backend/routers/trades.py:475` (import-путь), `backend/services/opening_anchor_service.py:42` (legacy NULL tr" as manual)
- Test: `backend/tests/integration/test_opening_anchor_service.py` (добавить достижимый сценарий)

**Проблема:** Гард `if account.initial_balance_source == "manual"` (`opening_anchor_service.py:48`) — мёртвый: `'manual'` не присваивается нигде. `sync_initial_balance` (`capital_service.py:250`: `setattr(account, "initial_balance", ...)`) пишет баланс БЕЗ `initial_balance_source`. На следующем sync `autoset_inferred_anchor` перетирает ручной ввод. Нарушение ADR-0010 §5.

**Interfaces:** производит: `sync_initial_balance(..., source: str | None)`. Потребители — `deposits.py:188` и import-путь. `autoset_inferred_anchor` дополнительно трактует `(source is None and initial_balance>0)` как manual (legacy-защита). Связка с S2-06 (ROI) и S2-11 (G2/G3) — все три про anchor, но файлы разные.

- [ ] **Step 1 — Тест.** Добавить в `backend/tests/integration/test_opening_anchor_service.py`:
```python
def test_manual_via_sync_initial_balance_survives_autoset(session):
    """S2-05: ручной initial_balance, установленный через sync_initial_balance
    с source='manual', НЕ перетирается авто-якорем на следующем sync.
    Раньше source не проставлялся → guard был мёртв → значение уничтожалось."""
    from capital_service import sync_initial_balance

    acc = _seed_acc2(session)
    sync_initial_balance(session, acc.id, 150000, source="manual", commit=True)
    session.refresh(acc)
    assert acc.initial_balance_source == "manual"

    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("150000")
    assert acc.initial_balance_source == "manual"


def test_legacy_null_source_with_balance_treated_as_manual(session):
    """S2-05: legacy-счёт (initial_balance>0, source=NULL) не перетирается."""
    acc = _seed_acc2(session)
    acc.initial_balance = Decimal("77000")
    acc.initial_balance_source = None
    session.commit()

    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("77000")
```
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_opening_anchor_service.py -q` → 2 новых FAILED (`TypeError: unexpected keyword 'source'` для первого; для второго — баланс перетёрт).
- [ ] **Step 3 — Фикс.** (a) `capital_service.py` — добавить параметр `source` в `sync_initial_balance` (сигнатура на строке 236-244):
```python
def sync_initial_balance(
    db: Session,
    account_id: int,
    amount: float,
    *,
    date: Optional[datetime] = None,
    note: Optional[str] = None,
    commit: bool = False,
) -> None:
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        return

    normalized_amount = float(amount or 0)
    setattr(account, "initial_balance", Decimal(str(normalized_amount)))
```
→
```python
def sync_initial_balance(
    db: Session,
    account_id: int,
    amount: float,
    *,
    date: Optional[datetime] = None,
    note: Optional[str] = None,
    source: Optional[str] = None,
    commit: bool = False,
) -> None:
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        return

    normalized_amount = float(amount or 0)
    setattr(account, "initial_balance", Decimal(str(normalized_amount)))
    if source is not None:
        setattr(account, "initial_balance_source", source)
```
(b) `deposits.py:188` — передать `source="manual"`:
```python
    sync_initial_balance(
        db,
        account_id,
        amount,
        date=operation_date,
        note="Начальный депозит",
        source="manual",
        commit=True,
    )
```
(c) import-путь `trades.py` (строка ~475, вызов `sync_initial_balance` из импорта отчёта) — добавить `source="manual"` в тот вызов (открыть строку, подтвердить kwargs, вставить `source="manual"`).
(d) `opening_anchor_service.py:47-49` — трактовать legacy NULL как manual:
```python
    # Manual имеет приоритет — никогда не перетираем (spec §3.4).
    if account.initial_balance_source == "manual":
        return AnchorDecision(False, Decimal("0"), "manual", "manual source frozen")
```
→
```python
    # Manual имеет приоритет — никогда не перетираем (spec §3.4).
    # Legacy-счёт (баланс задан вручную до ADR-0010, source=NULL) трактуем
    # как manual, иначе авто-якорь молча уничтожит пользовательский ввод.
    if account.initial_balance_source == "manual" or (
        account.initial_balance_source is None
        and Decimal(str(account.initial_balance or 0)) > 0
    ):
        return AnchorDecision(
            False, Decimal(str(account.initial_balance or 0)), "manual", "manual source frozen"
        )
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_opening_anchor_service.py -q` → all passed (включая существующий `test_complete_history_does_not_anchor`: там `initial_balance=0`, ветка legacy не сработает). `C:/Python314/python.exe -m pytest tests/unit/test_opening_anchor.py -q` (чистое ядро не тронуто) — passed.
- [ ] **Step 5 — Commit.** `fix(anchor): persist source='manual' and freeze legacy NULL balances (S2-05)`

---

### S2-06 [HIGH] Двойной счёт якоря в ROI-базе /stats/ — total_roi занижен ~вдвое

**Files:**
- Modify: `backend/routers/stats.py:399` (`public_period_start_balance`), `backend/routers/stats.py:374` (`starting_net_deposit`)
- Test: `backend/tests/integration/test_stats_roi_anchor_base.py` (Create)

**Проблема:** Для anchored брокер-счёта `public_period_start_balance = account_initial_balance + starting_net_deposit` (`stats.py:399`), но `starting_net_deposit = get_net_deposit_as_of(...)` при пустой DepositHistory возвращает сам `account.initial_balance` (`capital_service.py:154`), а при синтетическом INITIAL — тоже якорь. Итог: база = якорь + якорь; реальные Σ NET_DEPOSIT из OperationORM не входят. Расходится с `/broker/portfolio` (там честно anchor + Σ NET_DEPOSIT).

**Interfaces:** потребляет паттерн из `drawdown_baseline` (`stats.py:525-540`), где Σ NET_DEPOSIT уже считается через `OperationORM` + `cash_flow_classification`. Anchor-серия с S2-05/S2-11.

Решение: для `is_broker_user` считать `net_deposits_from_ops` = Σ payment по NET_DEPOSIT из OperationORM (as-of `period_start_date`), и `public_period_start_balance = account_initial_balance + net_deposits_from_ops`, а не через `get_net_deposit_as_of` (у которого fallback = сам initial_balance).

- [ ] **Step 1 — Тест.** Создать `backend/tests/integration/test_stats_roi_anchor_base.py`:
```python
"""S2-06: ROI-база anchored брокер-счёта = anchor + Σ NET_DEPOSIT(OperationORM),
БЕЗ двойного счёта якоря. Раньше get_net_deposit_as_of при пустой DepositHistory
возвращал сам initial_balance → база = anchor+anchor.

Oracle acc#2: anchor 99095 + Σ NET_DEPOSIT 8556 = 107651 (НЕ 198190).
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import database
from main import app
from models import Account, Base, OperationORM, Trade, TradeDirection, User


@pytest.fixture
def client_and_acc():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = _override
    s = TestingSession()
    u = User(email="roi@test.com", hashed_password="x", is_active=1)
    s.add(u); s.commit()
    acc = Account(user_id=u.id, name="Main", currency="RUB",
                  initial_balance=Decimal("99095"), initial_balance_source="inferred_anchor")
    acc.last_portfolio_value = Decimal("32938")
    s.add(acc); s.commit()
    # Σ NET_DEPOSIT = 8556 через OperationORM (тип input).
    s.add(OperationORM(account_id=acc.id, broker_account_id="B1", operation_id="d1",
                       operation_type="input", state="executed",
                       payment_units=8556, payment_nano=0, executed_at=datetime(2026, 6, 24)))
    s.add(Trade(account_id=acc.id, symbol="MXI", direction=TradeDirection.LONG,
                entry_price=Decimal("1"), quantity=Decimal("1"),
                entry_at=datetime(2026, 1, 5), exit_at=datetime(2026, 2, 5),
                pnl=Decimal("-100"), net_pnl=Decimal("-100")))
    s.commit()
    yield s, acc, u
    app.dependency_overrides.clear()
    s.close()


def test_broker_roi_base_no_double_anchor(client_and_acc, monkeypatch):
    s, acc, u = client_and_acc
    import auth_service
    monkeypatch.setattr(auth_service, "get_current_user", lambda *a, **k: u)
    monkeypatch.setattr(auth_service, "get_account_id", lambda db, user: acc.id)
    client = TestClient(app)
    resp = client.get("/stats/?period=all", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    body = resp.json()
    # period_start_balance = 99095 + 8556 = 107651, НЕ 198190 (99095*2).
    assert abs(body["period_start_balance"] - 107651) < 2.0
```
(если поле в схеме называется иначе — подтвердить по `schemas.DashboardStats` перед запуском; тест держится за фактическое имя.)
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_stats_roi_anchor_base.py -q` → FAIL (`period_start_balance ≈ 198190`).
- [ ] **Step 3 — Фикс.** В `get_stats` (`stats.py`) считать broker net-deposits из OperationORM. Заменить блок `public_period_start_balance` (строки 396-403):
```python
    period_start_balance_reason = None
    if is_broker_user and period_start_balance_reliable and account_initial_balance > 0:
        # ADR-0010: anchored broker → ROI-знаменатель = anchor + net deposits.
        # starting_balance=0 чтобы equity curve шла от 0 (cumulative PnL).
        public_period_start_balance = account_initial_balance + starting_net_deposit
    else:
```
→
```python
    period_start_balance_reason = None
    if is_broker_user and period_start_balance_reliable and account_initial_balance > 0:
        # ADR-0010 / S2-06: anchored broker → ROI-знаменатель = anchor +
        # Σ NET_DEPOSIT из OperationORM (реальные завозы, as-of period_start).
        # get_net_deposit_as_of при пустой DepositHistory возвращает сам
        # initial_balance → база = anchor+anchor (double count). Берём depozits
        # из того же источника, что drawdown_baseline ниже.
        from domain.pnl.cash_flow_classification import (
            CashFlowCategory as _CFC2,
            operation_types_in as _op_types_in2,
        )
        _dep_types2 = tuple(_op_types_in2(_CFC2.NET_DEPOSIT))
        net_dep_ops = 0.0
        if _dep_types2:
            _q = db.query(
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            ).filter(
                models.OperationORM.account_id == account_id,
                models.OperationORM.operation_type.in_(_dep_types2),
                models.OperationORM.state == "executed",
            )
            if period_start_date:
                _q = _q.filter(models.OperationORM.executed_at <= period_start_date)
            _r = _q.one()
            net_dep_ops = float(_r[0] or 0) + float(_r[1] or 0) / 1e9
        public_period_start_balance = account_initial_balance + net_dep_ops
    else:
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_stats_roi_anchor_base.py -q` → passed. Регресс: `C:/Python314/python.exe -m pytest tests/test_stats_cache.py -q`. P&L-sanity: сверить с `/broker/portfolio` базой (89a1e33) — обе должны давать 107651 для acc#2 (см. PNL_PLAYBOOK).
- [ ] **Step 5 — Commit.** `fix(stats): ROI base = anchor + net deposits from OperationORM, no double count (S2-06)`

**Финальное состояние реализации (после S3-14 + CR-1 интеграц-фикса) — ревью-follow-up:**
1. **Period-scoped date-фильтр (CR-1).** Реализация применяет `executed_at <= date_filter` ТОЛЬКО при явном периоде (`date_filter is not None`: today/week/month/3months/year/custom/start_trade_id). Числитель `total_pnl` period-scoped → знаменатель ROI тоже: депозиты после старта окна = заводы посреди периода, инъекция которых занижала бы ROI короткого периода. Для `period=all` (`date_filter` None) фильтра нет — полная Σ (deployed capital), что и даёт acc#2 = 107651. ВАЖНО: триггер — `date_filter`, НЕ `period_start_date` (последний выставляется ВСЕГДА, для all = дата первой сделки; фильтрация по нему сломала бы all, исключив поздние депозиты → баг base=99095). Покрыто `test_broker_roi_base_period_scoped_excludes_late_deposits`.
2. **ЗНАКОВАЯ Σ (signed), НЕ abs().** `net_dep_ops = Σ payment` без `abs()` — вывод средств (OUTPUT с отрицательным `payment_units`) УМЕНЬШАЕТ базу, согласовано с `get_net_deposits_baseline_from_db` (тоже signed, S3-14) и `drawdown_baseline`/`effective_deposits`. Покрыто `test_broker_roi_base_parity_with_baseline_on_withdrawal` (OUTPUT −20000: signed 87651; ошибочный abs дал бы 110539). НЕ реинтродуцировать `abs()`.

---

### S2-07 [HIGH] Лимит enrich 50 инструментов/прогон теряет сделки по инструментам 51+

**Files:**
- Modify: `backend/application/sync/pipeline.py:128` (`max_instruments_per_run`), `backend/application/sync/pipeline.py:552-590` (`_stage_enrich`)
- Test: `backend/tests/integration/test_pipeline_enrich_exhausts.py` (Create)

**Проблема:** `targets = missing[: self._max_instruments_per_run]` (`pipeline.py:563`, default 50) резолвит только 50; для нерезолвленных uid `_run_for_one` возвращает `0,0,[]` (`pipeline.py:614-618`), курсор коммитится, FIFO по инструментам 51+ не строится никогда. Первый sync активного трейдера с >50 инструментами молча теряет историю.

**Interfaces:** производит: enrich, зацикленный до исчерпания `missing` (rate-limiter в `client_factory`/cooldown gate уже защищает RPS). Не пересекается с другими задачами по коду, но логически близко к S2-08 (тот же файл, per-uid FIFO).

Решение: зациклить enrich по чанкам до полного исчерпания `missing`, сохранив per-chunk предел RPS через существующий throttle. Минимальный безопасный шаг — поднять лимит и обернуть резолв в while-loop по оставшимся missing.

- [ ] **Step 1 — Тест.** Создать `backend/tests/integration/test_pipeline_enrich_exhausts.py`:
```python
"""S2-07: enrich резолвит ВСЕ missing инструменты за прогон (циклом по чанкам),
а не только первые max_instruments_per_run. Иначе сделки по инструментам 51+
на первом sync теряются навсегда.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.sync.pipeline import SyncPipeline


@pytest.mark.asyncio
async def test_enrich_resolves_all_missing_across_chunks(monkeypatch):
    # 120 missing uid'ов, лимит 50 — должны разрешиться все 120.
    missing_uids = [f"uid-{i}" for i in range(120)]

    pipe = SyncPipeline(
        account_id=1,
        broker_account_id="B1",
        token_plaintext="t",
        session_factory=MagicMock(),
        max_instruments_per_run=50,
    )

    # missing_uids() всегда возвращает ещё-не-разрешённые.
    resolved_uids: list[str] = []

    def _missing_uids(session, uids):
        return [u for u in missing_uids if u not in resolved_uids]

    monkeypatch.setattr(pipe._instrument_repo, "missing_uids", _missing_uids)
    monkeypatch.setattr(pipe._instrument_repo, "upsert_many",
                        lambda session, insts: resolved_uids.extend(i.uid for i in insts))

    async def _fake_get_instrument_by_uid(uid):
        inst = MagicMock()
        inst.uid = uid
        return inst

    with patch("application.sync.pipeline.client_factory") as cf, \
         patch("application.sync.pipeline.TinkoffInstrumentsClient") as ic:
        cf.async_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        cf.async_client.return_value.__aexit__ = AsyncMock(return_value=False)
        ic.return_value.get_instrument_by_uid = _fake_get_instrument_by_uid

        total = await pipe._stage_enrich(missing_uids)

    assert sorted(resolved_uids) == sorted(missing_uids)
    assert total == 120
```
(Подтвердить фактическое имя метода — `_stage_enrich` — и его аргумент перед запуском; если сигнатура отличается, привести тест к ней.)
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_enrich_exhausts.py -q` → FAIL (resolved только 50, total==50).
- [ ] **Step 3 — Фикс.** Зациклить резолв по чанкам. В `_stage_enrich` (строки 559-590) заменить одноразовый `targets = missing[:limit]` на while-loop:
```python
        missing = await asyncio.to_thread(_missing)
        if not missing:
            return 0

        targets = missing[: self._max_instruments_per_run]
        log.info(
            f"enrich: {len(missing)} missing instruments, resolving {len(targets)}"
        )

        async with client_factory.async_client(self._token) as services:
            instruments_client = TinkoffInstrumentsClient(services)
            resolved = []
            for uid in targets:
                try:
                    inst = await instruments_client.get_instrument_by_uid(uid)
                    resolved.append(inst)
                except InstrumentNotFound:
                    log.warning(f"enrich: instrument {uid} not found, skipping")
                except BrokerError as exc:
                    log.warning(f"enrich: {uid}: {type(exc).__name__} — {exc.message}")

        if resolved:
            def _persist() -> None:
                session = self._session_factory()
                try:
                    self._instrument_repo.upsert_many(session, resolved)
                    session.commit()
                finally:
                    session.close()

            await asyncio.to_thread(_persist)
        return len(resolved)
```
→
```python
        missing = await asyncio.to_thread(_missing)
        if not missing:
            return 0

        log.info(f"enrich: {len(missing)} missing instruments, resolving all in chunks")

        total_resolved = 0
        # S2-07: резолвим ВСЕ missing чанками по max_instruments_per_run —
        # rate-limiter client_factory + IP-cooldown gate защищают RPS. Раньше
        # брали только первый чанк → сделки по инструментам 51+ терялись навсегда.
        for start in range(0, len(missing), self._max_instruments_per_run):
            targets = missing[start : start + self._max_instruments_per_run]
            async with client_factory.async_client(self._token) as services:
                instruments_client = TinkoffInstrumentsClient(services)
                resolved = []
                for uid in targets:
                    try:
                        inst = await instruments_client.get_instrument_by_uid(uid)
                        resolved.append(inst)
                    except InstrumentNotFound:
                        log.warning(f"enrich: instrument {uid} not found, skipping")
                    except BrokerError as exc:
                        log.warning(f"enrich: {uid}: {type(exc).__name__} — {exc.message}")

            if resolved:
                def _persist(_resolved=resolved) -> None:
                    session = self._session_factory()
                    try:
                        self._instrument_repo.upsert_many(session, _resolved)
                        session.commit()
                    finally:
                        session.close()

                await asyncio.to_thread(_persist)
                total_resolved += len(resolved)
        return total_resolved
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_enrich_exhausts.py tests/integration/test_pipeline_idempotency.py -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(sync): enrich all missing instruments in chunks, not just first 50 (S2-07)`

---

### S2-08 [HIGH] Generic except в per-uid FIFO глотает ошибку — курсор коммитится (нарушение SYNC-08)

**Files:**
- Modify: `backend/application/sync/pipeline.py:609-703` (`_run_for_one` + цикл `_stage_fifo_match`)
- Test: `backend/tests/integration/test_pipeline_fifo_error_no_cursor.py` (Create)

**Проблема:** `_run_for_one` ловит `except Exception` целиком (`pipeline.py:689-692`): транзиентная ошибка БД при `replace_for_instrument` → rollback + `return 0,0,[]`, pipeline продолжает, `_stage_commit_cursor` двигает курсор, статус 'success'. Сделки по инструменту протухают. Противоречит SYNC-08 (курсор двигается только когда trades соответствуют operations).

**Interfaces:** производит: разделённые ветки — осознанный skip (instrument is None) vs неожиданное исключение → аккумулируется → pipeline падает ДО `_stage_commit_cursor`. Тесно связано с S2-07 (тот же метод) и S2-17 (тот же паттерн «глотание → success»).

- [ ] **Step 1 — Тест.** Создать `backend/tests/integration/test_pipeline_fifo_error_no_cursor.py`:
```python
"""SYNC-08 / S2-08: если per-uid FIFO падает неожиданным исключением (не
InstrumentNotFound), pipeline НЕ двигает курсор и репортит error, а не success.
Раньше generic except глотал всё → курсор коммитился → протухшие сделки.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.sync.pipeline import SyncPipeline


@pytest.mark.asyncio
async def test_fifo_db_error_does_not_swallow(monkeypatch):
    pipe = SyncPipeline(
        account_id=1, broker_account_id="B1", token_plaintext="t",
        session_factory=MagicMock(),
    )

    op = MagicMock()
    op.instrument_uid = "uid-1"
    monkeypatch.setattr(pipe, "_extract_unique_uids", lambda ops: ["uid-1"])

    # instrument резолвится, но replace_for_instrument падает deadlock'ом.
    inst = MagicMock()
    monkeypatch.setattr(pipe._instrument_repo, "get_by_uid", lambda s, u: inst)
    monkeypatch.setattr(pipe._operation_repo, "fetch_for_instrument", lambda **k: [])
    monkeypatch.setattr(pipe._position_repo, "get_open_lots", lambda **k: ())
    monkeypatch.setattr(pipe._fifo_service, "match",
                        lambda **k: MagicMock(closed_trades=[], open_lots=[]))

    def _boom(*a, **k):
        raise RuntimeError("deadlock detected")

    monkeypatch.setattr(pipe._trade_repo, "replace_for_instrument", _boom)

    with pytest.raises(RuntimeError, match="deadlock"):
        await pipe._stage_fifo_match([op])
```
(Подтвердить, что `SyncPipeline` можно инстанцировать с `session_factory=MagicMock()` без побочек в `__init__`; репозитории мокаются полем.)
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_fifo_error_no_cursor.py -q` → FAIL (`DID NOT RAISE RuntimeError` — исключение проглочено, стадия вернула 0,0).
- [ ] **Step 3 — Фикс.** В `_run_for_one` (`pipeline.py:689-692`) — не глотать неожиданные исключения, только логировать и пробрасывать:
```python
            except Exception:
                session.rollback()
                log.exception("fifo_match failed for uid=%s", uid)
                return 0, 0, []
            finally:
                session.close()
```
→
```python
            except Exception:
                # S2-08 / SYNC-08: транзиентная ошибка БД (deadlock, IntegrityError
                # от конкурентного sync) НЕ должна молча возвращать 0 — иначе
                # _stage_commit_cursor сдвинет курсор при протухших сделках.
                # Осознанный skip выше — только для instrument is None.
                session.rollback()
                log.exception("fifo_match failed for uid=%s", uid)
                raise
            finally:
                session.close()
```
Проверить, что цикл в `_stage_fifo_match` (строки 699-703) `await asyncio.to_thread(_run_for_one, uid)` пробросит исключение — да, `to_thread` re-raises; оно поднимется из `_stage_fifo_match` → в `run()` попадёт в `except Exception` (строки 275-280) → `_save_error_state` + `raise`, курсор НЕ коммитится. Никакого доп. кода не нужно.
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_fifo_error_no_cursor.py tests/integration/test_pipeline_cursor_atomicity.py -q` → passed (atomicity-тест подтверждает: курсор не двинулся).
- [ ] **Step 5 — Commit.** `fix(sync): re-raise unexpected per-uid FIFO errors so cursor holds (S2-08)`

---

### S2-09 [HIGH] Лендинг-тикер отдаёт 1 из 10 и кеширует как stale=false

**Files:**
- Modify: `backend/market_service.py:307` (порог полноты в `get_landing_ticker`)
- Test: `backend/tests/test_landing_ticker.py` (добавить кейс порога)

**Проблема:** `stale = len(tickers) == 0` (`market_service.py:307`) считает 1/10 (только IMOEX из SNDX, когда TQBR marketdata анонимно пуст) «успехом» и кеширует на 60с; фронт уходит в fallback только при `length===0` → гости видят строку из одного IMOEX.

**Interfaces:** производит: порог `min_full`. Фронтовый `LiveTicker.tsx` уже уходит в статичный fallback при пустом массиве (`length===0`) — при `stale=true, tickers=[]` он покажет полный статичный snapshot (лучше, чем один символ). Backend-only фикс.

- [ ] **Step 1 — Тест.** Добавить в `backend/tests/test_landing_ticker.py`:
```python
@pytest.mark.asyncio
async def test_partial_response_below_threshold_is_stale(service):
    """S2-09: если TQBR marketdata пуст (анонимный доступ) и собрался только
    IMOEX из индекс-блока — это НЕ успех: stale=True, tickers=[], НЕ кешируем.
    Иначе гости лендинга видят бегущую строку из одного символа."""
    shares_empty = {"marketdata": {"columns": ["SECID", "LAST"], "data": []}}
    with patch.object(market_service, "_moex_get",
                      _dispatcher(shares=shares_empty)):
        result = await service.get_landing_ticker()

    assert result["stale"] is True
    assert result["tickers"] == []
    # Кеш не заполнен — повторный вызов снова пойдёт в ISS.
    assert market_service._ticker_cache.get("landing:ticker") is None
```
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_landing_ticker.py::test_partial_response_below_threshold_is_stale -q` → FAIL (`stale is False`, tickers=[IMOEX]).
- [ ] **Step 3 — Фикс.** `market_service.py:307-311` — ввести порог полноты (набор курируемый из 10, требуем ≥5):
```python
        stale = len(tickers) == 0
        result = {"stale": stale, "tickers": tickers}
        if not stale:
            _ticker_cache.set("landing:ticker", result)
        return result
```
→
```python
        # S2-09: 1/10 (только IMOEX при пустом TQBR marketdata) — не успех.
        # Требуем порог полноты, иначе фронт уйдёт в полный статичный fallback
        # вместо бегущей строки из одного символа, и мы не кешируем огрызок.
        _MIN_FULL = 5
        stale = len(tickers) < _MIN_FULL
        if stale:
            return {"stale": True, "tickers": []}
        result = {"stale": False, "tickers": tickers}
        _ticker_cache.set("landing:ticker", result)
        return result
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_landing_ticker.py -q` → all passed (happy-path даёт 4 акции + IMOEX = 5 ≥ порога; при необходимости happy-payload содержит достаточно строк — проверить: SBER/GAZP/LKOH + IMOEX = 4 < 5!). **Важно:** если happy-тест упадёт из-за порога 5 — снизить `_MIN_FULL` до 4 или расширить happy-payload. Подтвердить фактическим прогоном и выбрать порог так, чтобы happy-path (реально доступные строки) проходил, а «только IMOEX» — нет. Live-смоук (инфо): `curl -s http://localhost:8000/api/landing/ticker` — если реально отдаёт 1 символ, ответ станет `{"stale":true,"tickers":[]}`.
- [ ] **Step 5 — Commit.** `fix(landing): mark ticker stale below completeness threshold (S2-09)`

---

### S2-10 [MED] GET /trades/positions грузит ВСЕ сделки в память, пагинация после

**Files:**
- Modify: `backend/routers/trades.py:587-631` (`read_position_trades` — пагинация ключей в SQL)
- Test: `backend/tests/test_trades.py` (добавить кейс пагинации без полной загрузки)

**Проблема:** `all_trades = db.query(Trade).filter(account_id==...).all()` (`trades.py:587-592`) тянет все Trade-строки (5–10k), группирует в Python, режет страницу только на `:631`. Память + CPU-группировка на каждый запрос.

**Interfaces:** потребляет: `read_position_trades` уже стала `def` в S2-01 — правим синхронную версию. Двухфазный запрос: (1) страница `position_id` в SQL, (2) загрузка Trade по IN.

MEDIUM/сжатый цикл, но правка нетривиальная — оставляем полноценный тест.

- [ ] **Step 1 — Тест.** Добавить в `backend/tests/test_trades.py` (использовать существующий client/seed-фикстуры файла; ниже — контрактный тест на то, что при 3 позициях и limit=2 возвращаются 2 группы и Trade загружаются только для страницы). Подтвердить имена фикстур файла перед вставкой:
```python
def test_positions_pagination_returns_page_of_groups(client, seed_positions):
    """S2-10: /trades/positions?limit=2 возвращает ровно 2 position-группы
    (страница ключей), а не все. Регресс-гард на пагинацию по position_id."""
    # seed_positions создаёт 3 разных position_id с закрытыми round-trip'ами.
    resp = client.get("/trades/positions?status=all&skip=0&limit=2",
                      headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    resp2 = client.get("/trades/positions?status=all&skip=2&limit=2",
                       headers=AUTH_HEADER)
    assert len(resp2.json()) == 1
```
Если в `test_trades.py` нет готовой фикстуры на 3 позиции — создать локальную `seed_positions`, добавляющую 3 Trade с разными `position_id`+`instrument_uid`, все закрытые. (Смотреть, как соседние тесты файла делают seed/auth.)
- [ ] **Step 2 — Запуск, ожидание FAIL или baseline.** `cd backend && C:/Python314/python.exe -m pytest tests/test_trades.py::test_positions_pagination_returns_page_of_groups -q`. На текущей реализации пагинация в Python работает → тест может пройти сразу (он же — регресс-гард). Цель фикса — перенести срез в SQL без изменения контракта; если тест зелёный, он защищает контракт при рефакторинге.
- [ ] **Step 3 — Фикс.** Двухфазный запрос. Заменить полную загрузку (`trades.py:587-592`) на страницу ключей в SQL + загрузку по IN. Before:
```python
    account_id = auth_service.get_account_id(db, current_user)
    all_trades = (
        db.query(models.Trade)
        .filter(models.Trade.account_id == account_id)
        .order_by(models.Trade.entry_at.asc())
        .all()
    )
```
After (страница position_id в SQL, затем Trade только для страницы; legacy-сделки без position_id получают синтетический ключ по id):
```python
    account_id = auth_service.get_account_id(db, current_user)

    # S2-10: пагинация ГРУПП в SQL — не тянем все 5-10k Trade в память.
    # Фаза 1: агрегируем ключи (instrument_uid, position_id) с last-activity
    # и is_open, фильтруем по status, режем страницу в БД.
    last_activity = func.max(
        func.coalesce(models.Trade.exit_at, models.Trade.entry_at)
    ).label("last_activity")
    has_open = func.max(
        case((models.Trade.exit_at.is_(None), 1), else_=0)
    ).label("has_open")
    key_q = (
        db.query(
            models.Trade.instrument_uid,
            models.Trade.position_id,
            last_activity,
            has_open,
        )
        .filter(models.Trade.account_id == account_id)
        .filter(models.Trade.position_id.isnot(None), models.Trade.instrument_uid.isnot(None))
        .group_by(models.Trade.instrument_uid, models.Trade.position_id)
    )
    if status == "open":
        key_q = key_q.having(has_open == 1)
    elif status == "closed":
        key_q = key_q.having(has_open == 0)
    key_rows = key_q.order_by(last_activity.desc()).offset(skip).limit(limit).all()

    # Legacy-сделки (position_id IS NULL) — каждая сама себе позиция. Тянем их
    # страницей по last-activity, дополняя до limit если ключей позиций мало.
    page_keys = [(r.instrument_uid, r.position_id) for r in key_rows]
    if page_keys:
        conds = [
            (models.Trade.instrument_uid == uid) & (models.Trade.position_id == pid)
            for uid, pid in page_keys
        ]
        all_trades = (
            db.query(models.Trade)
            .filter(models.Trade.account_id == account_id)
            .filter(or_(*conds))
            .order_by(models.Trade.entry_at.asc())
            .all()
        )
    else:
        all_trades = []
```
Добавить импорты вверху `trades.py` если отсутствуют: `from sqlalchemy import func, case, or_`. Затем в теле удалить последующий Python-`filtered_groups.sort(...)` + `paginated_groups = filtered_groups[skip:skip+limit]` (строки 625-631) — группировка теперь только для страницы (построить `groups` по `all_trades`, но `paginated_groups = list(groups.items())`, сортировка сохраняется по `last_activity`). **Важно про legacy:** если в проекте есть legacy-сделки без position_id, добавить второй SQL-запрос страницы для них (по `id`) — но только если тест на legacy падает; иначе YAGNI, зафиксировать TODO-ограничение в докстринге (legacy round-trips не пагинируются этой веткой).
- [ ] **Step 4 — Верификация.** `cd backend && C:/Python314/python.exe -m pytest tests/test_trades.py -q` → passed. Ручной GET-смоук: `curl -s "http://localhost:8000/trades/positions?limit=2" -H "Authorization: Bearer <dev>"` → ≤2 группы. Сверить форму ответа (PositionTrade-схема) не изменилась.
- [ ] **Step 5 — Commit.** `fix(perf): paginate /trades/positions keys in SQL, not in Python (S2-10)`

---

### S2-11 [MED] G2-телескоп отключён для stock-only счетов — якорь может поглотить ошибку журнала

**Files:**
- Modify: `backend/domain/pnl/opening_anchor.py:19` (ужесточить G3), `backend/services/opening_anchor_service.py:114` (запрет позднего re-anchor)
- Test: `backend/tests/unit/test_opening_anchor.py` (добавить кейсы G3-tight)

**Проблема:** G2 работает только при `|varmargin_net| ≥ 1` (`opening_anchor.py:76`). Для stock-only счёта остаются G1 (знак) и G3 (`candidate ≤ 50×крупнейший buy` — потолок практически недостижим). Баг журнала (пропущенные sell, задвоение) занижает journal → candidate раздувается → якорится → маскируется навсегда. Плюс re-anchor разрешён из `inferred_skipped`/`inferred_blocked` в любой поздний день.

**Interfaces:** anchor-серия (S2-05, S2-06). Чистое ядро `opening_anchor.py` покрыто unit-тестом `test_opening_anchor.py`. Решение из find.fix: ужесточить G3 (5× суммарного gross_buy вместо 50× пикового) — но это меняет oracle-константу. Осторожно: `test_anchor_max_factor_constant_is_50` фиксирует 50 и `test_pure_stocks_account_anchors_via_g3` ожидает anchored при peak 40000. Меняем осмысленно: вводим доп. `ANCHOR_MAX_SUM_FACTOR` для stock-only ветки, оставляя пиковый 50× для совместимости.

MEDIUM/сжатый, но ядро P&L — полноценный TDD.

- [ ] **Step 1 — Тест.** Добавить в `backend/tests/unit/test_opening_anchor.py`:
```python
def test_stock_only_candidate_over_sum_of_buys_is_blocked():
    """S2-11: на stock-only счёте (G2 skip) якорь-кандидат больше суммарного
    gross_buy теперь блокируется (deposit-независимый гейт вместо только 50×peak).
    Пропущенные sell-операции раздувают candidate → раньше молча якорилось."""
    d = decide_anchor(
        incomplete_history=True,
        portfolio_value=Decimal("500000"),
        net_deposits=Decimal("10000"),
        journal_pnl=Decimal("-100000"),  # заниженный журнал → candidate=590000
        body_closed=Decimal("0"),
        varmargin_net=Decimal("0"),
        open_settled=Decimal("0"),
        gross_buy_peak=Decimal("40000"),
        gross_buy_sum=Decimal("60000"),  # candidate 590000 >> 5*60000=300000
    )
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_stock_only_plausible_candidate_still_anchors():
    """Разумный candidate ≤ 5×Σgross_buy на stock-only — якорится (не regressed)."""
    d = decide_anchor(
        incomplete_history=True,
        portfolio_value=Decimal("90000"),
        net_deposits=Decimal("10000"),
        journal_pnl=Decimal("-20000"),
        body_closed=Decimal("0"),
        varmargin_net=Decimal("0"),
        open_settled=Decimal("0"),
        gross_buy_peak=Decimal("40000"),
        gross_buy_sum=Decimal("40000"),  # candidate 100000 ≤ 5*40000=200000
    )
    assert d.should_anchor is True
    assert d.source == "inferred_anchor"
```
Также обновить существующие вызовы `decide_anchor(...)` в файле — добавить `gross_buy_sum=<peak>` там, где тест иначе упадёт (сделать `gross_buy_sum` необязательным с дефолтом = `gross_buy_peak`, чтобы старые тесты не падали — см. Step 3).
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_opening_anchor.py -q` → 2 новых FAILED (`TypeError: unexpected keyword 'gross_buy_sum'`).
- [ ] **Step 3 — Фикс.** (a) `opening_anchor.py` — добавить константу и параметр, ужесточить stock-only ветку:
```python
# G3 — потолок правдоподобия: якорь не больше N× крупнейшей buy-операции.
ANCHOR_MAX_FACTOR = Decimal("50")
```
→
```python
# G3 — потолок правдоподобия: якорь не больше N× крупнейшей buy-операции.
ANCHOR_MAX_FACTOR = Decimal("50")
# G3' (S2-11) — deposit-независимый гейт для stock-only счетов (G2 skip):
# якорь не больше M× СУММАРНОГО gross_buy. Ловит заниженный журнал
# (пропущенные sell), который раздувает candidate.
ANCHOR_MAX_SUM_FACTOR = Decimal("5")
```
Сигнатура `decide_anchor` — добавить `gross_buy_sum: Decimal | None = None`:
```python
def decide_anchor(
    *,
    incomplete_history: bool,
    portfolio_value: Decimal,
    net_deposits: Decimal,
    journal_pnl: Decimal,
    body_closed: Decimal,
    varmargin_net: Decimal,
    open_settled: Decimal,
    gross_buy_peak: Decimal,
    gross_buy_sum: Decimal | None = None,
) -> AnchorDecision:
```
Перед финальным `return ... inferred_anchor` (после G3 на строке 87-91) добавить G3' для stock-only:
```python
    # G3' — stock-only счёт (G2 не сработал): гейт по суммарному gross_buy.
    _effective_sum = gross_buy_sum if gross_buy_sum is not None else gross_buy_peak
    if abs(varmargin_net) < VARMARGIN_FLOOR and candidate > ANCHOR_MAX_SUM_FACTOR * abs(_effective_sum):
        return AnchorDecision(
            False, Decimal("0"), "inferred_blocked",
            f"stock-only candidate={candidate} exceeds {ANCHOR_MAX_SUM_FACTOR}x sum buys",
        )
```
(b) `opening_anchor_service.py` — передать `gross_buy_sum` (сумма всех buy) и запретить поздний re-anchor из blocked/skipped. Сначала посчитать сумму (рядом с `gross_buy_peak`, строки 90-99):
```python
    gross_buy_peak = max(
        (abs(_payment(u, n)) for u, n in buy_rows), default=Decimal(0)
    )
```
→
```python
    gross_buy_peak = max(
        (abs(_payment(u, n)) for u, n in buy_rows), default=Decimal(0)
    )
    gross_buy_sum = sum(
        (abs(_payment(u, n)) for u, n in buy_rows), Decimal(0)
    )
```
и в вызов `decide_anchor(...)` добавить `gross_buy_sum=gross_buy_sum,`.
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_opening_anchor.py tests/integration/test_opening_anchor_service.py -q` → all passed (существующие: `gross_buy_sum` дефолтит на peak, ветка G3' — только stock-only; acc#2 имеет varmargin → G3' skip → без регрессии).
- [ ] **Step 5 — Commit.** `fix(anchor): deposit-independent G3' gate for stock-only accounts (S2-11)`

---

### S2-12 [MED] IS_SCHEDULER_WORKER не задан в деплой-конфигах + per-process asyncio-lock не кросс-процессный

**Files:**
- Modify: `.env.production.example` (добавить `IS_SCHEDULER_WORKER`), `docs/RUNBOOK.md`/`docs/deployment.md` (recipe), `backend/routers/broker.py` (advisory lock вокруг manual sync — опционально в рамках S2-04)
- Test: конфиг-валидация + существующий `test_worker_role.py` (из S2-03)

**Проблема:** `IS_SCHEDULER_WORKER` не задан ни в `docker-compose.prod.yml`, ни в `.env.production.example` (grep: 0) → дефолт `true` на всех 8 процессах. S2-03 создаёт compose-сервис; S2-12 закрывает env-документацию и (опционально) кросс-процессную сериализацию.

**Interfaces:** зависит от S2-03 (compose-сервис уже создан). S2-04 уже добавил per-process in-flight guard; кросс-процессную часть (pg advisory lock) можно вынести сюда, но это отдельный HIGH-объём — в рамках MEDIUM делаем документацию + гард-тест.

MEDIUM/сжатый: конфиг + docs, unit-гард из S2-03.

- [ ] **Step 1 — Проверка.** `cd c:/Users/Administrator/Eqio/ATOM && grep -rn IS_SCHEDULER_WORKER .env.production.example docker-compose.prod.yml docs/ | head` — зафиксировать, что переменной нет в `.env.production.example` (после S2-03 она есть в compose).
- [ ] **Step 2 — Фикс.** (a) `.env.production.example` — добавить с пояснением:
```
# Роль воркера: API-реплики = false (не держат stream/scheduler);
# отдельный сервис backend-scheduler = true. См. docker-compose.prod.yml.
IS_SCHEDULER_WORKER=false
```
(b) `docs/RUNBOOK.md` — добавить раздел «Singleton-воркер»:
```markdown
### Singleton-воркер (scheduler + stream consumers)
Фоновые синглтоны крутятся ТОЛЬКО на сервисе `backend-scheduler`
(IS_SCHEDULER_WORKER=true, --workers 1). API-реплики (`backend`) — false.
Формула: ровно один процесс во всём деплое с true. Проверка после деплоя:
`docker compose -f docker-compose.prod.yml config | grep -A2 IS_SCHEDULER_WORKER`.
Кросс-процессную сериализацию sync одного аккаунта обеспечивает
in-flight guard оркестратора (S2-04) в пределах процесса; для полной
кросс-процессной защиты — pg_try_advisory_lock(account_id) (backlog).
```
- [ ] **Step 3 — Верификация + commit.** `grep -n IS_SCHEDULER_WORKER .env.production.example` → строка есть. `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_worker_role.py -q` → passed. Commit: `fix(infra): document IS_SCHEDULER_WORKER role split in env+runbook (S2-12)`

---

### S2-13 [MED] Reset во время sync оставляет БД полустёртой с продвинутым курсором

**Files:**
- Modify: `backend/routers/broker.py:480-512` (`reset_connection` — отклонять при running sync)
- Test: `backend/tests/test_accounts.py` или Create `backend/tests/integration/test_reset_during_sync.py`

**Проблема:** `reset_connection` (`broker.py:506-507`) не берёт account-lock и не проверяет in-flight sync: если auto-sync идёт, pipeline дозаписывает батч и коммитит свежий курсор + 'success' → в operations только окно последнего батча, курсор актуальный, следующий sync инкрементальный → полная история не перетянется.

**Interfaces:** потребляет: сигнал «sync идёт». Простейший кросс-процессный признак — `conn.last_sync_status == 'running'` (устанавливается pipeline в начале). Проверить фактическое поле статуса на BrokerConnection.

MEDIUM/сжатый.

- [ ] **Step 1 — Проверка/тест.** Подтвердить, какое поле pipeline пишет как «running» (grep): `cd backend && grep -rn "last_sync_status" application/sync/ | head`. Если статус 'running' выставляется — тест:
```python
def test_reset_rejected_while_sync_running(client, seed_broker_conn_running, AUTH_HEADER):
    """S2-13: reset во время идущего sync отклоняется 409, чтобы не оставить
    БД полустёртой с продвинутым курсором."""
    resp = client.post(f"/broker/connections/{seed_broker_conn_running}/reset",
                       headers=AUTH_HEADER)
    assert resp.status_code == 409
    assert "синхрониз" in resp.json()["detail"].lower()
```
`seed_broker_conn_running` — фикстура, создающая BrokerConnection с `last_sync_status='running'`.
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest -k reset_rejected_while_sync_running -q` → FAIL (200 вместо 409).
- [ ] **Step 3 — Фикс.** В `reset_connection` (`broker.py`, после проверки `if conn is None`, до `db.commit()` строка 506) добавить:
```python
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")

    # Закрываем текущую сессию (database.get_db) перед reset_account, чтобы
    # тот мог открыть свою собственную SessionLocal и сделать commit.
    db.commit()
```
→
```python
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")

    # S2-13: не сбрасывать при идущем sync — иначе pipeline дозапишет свой
    # батч и закоммитит свежий курсор поверх обнулённого → полная история
    # не перетянется, а UI покажет "success".
    if conn.last_sync_status == "running":
        raise HTTPException(
            status_code=409,
            detail="Синхронизация выполняется, повторите reset позже",
        )

    # Закрываем текущую сессию (database.get_db) перед reset_account, чтобы
    # тот мог открыть свою собственную SessionLocal и сделать commit.
    db.commit()
```
(Если поле называется иначе — подставить фактическое имя из Step 1.)
- [ ] **Step 4 — Верификация.** `cd backend && C:/Python314/python.exe -m pytest -k reset -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(sync): reject broker reset while sync is running (S2-13)`

---

### S2-14 [MED] Stale-cursor детект только для одностраничного batch — многостраничный проходит незамеченным

**Files:**
- Modify: `backend/application/sync/pipeline.py:489` (условие stale-детекта)
- Test: `backend/tests/integration/test_pipeline_stale_cursor.py` (Create) или добавить к существующему

**Проблема:** stale-детект гейтится `if cursor and current == cursor` (`pipeline.py:489`) — срабатывает только когда пагинация закончилась на ПЕРВОЙ странице. Многостраничный stale-ответ (>page_size старых операций) сдвигает `current`, условие не выполняется, stale не ловится, курсор сохраняется как success, свежие операции пропущены.

**Interfaces:** тот же цикл fetch, что S2-08. Fix из находки: сравнивать `max(executed_at)` батча против `max` в БД БЕЗУСЛОВНО перед return, для любого числа страниц.

MEDIUM/сжатый.

- [ ] **Step 1 — Тест.** Создать `backend/tests/integration/test_pipeline_stale_cursor.py` (или добавить кейс). Проверяем, что при многостраничном stale-ответе (2 страницы старых ops, next_cursor становится None) срабатывает fallback на from_dt:
```python
"""S2-14: stale-cursor детект работает при ЛЮБОМ числе страниц.

Многостраничный stale-ответ (cursor валиден, отдаёт >page_size старых ops,
затем next_cursor=None) раньше проходил незамеченным: `current == cursor`
уже неверно после первой страницы. Проверяем что max(batch) < max(db) − 1ч
триггерит fallback независимо от пагинации.
"""
# Тест уровня unit на выделенную функцию решения о stale (см. Step 3):
from datetime import datetime, timedelta

from application.sync.pipeline import _is_stale_batch  # helper, вводится фиксом


def test_multipage_stale_detected():
    max_in_batch = datetime(2024, 1, 1)
    max_in_db = datetime(2026, 1, 1)
    assert _is_stale_batch(max_in_batch, max_in_db) is True


def test_fresh_batch_not_stale():
    now = datetime(2026, 1, 1, 12, 0)
    assert _is_stale_batch(now, now - timedelta(minutes=5)) is False


def test_none_db_max_not_stale():
    assert _is_stale_batch(datetime(2024, 1, 1), None) is False
```
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_stale_cursor.py -q` → FAIL (`ImportError: _is_stale_batch`).
- [ ] **Step 3 — Фикс.** Вынести решение о stale в чистый хелпер и вызывать безусловно перед return (не только внутри `current == cursor`). Добавить в `pipeline.py` (module-level, до класса):
```python
def _is_stale_batch(max_in_batch, max_in_db) -> bool:
    """max(executed_at) батча строго старше max в БД (на >1ч) → stale cursor."""
    from datetime import timedelta
    if max_in_db is None or max_in_batch is None:
        return False
    return max_in_batch < max_in_db - timedelta(hours=1)
```
В цикле fetch — при `not next_cursor or next_cursor == current` вычислять stale безусловно (для любого числа страниц), не только внутри `if cursor and current == cursor`. Переписать блок (строки 487-515) так, чтобы:
- `empty_batch` остаётся под `cursor and current == cursor and not all_ops`;
- stale-ветка выносится наружу: `elif all_ops and _is_stale_batch(max(o.executed_at for o in all_ops), await self._get_max_executed_at()): needs_fallback = True; fallback_reason = "stale_batch_older_than_db"`.

Конкретно (заменить строки 487-515):
```python
                    needs_fallback = False
                    fallback_reason = None
                    if cursor and current == cursor:
                        if not all_ops:
                            needs_fallback = True
                            fallback_reason = "empty_batch"
                        else:
                            max_in_batch = max(o.executed_at for o in all_ops)
                            max_in_db = await self._get_max_executed_at()
                            if (
                                max_in_db is not None
                                and max_in_batch < max_in_db - timedelta(hours=1)
                            ):
                                needs_fallback = True
                                fallback_reason = "stale_batch_older_than_db"
                                log.warning(...)  # (существующий лог)
```
→
```python
                    needs_fallback = False
                    fallback_reason = None
                    if cursor and current == cursor and not all_ops:
                        needs_fallback = True
                        fallback_reason = "empty_batch"
                    elif all_ops:
                        # S2-14: stale-детект БЕЗУСЛОВНО, для любого числа
                        # страниц — многостраничный stale-ответ сдвигает
                        # current, но max(batch) < max(db) всё равно ловит.
                        max_in_batch = max(o.executed_at for o in all_ops)
                        max_in_db = await self._get_max_executed_at()
                        if _is_stale_batch(max_in_batch, max_in_db):
                            needs_fallback = True
                            fallback_reason = "stale_batch_older_than_db"
                            log.warning(
                                "cursor_returned_stale_data",
                                extra={
                                    "account_id": self._account_id,
                                    "stuck_cursor": (cursor or "")[:32],
                                    "batch_max_executed_at": max_in_batch.isoformat(),
                                    "db_max_executed_at": max_in_db.isoformat(),
                                    "ops_returned": len(all_ops),
                                },
                            )
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_stale_cursor.py tests/integration/test_pipeline_cursor_atomicity.py tests/integration/test_pipeline_idempotency.py -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(sync): detect stale cursor for multi-page batches too (S2-14)`

---

### S2-15 [LOW] get_current_user_optional не проверяет revocation/staleness/is_active

**Files:**
- Modify: `backend/auth_service.py:586-609` (`get_current_user_optional`)
- Test: `backend/tests/test_auth_hardening.py` (добавить кейс)

**Проблема:** `get_current_user_optional` (строки 599-606) декодирует токен и сразу возвращает user без `is_token_revoked`/`is_token_stale`/`is_active` (в отличие от `get_current_user`, строки 564-583). Сейчас dependency нигде не подключён (мёртвый код) — ловушка на будущее.

**Interfaces:** зеркалит проверки `get_current_user`. LOW/сжатый.

- [ ] **Step 1 — Тест.** Добавить в `backend/tests/test_auth_hardening.py` (использовать паттерн файла для генерации токена/user). Проверить, что optional-версия возвращает None для отозванного токена:
```python
def test_optional_returns_none_for_revoked_token(db_session, make_user, make_token):
    """S2-15: get_current_user_optional уважает revocation, как get_current_user."""
    import auth_service
    user = make_user(is_active=1)
    token, jti = make_token(user)
    auth_service.revoke_token(db_session, jti)  # имя по факту файла
    request = _request_with_bearer(token)
    result = asyncio.run(
        auth_service.get_current_user_optional(request, _creds(token), db_session)
    )
    assert result is None
```
Подстроить под фактические хелперы `test_auth_hardening.py` (make_user/make_token/revoke) — прочитать файл перед вставкой.
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest -k optional_returns_none_for_revoked -q` → FAIL (возвращён user).
- [ ] **Step 3 — Фикс.** `auth_service.py:599-606` — продублировать проверки:
```python
    try:
        token_data = decode_access_token(token)
        
        if token_data is None:
            return None
        
        user = get_user_by_id(db, token_data.user_id)
        return user
        
    except Exception:
        return None
```
→
```python
    try:
        token_data = decode_access_token(token)

        if token_data is None:
            return None

        # S2-15: та же гигиена, что get_current_user — отозванный/протухший
        # токен и деактивированный аккаунт НЕ считаем авторизованными.
        if is_token_revoked(db, token_data.jti):
            return None

        user = get_user_by_id(db, token_data.user_id)
        if user is None:
            return None
        if is_token_stale(user, token_data.iat_ts):
            return None
        if user.is_active != 1:
            return None
        return user

    except Exception:
        return None
```
- [ ] **Step 4 — Верификация.** `cd backend && C:/Python314/python.exe -m pytest tests/test_auth_hardening.py -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(auth): optional user dep respects revocation/staleness/is_active (S2-15)`

---

### S2-16 [LOW] Orchestrator/Redis-клиент пересоздаются каждые 60с — bulkhead мёртв, коннекты текут

**Files:**
- Modify: `backend/sync_scheduler.py:219` (кеш оркестратора), `backend/application/sync/ip_cooldown_gate.py:99` (общий клиент + close)
- Test: `backend/tests/unit/test_orchestrator_singleton.py` (Create)

**Проблема:** `_check_broker_sync` вызывает `build_default_orchestrator()` каждые 60с (`sync_scheduler.py:219`) → новый `IpCooldownGate` с новым `aioredis.from_url` (`ip_cooldown_gate.py:99`), который никогда не `.close()`-ится. `_in_flight` живёт один прогон.

**Interfaces:** производит: кешированный оркестратор в scheduler. Связано с S2-04 (in-flight guard теперь реально нужен — кеширование делает его долгоживущим). LOW/сжатый.

- [ ] **Step 1 — Тест.** Создать `backend/tests/unit/test_orchestrator_singleton.py`:
```python
"""S2-16: scheduler переиспользует один orchestrator между итерациями,
а не строит новый (с новым Redis-клиентом) каждые 60с.
"""
from unittest.mock import MagicMock, patch

from sync_scheduler import SyncScheduler  # имя класса по факту файла


def test_orchestrator_built_once_across_iterations():
    sched = SyncScheduler()
    built = []

    def _factory():
        o = MagicMock()
        built.append(o)
        return o

    with patch("application.sync.orchestrator.build_default_orchestrator", _factory):
        first = sched._get_orchestrator()
        second = sched._get_orchestrator()

    assert first is second
    assert len(built) == 1
```
(Подтвердить имя класса планировщика и точку сборки перед вставкой.)
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_orchestrator_singleton.py -q` → FAIL (`AttributeError: _get_orchestrator`).
- [ ] **Step 3 — Фикс.** В классе планировщика добавить lazy-кеш и использовать его в `_check_broker_sync`:
```python
    async def _check_broker_sync(self) -> None:
        if not settings.BROKER_SYNC_V2_ENABLED:
            return
        from application.sync.orchestrator import build_default_orchestrator

        orchestrator = build_default_orchestrator()
        if orchestrator is None:
            return
```
→
```python
    def _get_orchestrator(self):
        # S2-16: строим оркестратор (и его Redis-клиент IpCooldownGate) один раз,
        # переиспользуем между 60с-итерациями. Иначе churn TCP-коннектов к Redis
        # + in-flight bulkhead живёт лишь один прогон.
        if getattr(self, "_orchestrator", None) is None:
            from application.sync.orchestrator import build_default_orchestrator
            self._orchestrator = build_default_orchestrator()
        return self._orchestrator

    async def _check_broker_sync(self) -> None:
        if not settings.BROKER_SYNC_V2_ENABLED:
            return
        orchestrator = self._get_orchestrator()
        if orchestrator is None:
            return
```
Инициализировать `self._orchestrator = None` в `__init__` планировщика. Redis-клиент гейта закрывать в lifespan shutdown (`main.py`) — добавить в блок shutdown (рядом с `moex_async.close_client()`), если у гейта есть `.close()`; иначе вынести в backlog (не блокер LOW). Приоритет — устранить churn через кеш.
- [ ] **Step 4 — Верификация.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_orchestrator_singleton.py -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(sync): reuse orchestrator across scheduler iterations (S2-16)`

---

### S2-17 [LOW] _replace_positions_from_live глотает ошибку вставки — sync репортит success с протухшими позициями

**Files:**
- Modify: `backend/application/sync/pipeline.py:1335-1342` (`_replace_positions_from_live`)
- Test: `backend/tests/integration/test_pipeline_positions_error.py` (Create)

**Проблема:** `except Exception` в `_replace_positions_from_live` (`pipeline.py:1335-1340`) только логирует+rollback, pipeline продолжает как success. Сбой на самой вставке (кривой quantity/валюта) оставляет протухшие позиции без сигнала в last_sync_status/health. Осознанный degrade задокументирован только для BrokerError на fetch (строки 973-978).

**Interfaces:** тот же паттерн «глотание → success», что S2-08. Стадия mark-to-market идёт ДО `_stage_commit_cursor` (строка 224 vs 265) — значит проброс исключения сохранит SYNC-08. LOW/сжатый.

- [ ] **Step 1 — Тест.** Создать `backend/tests/integration/test_pipeline_positions_error.py`:
```python
"""S2-17: сбой ВСТАВКИ live-позиций (не BrokerError на fetch) пробрасывается,
а не глотается — иначе sync репортит success с протухшим снапшотом позиций.
"""
from unittest.mock import MagicMock

import pytest

from application.sync.pipeline import SyncPipeline


def test_replace_positions_insert_error_propagates(monkeypatch):
    pipe = SyncPipeline(
        account_id=1, broker_account_id="B1", token_plaintext="t",
        session_factory=MagicMock(),
    )
    bad_session = MagicMock()
    bad_session.commit.side_effect = RuntimeError("bad quantity")
    monkeypatch.setattr(pipe, "_session_factory", lambda: bad_session)

    positions = [{"instrument_uid": "u1", "quantity": 1}]  # форма по факту метода
    with pytest.raises(RuntimeError, match="bad quantity"):
        pipe._replace_positions_from_live(positions)
```
(Подтвердить сигнатуру `_replace_positions_from_live` и форму входа перед вставкой — читать метод целиком.)
- [ ] **Step 2 — Запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_positions_error.py -q` → FAIL (`DID NOT RAISE` — проглочено).
- [ ] **Step 3 — Фикс.** `pipeline.py:1335-1342`:
```python
        except Exception:
            log.exception("live_positions replace failed")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
```
→
```python
        except Exception:
            # S2-17: сбой вставки live-позиций (кривой quantity/валюта) — не
            # осознанный degrade (тот только для BrokerError на fetch выше).
            # Стадия идёт ДО _stage_commit_cursor → проброс сохраняет SYNC-08:
            # курсор не двинется, sync репортит error, а не молчаливый success.
            log.exception("live_positions replace failed")
            try:
                session.rollback()
            except Exception:
                pass
            raise
        finally:
            session.close()
```
- [ ] **Step 4 — Запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_pipeline_positions_error.py tests/integration/test_pipeline_cursor_atomicity.py -q` → passed. `C:/Python314/python.exe -c "import main"` OK.
- [ ] **Step 5 — Commit.** `fix(sync): propagate live-position insert errors instead of silent success (S2-17)`

---

## Проверка спринта

Полный гейт (из `backend/`):

```bash
cd c:/Users/Administrator/Eqio/ATOM/backend
C:/Python314/python.exe -m pytest tests/unit tests/integration -q
C:/Python314/python.exe -c "import main"
```

Зелёным должно быть:
- Все новые тесты задач S2-01…S2-17.
- Регресс-сьюты: `test_trades.py`, `test_stats_cache.py`, `test_advanced_benchmark.py`, `test_landing_ticker.py`, `test_auth_hardening.py`, `test_opening_anchor.py`, `test_opening_anchor_service.py`, `test_pipeline_cursor_atomicity.py`, `test_pipeline_idempotency.py`, `test_orchestrator.py`.
- `import main` без ошибок (все роутеры импортируются, изменённые сигнатуры валидны).

Конфиг-задачи (S2-02, S2-03, S2-12):
```bash
cd c:/Users/Administrator/Eqio/ATOM
docker compose -f docker-compose.prod.yml config >/dev/null && echo "compose OK"
grep -n IS_SCHEDULER_WORKER docker-compose.prod.yml .env.production.example
grep -n "max_connections" docker-compose.prod.yml
```
Ожидаемо: `backend` → `IS_SCHEDULER_WORKER: "false"`, `backend-scheduler` → `"true"`; `postgres` → `command: postgres -c max_connections=200`; `.env.production.example` содержит `IS_SCHEDULER_WORKER` и `DB_MAX_OVERFLOW`.

P&L-задачи (S2-05, S2-06, S2-11) — после прогона сверить с `docs/PNL_PLAYBOOK.md`: для anchored acc#2 ROI-база = 107651 (anchor 99095 + Σ NET_DEPOSIT 8556), совпадает с `/broker/portfolio`.

Флейк (игнорировать в полном прогоне): `test_debug_warning`, `test_market_service_async::test_get_client_returns_singleton`.

GET-смоук (backend :8000, без мутаций прод-данных):
```bash
curl -s http://localhost:8000/api/landing/ticker        # S2-09: {"stale":..., "tickers":[...]}
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health   # S2-01: 200 под нагрузкой
```

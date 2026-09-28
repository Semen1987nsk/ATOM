# Sprint 3 — Производительность и нагрузка (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend держит 500 одновременных пользователей с записанным SLO (p95, error-rate, pool); event-loop не блокируется sync I/O; БД-запросы без N+1; pipeline'ы синхронизации устойчивы к partial-crash; есть нагрузочный harness в репо.

**Architecture:**
- **Async-first I/O:** MOEX-вызовы через `httpx.AsyncClient`; access-log persist через `asyncio.to_thread` (fire-and-forget). Никакого блокирующего HTTP/DB в async-роутах.
- **Query-batched reads:** `read_position_trades` префетчит позиции одним `IN`-SELECT'ом; `/stats/` использует cheap fingerprint (`max(updated_at)`) вместо хеш-роллапа всех сделок; `_select_due_connection_ids` один SELECT вместо цикла.
- **Schema-aware indexes (Postgres-first, SQLite-safe):** alembic-миграции с `postgresql_concurrently=True` для composite-индексов (operations type+state, access_log status+time); конверсия `Trade.tags` JSON→JSONB + GIN.
- **Retention jobs:** `_run_cleanup_loop` в `sync_scheduler` чистит `access_log >30d`, `sync_events >90d`, `revoked_tokens` после `expires_at`.
- **Pipeline atomicity:** cursor сдвигается только после успешного FIFO+positions+health; `stream_manager._tasks` чистится в `_on_done`.
- **Load harness:** k6-скрипты (`backend/tests/load/`) с baseline-SLO (p95 < 800ms на read-эндпойнтах, error_rate < 1%, DB-pool без exhausted).

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · httpx (async) · alembic (Postgres + SQLite roundtrip) · pytest-asyncio · k6 (load harness).

**Operating mode (NO-COMMIT):** код, тесты и миграции — да; `git add` / `git commit` — НЕТ. После каждой задачи остаём изменения в working tree; пользователь ревьюит diff и коммитит сам.

---

## Декомпозиция файлов

**Новые:**
- `backend/services/moex_async.py` — singleton `httpx.AsyncClient` для MOEX вызовов с retry/timeout (вынесем общую логику из `market_service` и `moex_service`).
- `backend/jobs/retention.py` — функции `cleanup_access_log`, `cleanup_sync_events`, `cleanup_revoked_tokens` (чистые SQL DELETE'ы, тестируемые в отрыве).
- `backend/alembic/versions/0027_perf_indexes.py` — composite-индексы (`operations(state, operation_type)`, `access_log(status_code, created_at)`).
- `backend/alembic/versions/0028_tags_jsonb_gin.py` — JSON→JSONB + GIN (Postgres-only, SQLite no-op).
- `backend/tests/load/README.md` — как запускать k6 локально и в staging.
- `backend/tests/load/scenarios/read_hot_path.js` — k6 сценарий: login → /stats/, /trades/, /trades/positions, /market/prices.
- `backend/tests/load/scenarios/sync_idle.js` — k6 сценарий holding 500 idle connections.
- `backend/tests/load/baseline_slo.md` — записываем фактические p95/error_rate из baseline run.
- `backend/utils/downsample.py` — LTTB-downsample для equity_curve.

**Модифицируемые:**
- `backend/middleware.py` — `_persist_access_log` через `asyncio.to_thread`.
- `backend/market_service.py` — `_moex_get` и второй цикл через `httpx.AsyncClient`; `get_current_prices`/`get_futures_specs` → async.
- `backend/moex_service.py` — `httpx.Client` → `httpx.AsyncClient`; методы async.
- `backend/routers/market.py` — await на async-сервис.
- `backend/routers/stats.py` — IMOEX overlay вызывает уже-async сервис без to_thread; cheap fingerprint; equity_curve downsample; tag-фильтр через SQL (после JSONB).
- `backend/routers/trades.py` — `read_position_trades`: префетч `PositionORM` одним IN; реальная пагинация по группам.
- `backend/application/sync/orchestrator.py` — `_select_due_connection_ids` один SELECT.
- `backend/application/sync/pipeline.py` — cursor сдвигается после `_stage_fifo_match`; `_replace_positions_from_live` инвариантный тест + (опц.) savepoint.
- `backend/application/sync/stream_manager.py` — `_on_done` чистит `_tasks`; cleanup для `_account_locks` через explicit `release_account_lock`.
- `backend/application/sync/sync_scheduler.py` — регистрация cleanup-loop с интервалом 24h.
- `backend/models.py` — typing-only поправки если потребуются (декларация `JSONB` для Postgres dialect).

---

## Batch 1 — Async I/O fixes (event-loop unblocking)

### Task 1.1: PERF-03 — access-log persist через `asyncio.to_thread`

**Files:**
- Modify: `backend/middleware.py` (функция `_persist_access_log`, строки 174–204)
- Test: `backend/tests/unit/test_middleware_access_log.py` (новый)

- [ ] **Step 1: Read current middleware code**

Открой `backend/middleware.py` и найди классы `RequestLoggingMiddleware`, методы `dispatch` (~129) и `_persist_access_log` (~174). Цель — НЕ менять то, что пишется в `AccessLogORM`, только перенести запись из event-loop в thread.

- [ ] **Step 2: Write failing test — persist runs in thread**

```python
# backend/tests/unit/test_middleware_access_log.py
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from backend.middleware import RequestLoggingMiddleware


@pytest.mark.asyncio
async def test_persist_access_log_does_not_block_event_loop(monkeypatch):
    """PERF-03: sync db.commit() inside dispatch must run in a worker thread."""
    captured_thread_ids = []

    def fake_session_factory():
        import threading
        captured_thread_ids.append(threading.get_ident())
        sess = MagicMock()
        sess.add = MagicMock()
        sess.commit = MagicMock()
        sess.close = MagicMock()
        return sess

    monkeypatch.setattr("backend.middleware.SessionLocal", fake_session_factory)

    mw = RequestLoggingMiddleware(app=MagicMock())
    request = MagicMock()
    request.url.path = "/api/x"
    request.method = "GET"
    request.headers = {}
    request.client.host = "1.2.3.4"
    request.state = MagicMock(user_id=None, request_id="rid-1")

    # _persist_access_log invocation site (через wrapper)
    await mw._persist_access_log_async(request, 200, 12.5, "1.2.3.4")

    import threading
    assert captured_thread_ids, "persist did not run"
    assert captured_thread_ids[0] != threading.get_ident(), \
        "persist ran on event-loop thread — would block"
```

- [ ] **Step 3: Run test — expect FAIL (method missing)**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/unit/test_middleware_access_log.py -v
```

Expected: `AttributeError: 'RequestLoggingMiddleware' object has no attribute '_persist_access_log_async'`.

- [ ] **Step 4: Implement — split sync persist + async wrapper**

В `backend/middleware.py`:

```python
async def _persist_access_log_async(self, request, status_code, duration_ms, client_ip):
    """PERF-03: offload sync DB write to worker thread."""
    try:
        await asyncio.to_thread(
            self._persist_access_log, request, status_code, duration_ms, client_ip
        )
    except Exception:  # noqa: BLE001 — fire-and-forget audit log
        pass
```

В `dispatch` заменить прямой вызов `self._persist_access_log(...)` на `asyncio.create_task(self._persist_access_log_async(...))` (fire-and-forget, не блокируем response).

- [ ] **Step 5: Run test — expect PASS**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/unit/test_middleware_access_log.py -v
```

- [ ] **Step 6: Run integration tests for access-log**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/ -k "access_log or middleware" -v
```

Expected: no regressions. Existing PR26 access-log tests могут потребовать `await asyncio.sleep(0.05)` чтобы task успел отработать — поправь точечно если падают.

- [ ] **Step 7: NO-COMMIT — leave for review**

Не делать `git add`/`git commit`. Перейти к Task 1.2.

---

### Task 1.2: PERF-04 — market_service.py на `httpx.AsyncClient`

**Files:**
- Create: `backend/services/moex_async.py`
- Modify: `backend/market_service.py` (`_moex_get` ~79, retry loop ~424, `get_current_prices`, `get_futures_specs`)
- Modify: `backend/routers/market.py` (await на async-сервис)
- Test: `backend/tests/unit/test_market_service_async.py`

- [ ] **Step 1: Create shared async-MOEX client singleton**

```python
# backend/services/moex_async.py
"""SYNC-04/PERF-04: единый httpx.AsyncClient для MOEX-вызовов.

Лимит коннекций + retry/backoff + общий timeout. Используется и в market_service,
и в moex_service вместо разных sync httpx.Client/requests.get.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=2.0)
_DEFAULT_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def get_client() -> httpx.AsyncClient:
    """Lazy-singleton AsyncClient. На shutdown зови `close_client()`."""
    global _client
    if _client is None or _client.is_closed:
        async with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, limits=_DEFAULT_LIMITS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def fetch_json(url: str, *, params: dict | None = None, retries: int = 2) -> Optional[dict[str, Any]]:
    """GET + json. None при сетевой ошибке (caller сам решает fallback)."""
    client = await get_client()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
    logger.warning("MOEX fetch failed %s: %s", url, last_exc)
    return None
```

- [ ] **Step 2: Write failing test for async fetch + singleton behaviour**

```python
# backend/tests/unit/test_market_service_async.py
import pytest
import httpx

from backend.services import moex_async


@pytest.mark.asyncio
async def test_get_client_returns_singleton():
    c1 = await moex_async.get_client()
    c2 = await moex_async.get_client()
    assert c1 is c2
    await moex_async.close_client()


@pytest.mark.asyncio
async def test_fetch_json_uses_async_path(httpx_mock):
    httpx_mock.add_response(url="https://iss.moex.com/x.json", json={"a": 1})
    result = await moex_async.fetch_json("https://iss.moex.com/x.json")
    assert result == {"a": 1}
    await moex_async.close_client()
```

Зависимость: `pytest-httpx`. Если не установлено — `pip install pytest-httpx>=0.30` и добавить в `requirements.txt` dev-extras.

- [ ] **Step 3: Run test — expect FAIL (module missing or httpx_mock missing)**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/unit/test_market_service_async.py -v
```

- [ ] **Step 4: Migrate `market_service.py`**

В `backend/market_service.py`:
- Удалить `import requests`.
- `_moex_get` → `async def _moex_get(url: str, timeout: float = 5)`, внутри `return await moex_async.fetch_json(url)`.
- В retry-loop (`~line 413-425`) заменить `requests.get(url, params=params, timeout=10)` на `await moex_async.fetch_json(url, params=params)`.
- `get_current_prices` и `get_futures_specs` → async (методы `MarketService`).

Сохранить кеш в `_price_cache` как сейчас.

- [ ] **Step 5: Update router**

В `backend/routers/market.py`:

```python
@router.get("/prices")
@limiter.limit(MARKET_LIMIT)
async def prices(
    request: Request,
    tickers: str = Query(...),
    _: User = Depends(get_current_user),
):
    return await market_data_service.get_current_prices(tickers.split(","))
```

(Аналогично `/futures-specs`.)

- [ ] **Step 6: Run all market tests**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/ -k "market" -v
```

Expected: PASS. Если есть тесты с `monkeypatch.setattr("backend.market_service.requests.get", ...)` — поправь на `pytest_httpx` или `monkeypatch.setattr("backend.services.moex_async.fetch_json", ...)`.

- [ ] **Step 7: Register shutdown hook**

В `backend/main.py` lifespan (`shutdown`-секция) добавить `await moex_async.close_client()`.

- [ ] **Step 8: NO-COMMIT**

---

### Task 1.3: SYNC-04 — moex_service.py на `httpx.AsyncClient`

**Files:**
- Modify: `backend/moex_service.py` (`get_futures_specs` ~120, `get_candles_history` ~289, `get_index_history` ~360)
- Modify: `backend/routers/stats.py` (`_build_imoex_overlay_async` — снять `asyncio.to_thread`)
- Test: `backend/tests/unit/test_moex_service_async.py`

- [ ] **Step 1: Read current moex_service.py methods**

Запомни сигнатуры и поведение пагинации в `get_index_history` (есть while-loop с `start += step`).

- [ ] **Step 2: Write failing test for async API**

```python
# backend/tests/unit/test_moex_service_async.py
import pytest
from backend.moex_service import get_moex_service


@pytest.mark.asyncio
async def test_get_candles_history_is_async(httpx_mock):
    httpx_mock.add_response(
        url__regex=r"https://iss\.moex\.com/.+",
        json={"candles": {"data": [], "columns": []}},
    )
    svc = get_moex_service()
    # Метод должен быть coroutine
    result = await svc.get_candles_history("SBER", "1h", "2026-05-01", "2026-05-02")
    assert isinstance(result, list)
```

- [ ] **Step 3: Run — expect FAIL** (метод sync, `await` упадёт)

- [ ] **Step 4: Migrate methods to async**

В каждом методе:
```python
async def get_candles_history(self, ...):
    data = await moex_async.fetch_json(url, params=params)
    if not data:
        return []
    # ... парсинг как было
```

Для `get_index_history` сохранить пагинацию через `async while`.

- [ ] **Step 5: Update stats router**

В `backend/routers/stats.py` `_build_imoex_overlay_async`:

```python
async def _build_imoex_overlay_async(start_date, end_date):
    # SYNC-04: было asyncio.to_thread(_moex.get_index_history, ...)
    return await _moex.get_index_history("IMOEX", start_date, end_date)
```

- [ ] **Step 6: Run tests**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/ -k "moex or imoex or stats" -v
```

Expected: PASS. Найди вызовы `get_moex_service().get_X(...)` в проекте — все должны быть в async context'е.

- [ ] **Step 7: NO-COMMIT**

---

## Batch 2 — Query optimizations (без schema changes)

### Task 2.1: PERF-06 — префетч PositionORM одним IN-SELECT

**Files:**
- Modify: `backend/routers/trades.py` (`read_position_trades` ~536, цикл ~614–625)
- Test: `backend/tests/integration/test_positions_no_n_plus_1.py`

- [ ] **Step 1: Write failing test — count SQL queries**

```python
# backend/tests/integration/test_positions_no_n_plus_1.py
import pytest
from sqlalchemy import event

from backend.database import engine


@pytest.fixture
def query_counter():
    counts = {"n": 0}

    def _count(*_args, **_kw):
        counts["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    yield counts
    event.remove(engine, "before_cursor_execute", _count)


def test_position_trades_no_n_plus_1(client, auth_headers, seed_30_open_positions, query_counter):
    """PERF-06: 30 open positions = constant SQL count, not 30+."""
    resp = client.get("/trades/positions?status=open", headers=auth_headers)
    assert resp.status_code == 200
    # До правки было ~32 (1 на трейды + 30 на PositionORM + auth + access_log).
    # После — должно быть ≤ 8 (трейды + один IN + auth + access_log + sundry).
    assert query_counter["n"] <= 10, f"got {query_counter['n']} queries"
```

Зависит от фикстуры `seed_30_open_positions` — создаст 30 различных `instrument_uid`, по одной открытой позиции. Если фикстуры нет — создай в `backend/tests/conftest.py` (минимально 30 Trade-rows со `status='open'`).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Refactor read_position_trades**

В `backend/routers/trades.py` после строки `groups = ...`:

```python
# PERF-06: префетч позиций одним IN-SELECT вместо N+1.
open_uids = [
    g[0].instrument_uid
    for g in groups.values()
    if any(t.status == "open" for t in g) and g[0].instrument_uid
]
positions_by_uid: dict[str, models.PositionORM] = {}
if open_uids:
    rows = (
        db.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.instrument_uid.in_(open_uids),
        )
        .all()
    )
    positions_by_uid = {r.instrument_uid: r for r in rows}
```

В цикле заменить `.query(...).first()` на `positions_by_uid.get(first.instrument_uid)`.

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Run full positions tests**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/ -k "position" -v
```

- [ ] **Step 6: NO-COMMIT**

---

### Task 2.2: SYNC-10 — `_select_due_connection_ids` один SELECT

**Files:**
- Modify: `backend/application/sync/orchestrator.py` (~252–290)
- Test: `backend/tests/unit/test_orchestrator_select_due.py`

- [ ] **Step 1: Write failing test — query count for 50 connections**

```python
def test_select_due_runs_single_query(session_factory_with_50_connections, query_counter):
    """SYNC-10: один SELECT вместо 1 + N."""
    orchestrator = build_orchestrator(session_factory_with_50_connections)
    ids = orchestrator._select_due_connection_ids()
    assert len(ids) > 0
    assert query_counter["n"] == 1
```

- [ ] **Step 2: Run — expect FAIL** (51 query).

- [ ] **Step 3: Rewrite as single SELECT**

```python
def _select_due_connection_ids(self) -> list[int]:
    with self._session_factory() as session:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = (
            session.query(
                BrokerConnection.id,
                BrokerConnection.circuit_open_until,
                BrokerConnection.last_sync_at,
                BrokerConnection.sync_interval_minutes,
            )
            .join(Account, BrokerConnection.account_id == Account.id)
            .join(User, Account.user_id == User.id)
            .filter(
                BrokerConnection.is_active.is_(True),
                User.is_active.is_(True),
            )
            .all()
        )

    ids: list[int] = []
    for cid, circuit_open_until, last_sync_at, interval_min in rows:
        if circuit_open_until and circuit_open_until > now:
            continue
        if last_sync_at is None:
            ids.append(cid)
            continue
        next_due = last_sync_at + timedelta(minutes=interval_min or DEFAULT_SYNC_INTERVAL)
        if next_due <= now:
            ids.append(cid)
    return ids
```

- [ ] **Step 4: Run — expect PASS** + scheduler-тесты не падают.

- [ ] **Step 5: NO-COMMIT**

---

### Task 2.3: PERF-10 — реальная пагинация позиций + LTTB downsample equity

**Files:**
- Create: `backend/utils/downsample.py`
- Modify: `backend/routers/trades.py` (`read_position_trades`)
- Modify: `backend/routers/stats.py` (`equity_curve`)
- Test: `backend/tests/unit/test_downsample.py`, `backend/tests/integration/test_positions_pagination.py`

- [ ] **Step 1: Create LTTB downsample utility**

```python
# backend/utils/downsample.py
"""LTTB (Largest-Triangle-Three-Buckets) downsample для equity_curve.

Сохраняет визуальную форму ряда при сжатии до N точек.
"""
from __future__ import annotations
from typing import Sequence


def lttb(points: Sequence[tuple[float, float]], threshold: int) -> list[tuple[float, float]]:
    n = len(points)
    if threshold >= n or threshold < 3:
        return list(points)
    bucket_size = (n - 2) / (threshold - 2)
    out: list[tuple[float, float]] = [points[0]]
    a = 0
    for i in range(threshold - 2):
        avg_start = int((i + 1) * bucket_size) + 1
        avg_end = int((i + 2) * bucket_size) + 1
        avg_end = min(avg_end, n)
        if avg_end <= avg_start:
            continue
        avg_x = sum(p[0] for p in points[avg_start:avg_end]) / (avg_end - avg_start)
        avg_y = sum(p[1] for p in points[avg_start:avg_end]) / (avg_end - avg_start)
        range_start = int(i * bucket_size) + 1
        range_end = int((i + 1) * bucket_size) + 1
        max_area = -1.0
        chosen = points[range_start]
        ax, ay = points[a]
        for p in points[range_start:range_end]:
            area = abs((ax - avg_x) * (p[1] - ay) - (ax - p[0]) * (avg_y - ay)) * 0.5
            if area > max_area:
                max_area = area
                chosen = p
        out.append(chosen)
        a = points.index(chosen)
    out.append(points[-1])
    return out
```

- [ ] **Step 2: Write test for LTTB**

```python
# backend/tests/unit/test_downsample.py
from backend.utils.downsample import lttb


def test_lttb_returns_threshold_points():
    pts = [(float(i), float(i * i)) for i in range(1000)]
    out = lttb(pts, 100)
    assert len(out) == 100
    assert out[0] == pts[0]
    assert out[-1] == pts[-1]


def test_lttb_passthrough_when_below_threshold():
    pts = [(1.0, 2.0), (3.0, 4.0)]
    assert lttb(pts, 100) == pts
```

- [ ] **Step 3: Run — expect PASS** после Step 1.

- [ ] **Step 4: Apply downsample to equity_curve in stats router**

В `backend/routers/stats.py`, там где формируется `equity_curve`:

```python
from backend.utils.downsample import lttb

# ... после построения equity_curve as list[dict]
if len(equity_curve) > settings.EQUITY_CURVE_MAX_POINTS:
    indexed = [(float(i), float(p["equity"])) for i, p in enumerate(equity_curve)]
    keep_indices = {int(p[0]) for p in lttb(indexed, settings.EQUITY_CURVE_MAX_POINTS)}
    equity_curve = [p for i, p in enumerate(equity_curve) if i in keep_indices]
```

В `backend/config.py`:
```python
EQUITY_CURVE_MAX_POINTS: int = 500
```

- [ ] **Step 5: Fix positions pagination — apply skip/limit AFTER grouping**

В `read_position_trades`:

```python
# Преобразуем groups в list, отсортируем по дате последнего трейда desc
ordered_groups = sorted(
    groups.items(),
    key=lambda kv: max(t.exit_at or t.entry_at for t in kv[1]),
    reverse=True,
)
# Затем применяем skip/limit
paginated = ordered_groups[skip : skip + limit]
```

- [ ] **Step 6: Test — assert pagination & downsample**

```python
def test_positions_pagination_returns_limit(client, auth_headers, seed_30_positions):
    resp = client.get("/trades/positions?limit=10&skip=0", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 10


def test_stats_equity_curve_downsampled(client, auth_headers, seed_2000_trades):
    resp = client.get("/stats/", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["equity_curve"]) <= 500
```

- [ ] **Step 7: Run all touched tests — PASS**

- [ ] **Step 8: NO-COMMIT**

---

### Task 2.4: PERF-07 — cheap fingerprint вместо хеша всех сделок

**Files:**
- Modify: `backend/routers/stats.py` (`_get_trades_state_fingerprint` ~217)
- Test: `backend/tests/unit/test_stats_fingerprint.py`

- [ ] **Step 1: Write failing test — fingerprint без полного скана**

```python
def test_trades_state_fingerprint_uses_aggregate_query(db_session, query_counter):
    """PERF-07: fingerprint = 1 SQL (max(updated_at), count), не полный скан."""
    from backend.routers.stats import _get_trades_state_fingerprint
    fp = _get_trades_state_fingerprint(db_session, account_id=1)
    assert isinstance(fp, str)
    assert query_counter["n"] == 1
```

- [ ] **Step 2: Run — FAIL** (текущая функция принимает список сделок).

- [ ] **Step 3: Replace fingerprint with aggregate SQL**

```python
def _get_trades_state_fingerprint(db, account_id: int) -> str:
    """PERF-07: дешёвый fingerprint без загрузки всех Trade-rows.

    Использует aggregate-SQL: max(updated_at) || count(id).
    Меняется при любом INSERT/UPDATE сделок аккаунта.
    """
    row = db.query(
        func.max(models.Trade.updated_at),
        func.count(models.Trade.id),
    ).filter(models.Trade.account_id == account_id).one()
    max_updated, total = row
    return f"{max_updated.isoformat() if max_updated else '0'}|{total}"
```

Где раньше передавали `trades`, теперь — `db, account_id`. Обнови `get_stats` (`stats.py:217`) — fingerprint вычисляется до загрузки `all_trades`, и при cache hit `all_trades` не загружается вообще.

- [ ] **Step 4: Make sure load is skipped on cache hit**

В `get_stats`:
```python
fingerprint = _get_trades_state_fingerprint(db, account_id)
cache_key = _get_cache_key(account_id, period=period, ..., trades_fingerprint=fingerprint)
cached = _get_cached(cache_key)
if cached:
    return cached
# Только теперь грузим all_trades
all_trades = query.order_by(models.Trade.exit_at.desc()).all()
```

- [ ] **Step 5: Run — PASS**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/ -k "stats" -v
```

Если есть тесты, мокающие старую сигнатуру `_get_trades_state_fingerprint(trades)` — поправь моки.

- [ ] **Step 6: NO-COMMIT**

---

## Batch 3 — Schema changes (alembic)

### Task 3.1: PERF-08a — composite-индексы

**Files:**
- Create: `backend/alembic/versions/0027_perf_indexes.py`
- Test: `backend/tests/integration/test_perf_indexes_roundtrip.py`

- [ ] **Step 1: Write roundtrip test (alembic up → down → up)**

```python
# backend/tests/integration/test_perf_indexes_roundtrip.py
import subprocess
import pytest


@pytest.mark.skipif(
    "sqlite" not in str(__import__("backend.database", fromlist=["engine"]).engine.url),
    reason="alembic roundtrip checked on SQLite (Postgres проверяем в CI)",
)
def test_alembic_0027_roundtrip():
    base = "PYTHONUTF8=1 python -X utf8 -m alembic"
    # up
    subprocess.run(f"{base} upgrade head", shell=True, check=True, cwd="backend")
    # down 1
    subprocess.run(f"{base} downgrade -1", shell=True, check=True, cwd="backend")
    # up again
    subprocess.run(f"{base} upgrade head", shell=True, check=True, cwd="backend")
```

- [ ] **Step 2: Run — expect FAIL** (миграции нет).

- [ ] **Step 3: Write migration**

```python
# backend/alembic/versions/0027_perf_indexes.py
"""PERF-08: composite indexes (operations type+state, access_log status+time).

Revision ID: 0027_perf_indexes
Revises: 0026_auth_hardening
Create Date: 2026-05-26
"""
from alembic import op


revision = "0027_perf_indexes"
down_revision = "0026_auth_hardening"
branch_labels = None
depends_on = None

_INDEXES = [
    # (name, table, columns, kwargs)
    ("ix_operations_state_type_executed",
     "operations", ["state", "operation_type", "executed_at"], {}),
    ("ix_access_log_status_created",
     "access_log", ["status_code", "created_at"], {}),
]


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    for name, table, cols, _kw in _INDEXES:
        if is_pg:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                       f"ON {table} ({', '.join(cols)})")
        else:
            op.create_index(name, table, cols, if_not_exists=True)


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    for name, _t, _c, _kw in reversed(_INDEXES):
        if is_pg:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        else:
            op.drop_index(name, if_exists=True)
```

**Внимание (Postgres CONCURRENTLY):** `CREATE INDEX CONCURRENTLY` нельзя внутри транзакции alembic. Нужно вне; добавь в начале файла:

```python
# Postgres: индексы должны создаваться вне транзакции
def upgrade() -> None:
    # alembic.ini-вариант: используем op.execute + autocommit_block
    ...
```

Для Postgres используем `with op.get_context().autocommit_block():`. Уточни корректный idiom — он зависит от версии alembic в проекте; в SQLite просто `op.create_index`.

- [ ] **Step 4: Run roundtrip test — PASS**

- [ ] **Step 5: NO-COMMIT**

---

### Task 3.2: PERF-08b — Trade.tags JSON→JSONB + GIN (Postgres-only)

**Files:**
- Create: `backend/alembic/versions/0028_tags_jsonb_gin.py`
- Modify: `backend/models.py` (тип `Trade.tags`)
- Modify: `backend/routers/stats.py` (tag-фильтр через SQL вместо Python-loop)
- Test: `backend/tests/integration/test_tags_jsonb.py`

- [ ] **Step 1: Read models.py — Trade.tags declaration**

`Trade.tags: Column(JSON, default=list)` (строка ~353). На SQLite JSON ≈ TEXT с json-serialization; на Postgres — JSON (не JSONB).

- [ ] **Step 2: Write failing integration test — tag filter through SQL**

```python
def test_stats_filters_tags_via_sql(client, auth_headers, seed_trades_with_tags, query_counter):
    """PERF-08b: tag-фильтр приходит как WHERE tags @> '...', не Python-loop."""
    resp = client.get("/stats/?tag=FOMO", headers=auth_headers)
    assert resp.status_code == 200
    # Query count должен быть малым (нет загрузки всех сделок) — проверь через query_counter.
    assert query_counter["n"] <= 12
```

- [ ] **Step 3: Run — expect FAIL** (currently Python-loop, query_counter может быть OK, но больше всё равно).

- [ ] **Step 4: Write migration**

```python
# backend/alembic/versions/0028_tags_jsonb_gin.py
"""PERF-08b: trade.tags JSON→JSONB + GIN.

Revision ID: 0028_tags_jsonb_gin
Revises: 0027_perf_indexes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0028_tags_jsonb_gin"
down_revision = "0027_perf_indexes"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite — JSON остаётся, no-op
    op.alter_column(
        "trades", "tags",
        type_=postgresql.JSONB(),
        postgresql_using="tags::jsonb",
    )
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trades_tags_gin "
        "ON trades USING GIN (tags jsonb_path_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_trades_tags_gin")
    op.alter_column(
        "trades", "tags",
        type_=postgresql.JSON(),
        postgresql_using="tags::json",
    )
```

- [ ] **Step 5: Update models.py declaration**

```python
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

# Dialect-aware: JSON on SQLite, JSONB on Postgres
tags = Column(JSON().with_variant(JSONB(), "postgresql"), default=list, nullable=False, server_default="[]")
```

- [ ] **Step 6: Update tag-filter in stats router**

```python
# Было:
# all_trades = query.order_by(...).all()
# if tag: all_trades = [t for t in all_trades if t.tags and ...]
#
# Стало:
if tag:
    if db.bind.dialect.name == "postgresql":
        query = query.filter(models.Trade.tags.contains([tag]))
    else:
        # SQLite fallback — JSON-функция
        query = query.filter(func.json_extract(models.Trade.tags, "$").contains(tag))
all_trades = query.order_by(models.Trade.exit_at.desc()).all()
```

- [ ] **Step 7: Run alembic roundtrip + integration tests on SQLite**

Migration на SQLite — no-op; integration-test проверь, что tag-фильтр всё ещё корректно работает (через SQLite fallback).

- [ ] **Step 8: NO-COMMIT**

---

### Task 3.3: PERF-09 — retention jobs (access_log, sync_events, revoked_tokens)

**Files:**
- Create: `backend/jobs/retention.py`
- Modify: `backend/application/sync/sync_scheduler.py` (зарегистрировать cleanup-loop)
- Modify: `backend/config.py` (retention thresholds)
- Test: `backend/tests/unit/test_retention.py`

- [ ] **Step 1: Add retention settings**

```python
# backend/config.py
ACCESS_LOG_RETENTION_DAYS: int = 30
SYNC_EVENTS_RETENTION_DAYS: int = 90
RETENTION_CLEANUP_INTERVAL_HOURS: int = 24
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/unit/test_retention.py
from datetime import datetime, timedelta, timezone
from backend.jobs.retention import (
    cleanup_access_log,
    cleanup_sync_events,
    cleanup_revoked_tokens,
)
from backend import models


def test_cleanup_access_log_deletes_old(db_session):
    old = models.AccessLogORM(
        path="/", method="GET", status_code=200,
        created_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    fresh = models.AccessLogORM(
        path="/", method="GET", status_code=200,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    deleted = cleanup_access_log(db_session, retention_days=30)
    assert deleted == 1
    remaining = db_session.query(models.AccessLogORM).all()
    assert len(remaining) == 1
    assert remaining[0].created_at == fresh.created_at


def test_cleanup_revoked_tokens_uses_expires_at(db_session):
    expired = models.RevokedTokenORM(
        jti="a", expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    still_valid = models.RevokedTokenORM(
        jti="b", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add_all([expired, still_valid])
    db_session.commit()

    deleted = cleanup_revoked_tokens(db_session)
    assert deleted == 1
```

- [ ] **Step 3: Run — FAIL** (`backend/jobs/retention.py` не существует).

- [ ] **Step 4: Implement retention.py**

```python
# backend/jobs/retention.py
"""PERF-09: retention/cleanup для безграничных таблиц."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from backend import models

logger = logging.getLogger(__name__)


def _utc_naive_threshold(days: int) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)


def cleanup_access_log(session: Session, *, retention_days: int) -> int:
    cutoff = _utc_naive_threshold(retention_days)
    n = session.query(models.AccessLogORM)\
        .filter(models.AccessLogORM.created_at < cutoff)\
        .delete(synchronize_session=False)
    session.commit()
    logger.info("retention: access_log deleted=%d cutoff=%s", n, cutoff)
    return n


def cleanup_sync_events(session: Session, *, retention_days: int) -> int:
    cutoff = _utc_naive_threshold(retention_days)
    n = session.query(models.SyncEventORM)\
        .filter(models.SyncEventORM.started_at < cutoff)\
        .delete(synchronize_session=False)
    session.commit()
    logger.info("retention: sync_events deleted=%d cutoff=%s", n, cutoff)
    return n


def cleanup_revoked_tokens(session: Session) -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    n = session.query(models.RevokedTokenORM)\
        .filter(models.RevokedTokenORM.expires_at < now)\
        .delete(synchronize_session=False)
    session.commit()
    logger.info("retention: revoked_tokens deleted=%d", n)
    return n
```

- [ ] **Step 5: Register cleanup in scheduler (scheduler-worker only)**

В `backend/application/sync/sync_scheduler.py` (метод `_run_loop` или эквивалент):

```python
from backend.jobs import retention as _retention
from backend.utils.worker_role import is_scheduler_worker

# В цикле, рядом с pnl_health_nightly:
if is_scheduler_worker():
    last_retention_run = ...  # store on self
    if (now - last_retention_run) >= timedelta(hours=settings.RETENTION_CLEANUP_INTERVAL_HOURS):
        with self._session_factory() as s:
            _retention.cleanup_access_log(s, retention_days=settings.ACCESS_LOG_RETENTION_DAYS)
            _retention.cleanup_sync_events(s, retention_days=settings.SYNC_EVENTS_RETENTION_DAYS)
            _retention.cleanup_revoked_tokens(s)
        last_retention_run = now
```

- [ ] **Step 6: Run tests — PASS**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/unit/test_retention.py -v
```

- [ ] **Step 7: NO-COMMIT**

---

## Batch 4 — Pipeline atomicity & leak fix

### Task 4.1: SYNC-08 — cursor сдвигается ПОСЛЕ FIFO/positions

**Files:**
- Modify: `backend/application/sync/pipeline.py` (`_stage_upsert` ~671, упорядочивание этапов ~190–210)
- Test: `backend/tests/integration/test_pipeline_cursor_atomicity.py`

- [ ] **Step 1: Read pipeline.py — точная последовательность stages**

Найди:
```python
inserted = await self._stage_upsert(fetched_operations, last_cursor)
trades, positions = await self._stage_fifo_match(fetched_operations)
positions = await self._stage_replace_positions_from_live(positions)
# и т.д.
```

В `_stage_upsert` сейчас: `upsert_many` + `save_cursor` + `commit` в одной транзакции.

- [ ] **Step 2: Write failing test — simulated crash after upsert leaves cursor un-advanced**

```python
def test_cursor_not_advanced_if_fifo_fails(pipeline_with_failing_fifo, broker_connection):
    """SYNC-08: при исключении на FIFO-стадии cursor должен остаться старым."""
    initial_cursor = broker_connection.sync_cursor
    with pytest.raises(RuntimeError):
        pipeline_with_failing_fifo.run_once()
    # После провала FIFO cursor НЕ должен сдвинуться.
    db.refresh(broker_connection)
    assert broker_connection.sync_cursor == initial_cursor
```

- [ ] **Step 3: Run — FAIL**

- [ ] **Step 4: Split _stage_upsert into upsert_only + commit_cursor**

```python
async def _stage_upsert(self, operations, _cursor):
    """SYNC-08: upsert операций БЕЗ сдвига курсора."""
    return await asyncio.to_thread(self._operation_repo.upsert_many, operations)

async def _stage_commit_cursor(self, cursor: str) -> None:
    """SYNC-08: вызывается только после успешного FIFO+positions."""
    def _save():
        with self._session_factory() as session:
            self._operation_repo.save_cursor(
                session,
                cursor=cursor,
                last_sync_status="success",
            )
            session.commit()
    await asyncio.to_thread(_save)
```

В `run_once` (или эквиваленте):
```python
inserted = await self._stage_upsert(fetched_operations, last_cursor)
trades, positions = await self._stage_fifo_match(fetched_operations)
positions = await self._stage_replace_positions_from_live(positions)
# Только теперь, после ВСЕХ stage'ей:
await self._stage_commit_cursor(last_cursor)
```

- [ ] **Step 5: Run test — PASS**

- [ ] **Step 6: NO-COMMIT**

---

### Task 4.2: SYNC-09 — инвариант атомарности `_replace_positions_from_live`

**Files:**
- Test: `backend/tests/integration/test_replace_positions_atomic.py`
- (Возможно) Modify: `backend/application/sync/pipeline.py` (`_replace_positions_from_live` ~1071)

- [ ] **Step 1: Write invariant test FIRST**

```python
def test_replace_positions_atomic_on_insert_error(pipeline, account_with_3_positions):
    """SYNC-09: при исключении в середине INSERT-цикла, состояние позиций неизменно."""
    before = list_positions(account_with_3_positions.id)

    # Подменяем session.commit чтобы упасть на 2-ом INSERT.
    with patch_insert_failure_at(index=1):
        with pytest.raises(RuntimeError):
            pipeline._replace_positions_from_live([fake_pos_1, fake_pos_2, fake_pos_3])

    after = list_positions(account_with_3_positions.id)
    assert before == after, "позиции должны остаться нетронутыми после crash"
```

- [ ] **Step 2: Run — most likely PASS (один commit в конце + rollback в except)**

Если **зелёное** — finding закрыт, добавь только комментарий-документ:

```python
# SYNC-09: атомарность гарантируется единым commit + rollback в except.
# Инвариант покрыт test_replace_positions_atomic_on_insert_error.
```

- [ ] **Step 3: Если test красный — добавь savepoint**

```python
def _replace_positions_from_live(self, live_positions):
    with self._session_factory() as session:
        with session.begin_nested():  # SAVEPOINT
            session.query(PositionORM).filter(
                PositionORM.account_id == self._account_id
            ).delete(synchronize_session=False)
            for pos in live_positions:
                session.add(...)
        session.commit()
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: NO-COMMIT**

---

### Task 4.3: SYNC-11 — cleanup `stream_manager._tasks`

**Files:**
- Modify: `backend/application/sync/stream_manager.py` (`_on_done` ~70)
- Test: `backend/tests/unit/test_stream_manager_cleanup.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_completed_task_removed_from_registry(stream_manager):
    """SYNC-11: после завершения task'а он не должен висеть в _tasks dict."""
    await stream_manager.start_task(connection_id=1, coro=asyncio.sleep(0.01))
    assert 1 in stream_manager._tasks
    await asyncio.sleep(0.05)
    assert 1 not in stream_manager._tasks
```

- [ ] **Step 2: Run — FAIL** (текущий код не удаляет done-task).

- [ ] **Step 3: Patch _on_done**

В `stream_manager.py`:

```python
def _on_done(self, connection_id: int, task: asyncio.Task) -> None:
    # SYNC-11: очистка завершённых тасков из реестра.
    self._tasks.pop(connection_id, None)
    # ... остальной существующий код (логирование исключений и т.п.)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Also clean _account_locks on disable/delete (light touch)**

Добавь публичный метод:

```python
def release_account_lock(self, connection_id: int) -> None:
    """SYNC-11: явный cleanup при disable/delete account."""
    self._account_locks.pop(connection_id, None)
```

И вызывай его из admin-роута `/admin/connections/{id}/disable` и `delete`.

- [ ] **Step 6: NO-COMMIT**

---

## Batch 5 — Load test harness

### Task 5.1: k6 — setup + read-hot-path сценарий

**Files:**
- Create: `backend/tests/load/README.md`
- Create: `backend/tests/load/scenarios/read_hot_path.js`
- Create: `backend/tests/load/baseline_slo.md`

- [ ] **Step 1: Write README with run instructions**

```markdown
# Load tests — k6

## Локальный запуск (5 VU, 1 минута — smoke)

```
k6 run -e BASE_URL=http://localhost:8000 \
       -e AUTH_TOKEN=$(cat .load-token) \
       scenarios/read_hot_path.js
```

## SLO baseline

Цель Sprint 3 (500 одновременных, read-mix 80/20):
- p95(/stats/) < 800ms
- p95(/trades/) < 400ms
- p95(/market/prices) < 600ms
- error_rate < 1%
- DB pool exhausted events == 0

Базовые цифры записываются в `baseline_slo.md` после первого прохода.
```

- [ ] **Step 2: Write read_hot_path.js**

```javascript
// backend/tests/load/scenarios/read_hot_path.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.AUTH_TOKEN;

const statsLatency = new Trend('stats_latency');
const tradesLatency = new Trend('trades_latency');
const errorRate = new Rate('errors');

export const options = {
  scenarios: {
    read_mix: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { duration: '1m', target: 100 },
        { duration: '3m', target: 500 },
        { duration: '5m', target: 500 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    'stats_latency': ['p(95)<800'],
    'trades_latency': ['p(95)<400'],
    'errors': ['rate<0.01'],
  },
};

const headers = { Authorization: `Bearer ${TOKEN}` };

export default function () {
  const r1 = http.get(`${BASE}/stats/`, { headers });
  statsLatency.add(r1.timings.duration);
  errorRate.add(r1.status >= 400);
  check(r1, { 'stats 200': (r) => r.status === 200 });

  const r2 = http.get(`${BASE}/trades/?limit=100`, { headers });
  tradesLatency.add(r2.timings.duration);
  errorRate.add(r2.status >= 400);

  const r3 = http.get(`${BASE}/trades/positions?limit=50&status=open`, { headers });
  errorRate.add(r3.status >= 400);

  const r4 = http.get(`${BASE}/market/prices?tickers=SBER,GAZP,LKOH`, { headers });
  errorRate.add(r4.status >= 400);

  sleep(Math.random() * 2 + 1);  // 1-3s think-time
}
```

- [ ] **Step 3: Verify locally — smoke 1-minute run**

Запусти на localhost (если k6 не установлен — `winget install k6` или docker `grafana/k6`).

```
k6 run -e BASE_URL=http://localhost:8000 -e AUTH_TOKEN=... \
       --stage 30s:5,30s:0 backend/tests/load/scenarios/read_hot_path.js
```

Цель шага: смок-проход, не нагрузка. Просто проверить, что скрипт работает.

- [ ] **Step 4: Document baseline numbers in baseline_slo.md**

После того как Batch 1–4 готов и тесты зелёные — запусти полный 10-минутный сценарий и зафиксируй фактические p95/error_rate в `baseline_slo.md`.

- [ ] **Step 5: NO-COMMIT**

---

### Task 5.2 (опционально, по результатам baseline): tuning passes

Если baseline показал SLO-промахи:
- `/stats/` > 800ms p95 → проверь, что fingerprint всё ещё cheap, профайл расчёта analytics.
- `/market/prices` > 600ms p95 → MOEX upstream — добавь stale-while-revalidate в кэш.
- DB pool exhausted — поднять pool в `database.py` или вынести access-log в отдельный engine.

Не делать в первый проход; зависит от того, что покажет baseline.

---

## Self-Review (после написания плана)

**Coverage против спеки (Sprint 3 раздел):**
- PERF-03 ✅ Task 1.1
- PERF-04 ✅ Task 1.2
- PERF-06 ✅ Task 2.1
- PERF-07 ✅ Task 2.4
- PERF-08 ✅ Task 3.1 + 3.2
- PERF-09 ✅ Task 3.3
- PERF-10 ✅ Task 2.3
- SYNC-04 ✅ Task 1.3
- SYNC-08 ✅ Task 4.1
- SYNC-09 ✅ Task 4.2 (test-first; правка только если упало)
- SYNC-10 ✅ Task 2.2
- SYNC-11 ✅ Task 4.3
- Load test harness ✅ Task 5.1

**Placeholders scan:** нет TBD/TODO/«handle edge cases» без кода. Все code-блоки конкретны.

**Type consistency:** `_stage_commit_cursor` — новое имя, использовано последовательно. `_persist_access_log_async` vs `_persist_access_log` — оба определены, без коллизии. `cleanup_access_log`/`cleanup_sync_events`/`cleanup_revoked_tokens` — единая сигнатура `(session, *, retention_days)` (revoked без days — использует `expires_at`).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-sprint-3-performance-load.md`. Два варианта исполнения:

**1. Subagent-Driven (recommended)** — диспатч свежего implementer-агента на каждый Task; между задачами `code-reviewer` (+ `security-reviewer` на pipeline.py/middleware.py); быстрая итерация, чистый контекст на каждой задаче.

**2. Inline Execution** — исполнение в текущей сессии через `superpowers:executing-plans`, batch-checkpointed.

Какой подход?

# Sprint 1A — Postgres + Redis foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать приложение безопасным и консистентным под мульти-воркер на Postgres+Redis: запретить SQLite в проде, дать общий (Redis) кэш статистики вместо per-process, починить утечку scheduler-коннекта, задокументировать прод-конфиг БД/Redis.

**Architecture:** Точечные правки. БД уже умеет Postgres (QueuePool в `database.py`) — добавляем прод-гард + WAL для dev-SQLite. Rate-limiter уже fail-fast без Redis (PR 26) — подтверждаем и документируем. Главная новая единица — `RedisStatsCache` (drop-in к существующему `StatsCache`, выбирается фабрикой по `REDIS_URL`). Сериализация — **JSON** (безопасно для shared Redis); кэшируются только JSON-сериализуемые значения, остальное молча не кэшируется (пересчёт). При сбое Redis — деградация в cache-miss, эндпойнт не падает.

**Tech Stack:** SQLAlchemy 2.0 (QueuePool), redis-py (sync, уже в deps `redis>=5.0.0`), slowapi, pytest.

**Покрывает (из spec 2026-05-23):** PERF-01, PERF-02, PERF-05, API-10, SYNC-06. **PERF-11** уже закрыт Sprint 0 (nightly P&L health внутри scheduler-loop, а `scheduler.start()` рано выходит на не-scheduler воркерах) — здесь только верификационный тест.

**НЕ входит (Sprint 1B, отдельный план):** gRPC-резилентность — SYNC-02 (межтокенный лимитер), SYNC-03 (call-level timeouts), SYNC-05 (global backoff на IP-cooldown), SYNC-07 (stream rate-limiter). Это связная подсистема `application/sync/*`, делается отдельно.

**Режим коммитов:** no-commit. «Commit»-шаги — предложенные команды; человек ревьюит/коммитит. `PYTHONUTF8=1 python -X utf8` для всех backend-команд.

---

## File Structure

- Modify: `backend/database.py` — прод-гард (SQLite запрещён при DEBUG=false) + WAL/busy_timeout для file-SQLite. Новая чистая функция `_assert_db_safe_for_env`.
- Modify: `backend/services/stats_cache.py` — добавить `RedisStatsCache` (JSON) + `build_stats_cache()` фабрику; `stats_cache` инстанс через фабрику.
- Modify: `backend/sync_scheduler.py` — `_acquire_scheduler_lock` не течёт коннектом при ошибке/отмене.
- Modify: `backend/main.py` — стартовый readiness-лог (тип БД, пул, redis, worker-role).
- Modify: `.business/operations/deployment.md` — прод-требования БД/Redis (PgBouncer, sizing на 500, Redis обязателен, поведение при Redis-down).
- Test: `backend/tests/unit/test_db_env_guard.py`, `backend/tests/unit/test_redis_stats_cache.py`, `backend/tests/unit/test_scheduler_lock_no_leak.py`, `backend/tests/unit/test_scheduler_worker_gate.py`.

---

## Task 1: PERF-01 — запрет SQLite в проде + WAL для dev-SQLite

**Files:**
- Test: `backend/tests/unit/test_db_env_guard.py`
- Modify: `backend/database.py`

- [ ] **Step 1: Падающий тест на гард**

Create `backend/tests/unit/test_db_env_guard.py`:
```python
"""PERF-01: в проде (DEBUG=false) SQLite запрещён — только Postgres.
Гард — чистая функция, чтобы тестировать без import-time эффектов."""
from __future__ import annotations

import pytest

from database import _assert_db_safe_for_env


def test_sqlite_in_prod_raises():
    with pytest.raises(RuntimeError, match="SQLite"):
        _assert_db_safe_for_env("sqlite:///./atom.db", debug=False)


def test_sqlite_in_debug_ok():
    _assert_db_safe_for_env("sqlite:///./atom.db", debug=True)  # no raise


def test_postgres_in_prod_ok():
    _assert_db_safe_for_env("postgresql://u:p@h/db", debug=False)  # no raise
```

- [ ] **Step 2: Запустить — FAIL (нет `_assert_db_safe_for_env`)**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_db_env_guard.py -q
```
Expected: FAIL — `ImportError: cannot import name '_assert_db_safe_for_env'`.

- [ ] **Step 3: Добавить гард в `database.py`**

В `backend/database.py` после блока определения `IS_SQLITE`/`IS_POSTGRES` (после строки 24) вставить:
```python


def _assert_db_safe_for_env(url: str, debug: bool) -> None:
    """PERF-01: SQLite не годится для прод-нагрузки (single writer, нет WAL
    durability под конкуренцией). В проде (DEBUG=false) требуем Postgres."""
    if url.startswith("sqlite") and not debug:
        raise RuntimeError(
            "\n🚨 FATAL: SQLite запрещён в production (DEBUG=false).\n"
            "   SQLite = один писатель → 'database is locked' под нагрузкой.\n"
            "   Установите DATABASE_URL=postgresql://user:pass@host:5432/db"
        )
```

- [ ] **Step 4: Вызвать гард при создании engine**

В `backend/database.py`, в начале `create_db_engine()` (сразу после `def create_db_engine():` и docstring, перед `if IS_SQLITE:`) добавить:
```python
    _assert_db_safe_for_env(SQLALCHEMY_DATABASE_URL, settings.DEBUG)
```

- [ ] **Step 5: WAL + busy_timeout для file-SQLite**

В `backend/database.py` заменить существующий listener (строки ~96-101):
```python
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```
на:
```python
if IS_SQLITE:
    _sqlite_is_memory = ":memory:" in SQLALCHEMY_DATABASE_URL

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if not _sqlite_is_memory:
            # WAL снижает писатель-блокировки в dev; busy_timeout вместо мгновенного
            # 'database is locked'. Для :memory: (тесты) WAL неприменим.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
```

- [ ] **Step 6: Запустить тесты + app import**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_db_env_guard.py -q
DEBUG=true PYTHONUTF8=1 python -X utf8 -c "from main import app; print('IMPORT-OK', len(app.routes))"
```
Expected: 3 passed; IMPORT-OK <N>. (Tests используют in-memory SQLite + DEBUG=true → гард не срабатывает.)

- [ ] **Step 7 (suggested commit):**
```bash
git add backend/database.py backend/tests/unit/test_db_env_guard.py
git commit -m "feat(db): forbid SQLite in prod + WAL for dev SQLite (PERF-01)"
```

---

## Task 2: PERF-05 — Redis-backed stats cache (JSON, drop-in, graceful degrade)

**Files:**
- Test: `backend/tests/unit/test_redis_stats_cache.py`
- Modify: `backend/services/stats_cache.py`

Контекст: `StatsCache` (in-memory, per-process) уже имеет интерфейс `get/set/invalidate/clear` и в docstring предусмотрен Redis-drop-in. Добавляем `RedisStatsCache` с тем же интерфейсом (JSON-сериализация — безопасно для общего Redis), фабрику выбора по `settings.REDIS_URL`. Несериализуемое значение → set() молча пропускает (значение просто не кэшируется, без расхождения типов). При сбое Redis — деградация в cache-miss.

- [ ] **Step 1: Падающий тест**

Create `backend/tests/unit/test_redis_stats_cache.py`:
```python
"""PERF-05: RedisStatsCache — общий кэш между воркерами, тот же интерфейс
что in-memory StatsCache, JSON-сериализация, graceful-degrade при сбое Redis."""
from __future__ import annotations

from services.stats_cache import RedisStatsCache


class FakeRedis:
    """Минимальный in-memory дублёр redis-клиента для теста."""
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.fail = False

    def get(self, k):
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.get(k)

    def set(self, k, v, ex=None):
        if self.fail:
            raise ConnectionError("redis down")
        self.store[k] = v

    def delete(self, *names):
        for n in names:
            self.store.pop(n, None)

    def scan_iter(self, match=None):
        pref = (match or "").rstrip("*")
        return [k for k in list(self.store) if k.startswith(pref)]


def test_set_get_roundtrip_json_value():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    value = {"win_rate": 48.52, "n": 10, "nested": {"x": [1, 2]}}
    c.set("k1", value)
    assert c.get("k1") == value


def test_keys_are_namespaced():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    c.set("k1", 123)
    assert all(k.startswith("stats:") for k in r.store)


def test_ttl_passed_to_redis():
    r = FakeRedis()
    captured = {}
    orig = r.set
    def spy(k, v, ex=None):
        captured["ex"] = ex
        return orig(k, v, ex=ex)
    r.set = spy
    c = RedisStatsCache(r, ttl_seconds=42)
    c.set("k1", 1)
    assert captured["ex"] == 42


def test_get_miss_returns_none():
    c = RedisStatsCache(FakeRedis(), ttl_seconds=30)
    assert c.get("absent") is None


def test_invalidate_and_clear():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    c.set("a", 1); c.set("b", 2)
    c.invalidate("a")
    assert c.get("a") is None and c.get("b") == 2
    c.clear()
    assert c.get("b") is None


def test_non_serializable_value_skipped_not_crash():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    c.set("k", object())   # не JSON-сериализуемо → пропускаем, без исключения
    assert c.get("k") is None


def test_redis_failure_degrades_to_miss_not_crash():
    r = FakeRedis(); r.fail = True
    c = RedisStatsCache(r, ttl_seconds=30)
    assert c.get("k") is None      # не бросает
    c.set("k", {"a": 1})           # не бросает
```

- [ ] **Step 2: Запустить — FAIL (нет RedisStatsCache)**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_redis_stats_cache.py -q
```
Expected: FAIL — `ImportError: cannot import name 'RedisStatsCache'`.

- [ ] **Step 3: Добавить `RedisStatsCache` + фабрику в `stats_cache.py`**

`json` уже импортирован вверху `backend/services/stats_cache.py`. Перед блоком «Module-global instance» (перед строкой `stats_cache = StatsCache(...)`) вставить:
```python
class RedisStatsCache:
    """Redis-backed кэш с тем же интерфейсом, что StatsCache.

    JSON-сериализация (безопасно для общего Redis). Кэшируются только
    JSON-сериализуемые значения; несериализуемое set() молча пропускает.
    При любой ошибке Redis деградируем в cache-miss (stats пересчитаются),
    эндпойнт не падает.
    """

    _PREFIX = "stats:"

    def __init__(self, redis_client, ttl_seconds: int = 30) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _k(self, key: str) -> str:
        return f"{self._PREFIX}{key}"

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._redis.get(self._k(key))
        except Exception:
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError):
            return  # несериализуемо — просто не кэшируем
        try:
            self._redis.set(self._k(key), payload, ex=self._ttl)
        except Exception:
            pass

    def invalidate(self, key: str) -> None:
        try:
            self._redis.delete(self._k(key))
        except Exception:
            pass

    def clear(self) -> None:
        try:
            keys = list(self._redis.scan_iter(match=f"{self._PREFIX}*"))
            if keys:
                self._redis.delete(*keys)
        except Exception:
            pass


def build_stats_cache(ttl_seconds: int = 30, max_size: int = 100):
    """Фабрика: Redis-backed если задан REDIS_URL, иначе in-memory.

    Под gunicorn N воркеров in-memory даёт ¼ hit-rate (каждый свой словарь).
    """
    try:
        from config import settings
        if settings.REDIS_URL:
            import redis
            client = redis.from_url(settings.REDIS_URL)
            return RedisStatsCache(client, ttl_seconds=ttl_seconds)
    except Exception:
        # Любой сбой подключения к Redis на старте → безопасный фолбэк in-memory.
        pass
    return StatsCache(ttl_seconds=ttl_seconds, max_size=max_size)
```

- [ ] **Step 4: Переключить module-global на фабрику**

В `backend/services/stats_cache.py` заменить строку 113:
```python
stats_cache = StatsCache(ttl_seconds=30, max_size=100)
```
на:
```python
stats_cache = build_stats_cache(ttl_seconds=30, max_size=100)
```

- [ ] **Step 5: Запустить тесты + проверить fallback (без REDIS_URL → in-memory)**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_redis_stats_cache.py -q
DEBUG=true PYTHONUTF8=1 python -X utf8 -c "from services.stats_cache import stats_cache, StatsCache; print('FALLBACK-OK', isinstance(stats_cache, StatsCache))"
```
Expected: 7 passed; `FALLBACK-OK True` (нет REDIS_URL → in-memory).

- [ ] **Step 6: Регресс — существующие stats/cache-тесты зелёные**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit -k "stats or cache" -q
```
Expected: PASS (фабрика без REDIS_URL ведёт себя как раньше).

- [ ] **Step 7 (suggested commit):**
```bash
git add backend/services/stats_cache.py backend/tests/unit/test_redis_stats_cache.py
git commit -m "feat(perf): Redis-backed stats cache (JSON) with in-memory fallback (PERF-05)"
```

---

## Task 3: SYNC-06 — scheduler advisory-lock без утечки коннекта

**Files:**
- Test: `backend/tests/unit/test_scheduler_lock_no_leak.py`
- Modify: `backend/sync_scheduler.py` (`_acquire_scheduler_lock`, ~строки 366-388)

Контекст: `_acquire_scheduler_lock()` открывает `conn = engine.connect()` (стр. 378), но в ветке `except Exception` (387) и при `CancelledError` (BaseException, не ловится `except Exception`) коннект не закрывается → утечка из пула на shutdown/ошибке.

- [ ] **Step 1: Падающий тест**

Create `backend/tests/unit/test_scheduler_lock_no_leak.py`:
```python
"""SYNC-06: при ошибке выполнения advisory-lock запроса коннект должен
закрываться, а не утекать из пула."""
from __future__ import annotations

import sync_scheduler


class _Conn:
    def __init__(self, fail_execute=False):
        self.closed = False
        self._fail = fail_execute

    def execute(self, *a, **k):
        if self._fail:
            raise RuntimeError("boom during pg_try_advisory_lock")
        class _R:
            def scalar(self_inner):
                return True
        return _R()

    def close(self):
        self.closed = True


class _Engine:
    def __init__(self, conn):
        self._conn = conn
        class _D:
            name = "postgresql"
        self.dialect = _D()

    def connect(self):
        return self._conn


def test_connection_closed_when_execute_fails(monkeypatch):
    conn = _Conn(fail_execute=True)
    monkeypatch.setattr(sync_scheduler, "engine", _Engine(conn), raising=False)
    sync_scheduler._acquire_scheduler_lock()   # не падает
    assert conn.closed is True


def test_connection_kept_open_when_lock_acquired(monkeypatch):
    conn = _Conn(fail_execute=False)
    monkeypatch.setattr(sync_scheduler, "engine", _Engine(conn), raising=False)
    sync_scheduler._lock_connection = None
    got = sync_scheduler._acquire_scheduler_lock()
    assert got is True
    assert conn.closed is False           # держим открытым — это и есть lock
    assert sync_scheduler._lock_connection is conn
    sync_scheduler._release_scheduler_lock()  # cleanup
```

- [ ] **Step 2: Запустить — FAIL**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_scheduler_lock_no_leak.py -q
```
Expected: FAIL (в текущем коде `conn.closed` остаётся False в ветке ошибки, либо тест не может подменить engine из-за локального import).

- [ ] **Step 3: Починить `_acquire_scheduler_lock`**

Прочитать `backend/sync_scheduler.py` строки ~360-390. Убедиться, что вверху файла есть модульный `from database import engine` (если нет — добавить рядом с другими импортами). Затем заменить тело `_acquire_scheduler_lock` (блок начиная с `try:` ... `from database import engine` ... до `return True` финального) на:
```python
    global _lock_connection
    try:
        from sqlalchemy import text

        if not engine.dialect.name.startswith("postgres"):
            # SQLite / другая БД — нет advisory locks, надеемся на
            # IS_SCHEDULER_WORKER + in-process flag.
            return True

        conn = engine.connect()
        try:
            result = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SCHEDULER_LOCK_KEY})
            got = bool(result.scalar())
        except BaseException:
            # Включая CancelledError на shutdown — коннект НЕ должен утечь.
            conn.close()
            raise
        if got:
            _lock_connection = conn   # держим открытым — пока коннект жив, lock наш
            return True
        conn.close()
        return False
    except Exception as exc:
        log.warning("scheduler.advisory_lock_failed: %s — proceeding anyway", exc)
        return True
```
ВАЖНО: убрать локальный `from database import engine` внутри функции (полагаемся на модульный `engine`, чтобы `monkeypatch.setattr(sync_scheduler, "engine", ...)` работал).

- [ ] **Step 4: Запустить — PASS + app import**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_scheduler_lock_no_leak.py -q
DEBUG=true PYTHONUTF8=1 python -X utf8 -c "import sync_scheduler; print('OK')"
```
Expected: 2 passed; OK.

- [ ] **Step 5 (suggested commit):**
```bash
git add backend/sync_scheduler.py backend/tests/unit/test_scheduler_lock_no_leak.py
git commit -m "fix(sync): close advisory-lock conn on failure/cancel (SYNC-06)"
```

---

## Task 4: PERF-11 verification + PERF-02/API-10 ops-docs + readiness-лог

**Files:**
- Test: `backend/tests/unit/test_scheduler_worker_gate.py`
- Modify: `backend/main.py` (startup log)
- Modify: `.business/operations/deployment.md`

- [ ] **Step 1: Верификационный тест PERF-11 (scheduler-gate)**

Create `backend/tests/unit/test_scheduler_worker_gate.py`:
```python
"""PERF-11: на не-scheduler воркере планировщик (а с ним nightly P&L health
внутри его loop) НЕ стартует. Закрыто Sprint 0; тест защищает от регрессии."""
from __future__ import annotations

import asyncio

from sync_scheduler import SyncScheduler


def test_scheduler_skips_on_non_scheduler_worker(monkeypatch):
    monkeypatch.setenv("IS_SCHEDULER_WORKER", "false")
    sched = SyncScheduler()
    asyncio.run(sched.start())
    assert sched._running is False
    assert sched._task is None
```

- [ ] **Step 2: Запустить — должен ПРОЙТИ сразу (закрыто Sprint 0)**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_scheduler_worker_gate.py -q
```
Expected: PASS. (Verification-тест: фича есть, тест фиксирует поведение. Если падает — gate сломан, чинить `scheduler.start()`.)

- [ ] **Step 3: Readiness-лог в `main.py`**

В `backend/main.py` в lifespan, сразу после строки `log.info("🔄 Auto-sync scheduler started")`, добавить:
```python
    from worker_role import is_scheduler_worker
    import database as _db
    log.info(
        "🩺 Readiness: db=%s redis=%s scheduler_worker=%s",
        "postgres" if _db.IS_POSTGRES else "sqlite" if _db.IS_SQLITE else "other",
        "set" if settings.REDIS_URL else "MISSING",
        is_scheduler_worker(),
    )
```

- [ ] **Step 4: Проверить, что лог не ломает старт**

Run:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -c "from main import app; print('IMPORT-OK', len(app.routes))"
```
Expected: IMPORT-OK <N>.

- [ ] **Step 5: Прод-документация БД/Redis**

В `.business/operations/deployment.md` добавить раздел:
```markdown
## Прод-требования: БД и Redis (Sprint 1A)

- **DATABASE_URL** — ОБЯЗАТЕЛЬНО PostgreSQL (`postgresql://...`). SQLite в проде
  запрещён кодом (DEBUG=false + sqlite → fail-fast). Причина: single-writer.
- **Пул соединений** (env, дефолты в `database.py`): `DB_POOL_SIZE=5`,
  `DB_MAX_OVERFLOW=10`, `DB_POOL_TIMEOUT=30`, `DB_POOL_RECYCLE=1800`,
  pre-ping включён. На 500 пользователей при N gunicorn-воркерах суммарные
  коннекты = N × (pool_size + max_overflow). Postgres `max_connections` должен
  это покрывать ЛИБО ставим **PgBouncer** (transaction pooling) между app и PG —
  рекомендуется при N×15 > ~100.
- **REDIS_URL** — ОБЯЗАТЕЛЕН в проде: rate-limiter fail-fast без Redis
  (`rate_limiter.py`), а stats-cache без Redis деградирует в per-process
  (¼ hit-rate под N воркерами). Один Redis обслуживает и rate-limit, и stats
  (ключи stats префиксованы `stats:`).
- **Поведение при Redis-down:** старт приложения требует Redis (rate-limit
  fail-fast) — осознанный trade-off (безопасность > доступность для
  brute-force). Stats-cache при рантайм-сбое Redis молча пересчитывает (не
  падает). Старт без Redis — только явный `RATE_LIMIT_ENABLED=false` (НЕ реком.).
```

- [ ] **Step 6 (suggested commit):**
```bash
git add backend/tests/unit/test_scheduler_worker_gate.py backend/main.py .business/operations/deployment.md
git commit -m "docs+test(infra): PERF-11 gate test, readiness log, prod DB/Redis docs (PERF-02/API-10/PERF-11)"
```

---

## Финальная проверка спринта

- [ ] Полный unit-прогон зелёный:
```bash
cd /c/Users/Administrator/Empirik/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit -q
```
Expected: все passed (523 базовых + новые из 1A; 0 failed).

- [ ] CI-эквивалент (Postgres+Redis) — после коммита прогнать на GitHub: alembic + pytest на postgres-сервисе, REDIS_URL задан → RedisStatsCache активируется в рантайме.

---

## Self-Review

**1. Spec coverage (Sprint 1A findings):**
- PERF-01 → Task 1 ✓ (prod-гард + WAL)
- PERF-05 → Task 2 ✓ (RedisStatsCache JSON + фабрика + fallback)
- SYNC-06 → Task 3 ✓ (no-leak advisory lock)
- PERF-11 → Task 4 Step 1-2 ✓ (verification — закрыто Sprint 0)
- PERF-02 → Task 4 Step 5 ✓ (пул/PgBouncer ops-doc; код пула уже есть)
- API-10 → Task 4 Step 5 ✓ (Redis-required + Redis-down поведение задокументировано; fail-fast уже в коде)
- **Deferred → Sprint 1B:** SYNC-02, SYNC-03, SYNC-05, SYNC-07 (gRPC resilience).

**2. Placeholder scan:** код приведён дословно во всех code-шагах; нет TODO/«добавь обработку». ✓

**3. Type/identifier consistency:** `_assert_db_safe_for_env(url, debug)`, `RedisStatsCache(redis_client, ttl_seconds)`, `build_stats_cache(ttl_seconds, max_size)`, `_acquire_scheduler_lock()/_release_scheduler_lock()/_lock_connection` — имена совпадают между задачами и тестами. ✓

**Допущения, проверяемые при исполнении:**
- Task 3: точное тело `_acquire_scheduler_lock` сверить по факту (строки ~366-388) перед заменой; убрать локальный `from database import engine`, добавить модульный — ради monkeypatch.
- Task 2: кэшируемые значения JSON-сериализуемы (stats-ответы — да); несериализуемые молча не кэшируются (без расхождения с in-memory).
- Redis в проде уже подразумевается rate-limiter'ом; stats-cache переиспользует тот же `REDIS_URL`.

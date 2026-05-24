# Sprint 1B — gRPC-резилентность (SYNC-02/03/05/07) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **NO-COMMIT MODE (standing для этой сессии):** реализуй правки + тесты до зелёного, но **НЕ выполняй `git add` / `git commit`**. Пользователь сам ревьюит diff и коммитит. Все «Commit» шаги ниже = no-op (оставлены для структуры).

> **Окружение:** backend без venv (Python 3.14 на dev, целевой CI/prod 3.11). Все backend-команды запускать `PYTHONUTF8=1 python -X utf8 ...` (Windows cp1251 ломает Unicode). На dev НЕТ Docker и НЕТ запущенного Redis — юнит-тесты обязаны проходить без Redis.

**Goal:** Сделать Tinkoff/T-Bank gRPC-слой безопасным под N gunicorn-воркеров: общий межпроцессный per-token rate-limit, call-level таймауты, глобальный backoff на IP-cooldown, корректный стрим-лимитер.

**Architecture:** Новый общий лимитер на `redis.asyncio` (уже в зависимостях) с атомарным Lua token-bucket; in-process token-bucket как degraded-фолбэк при отсутствии/сбое Redis (никогда не fail-open — лимитер деградирует «уже` до per-process N×, не до ∞). Глобальный IP-cooldown gate на Redis-ключе с TTL + per-process datetime-фолбэк, слой НАД per-connection `circuit_open_until`. SYNC-03 таймауты используют то, что `asyncio.TimeoutError == builtins.TimeoutError` на 3.11+ и `error_mapper` уже маппит `TimeoutError → BrokerUnavailable` (retryable). SYNC-07 — сузить захват лимитера до открытия стрима (1 токен/стрим, не на весь lifetime).

**Tech Stack:** Python (asyncio), redis>=5.0.0 (`redis.asyncio`, `register_script`/EVALSHA), tenacity (есть), pytest. **Никаких новых зависимостей** (отвергнут `limits.aio`+`coredis` — async-Redis-бэкенд `limits` требует `coredis`, которого нет и который рискует не встать на 3.14).

**Решения зафиксированы** (senior-software-engineer, 2 раунда):
- SYNC-02: build на `redis.asyncio` + tiny Lua token-bucket. НЕ покупать `limits` (нужен coredis).
- Алгоритм: token-bucket `capacity = rate`, `refill = rate/period` — **паритет с текущим `aiolimiter`** (тот же burst-профиль), но shared cross-worker. Боундари-даблинг существует и сейчас, это НЕ репортнутый баг; репортнутый баг — N× от per-process. Сужение burst (`capacity < rate`) — будущая опция если cooldown'ы T-Bank продолжатся.
- Фолбэк лимитера: in-process token-bucket (degraded N×rate, ограниченный), warn при старте. **Не fail-open.**
- SYNC-05 gate: Redis-ключ с TTL (escalating backoff) + per-process datetime fallback; **fail-open допустим** (gate — оптимизация против шторма, не последняя линия). Триггер — кросс-коннекшн корреляция (≥ N различных connection_id поймали RateLimitExceeded за один прогон). Слой НАД per-connection circuit; во время global cooldown per-connection circuit'ы НЕ трогаем.
- SYNC-03 в scope этого спринта; `max_wait` лимитера = одно-попытка-дедлайн (не бюджет всей tenacity-цепи).

---

## File Structure

| Файл | Ответственность | Действие |
|---|---|---|
| `backend/config.py` | 5 новых settings (limiter max_wait, grpc timeout, ip-cooldown base/max/threshold) | Modify (~line 325) |
| `backend/adapters/tinkoff/grpc_rate_limiter.py` | `TokenBucketBackend` protocol; `InProcessTokenBucket`; `RedisTokenBucket` (Lua); `SharedRateLimiter` (`async with` drop-in); `build_token_bucket_backend()` factory | Create |
| `backend/adapters/tinkoff/client_factory.py` | Заменить per-token aiolimiter dicts на shared backend; `RateLimitedServices.limiter`/`.broker_report_limiter` = `SharedRateLimiter` | Modify |
| `backend/adapters/tinkoff/operations_client.py` | SYNC-03: `_guarded()` helper оборачивает каждый RPC в `asyncio.wait_for` | Modify |
| `backend/adapters/tinkoff/operations_stream_client.py` | SYNC-07: захват лимитера только на открытие стрима | Modify (`_stream_once`, ~line 121-137) |
| `backend/application/sync/ip_cooldown_gate.py` | `IpCooldownGate` (is_open/open/clear, Redis+proc fallback); `build_ip_cooldown_gate()` | Create |
| `backend/application/sync/orchestrator.py` | Inject gate; `is_open()` перед fan-out; кросс-коннекшн trip/clear; RateLimitExceeded-хэндлер | Modify |
| `backend/.business/operations/deployment.md` | Worker-модель + новые env-переменные | Modify |
| `backend/tests/unit/test_grpc_rate_limiter.py` | InProcess bucket math, SharedRateLimiter блокировка+max_wait→RateLimitExceeded, фолбэк-селекция, Redis-down degrade | Create |
| `backend/tests/unit/test_operations_client_timeout.py` | SYNC-03: зависший RPC → BrokerUnavailable за timeout | Create |
| `backend/tests/unit/test_operations_stream_limiter.py` | SYNC-07: ровно 1 acquire на стрим независимо от N событий | Create |
| `backend/tests/unit/test_ip_cooldown_gate.py` | open/is_open/escalation, proc-fallback, redis-down | Create |
| `backend/tests/integration/test_orchestrator.py` | Gate is_open → весь прогон skipped; ≥threshold коннекшнов → gate открыт | Modify |
| `backend/tests/integration/test_grpc_rate_limiter_redis.py` | Lua token-bucket против реального Redis (skip если REDIS_TEST_URL не задан) | Create |

---

## Task 1: Config settings

**Files:**
- Modify: `backend/config.py` (после строки ~325, в блоке BROKER SYNC V2 / TINKOFF)
- Test: `backend/tests/unit/test_config_sync_resilience.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_config_sync_resilience.py
"""Sprint 1B: новые resilience-настройки имеют разумные дефолты и читаются из env."""
from __future__ import annotations

import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config
    return importlib.reload(config).settings


def test_defaults(monkeypatch):
    s = _reload_config(monkeypatch)
    assert s.TINKOFF_LIMITER_MAX_WAIT_SECONDS == 60.0
    assert s.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS == 30.0
    assert s.TINKOFF_IP_COOLDOWN_BASE_SECONDS == 60
    assert s.TINKOFF_IP_COOLDOWN_MAX_SECONDS == 600
    assert s.TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS == 2


def test_env_override(monkeypatch):
    s = _reload_config(
        monkeypatch,
        TINKOFF_GRPC_CALL_TIMEOUT_SECONDS="12.5",
        TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS="5",
    )
    assert s.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS == 12.5
    assert s.TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_config_sync_resilience.py -v`
Expected: FAIL — `AttributeError: ... TINKOFF_LIMITER_MAX_WAIT_SECONDS`.

- [ ] **Step 3: Add settings**

В `backend/config.py`, сразу после `TINKOFF_BROKER_REPORT_RATE_LIMIT_PER_MIN` (строка ~325), добавить:

```python
    # ==================== SYNC RESILIENCE (Sprint 1B) ====================
    # SYNC-02: общий per-token rate-limit живёт в Redis (если REDIS_URL задан),
    # иначе in-process (degraded — каждый воркер свой бакет).
    # SYNC-03: максимум, сколько одна попытка RPC ждёт токен лимитера, прежде
    # чем поднять RateLimitExceeded (одна попытка, НЕ бюджет всей tenacity-цепи).
    TINKOFF_LIMITER_MAX_WAIT_SECONDS: float = float(
        os.getenv("TINKOFF_LIMITER_MAX_WAIT_SECONDS", "60")
    )
    # SYNC-03: call-level deadline на каждый gRPC RPC. Зависший вызов иначе
    # держит лимитер-токен + семафор бесконечно. По таймауту → BrokerUnavailable
    # (retryable; error_mapper маппит TimeoutError).
    TINKOFF_GRPC_CALL_TIMEOUT_SECONDS: float = float(
        os.getenv("TINKOFF_GRPC_CALL_TIMEOUT_SECONDS", "30")
    )
    # SYNC-05: глобальный IP-cooldown gate. При обнаружении IP-уровневого
    # RESOURCE_EXHAUSTED оркестратор открывает gate с эскалирующим backoff,
    # чтобы retry-шторм не продлевал outage.
    TINKOFF_IP_COOLDOWN_BASE_SECONDS: int = int(
        os.getenv("TINKOFF_IP_COOLDOWN_BASE_SECONDS", "60")
    )
    TINKOFF_IP_COOLDOWN_MAX_SECONDS: int = int(
        os.getenv("TINKOFF_IP_COOLDOWN_MAX_SECONDS", "600")
    )
    # Сколько РАЗНЫХ connection_id должны словить RateLimitExceeded за один
    # прогон, чтобы счесть это IP-уровневым cooldown (а не throttle одного
    # токена). 1 токен НЕ открывает global gate — для него per-connection circuit.
    TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS: int = int(
        os.getenv("TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS", "2")
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_config_sync_resilience.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 2: Shared rate limiter (token-bucket backend + async-with adapter)

**Files:**
- Create: `backend/adapters/tinkoff/grpc_rate_limiter.py`
- Test: `backend/tests/unit/test_grpc_rate_limiter.py`

Это ядро SYNC-02. Делаем в TDD: сначала in-process backend (без Redis), потом адаптер `async with` + max_wait, потом factory. Redis-бэкенд пишем кодом сразу (Lua), но его атомарность проверяем отдельным integration-тестом против реального Redis (Task 9, skip без REDIS_TEST_URL).

- [ ] **Step 1: Write the failing test (in-process bucket + adapter)**

```python
# backend/tests/unit/test_grpc_rate_limiter.py
"""SYNC-02/03: общий token-bucket лимитер.

InProcessTokenBucket — точная Python-копия Lua-алгоритма (degraded-фолбэк).
SharedRateLimiter — `async with`-обёртка, drop-in для aiolimiter.AsyncLimiter,
с max_wait → RateLimitExceeded.
"""
from __future__ import annotations

import asyncio

import pytest

from adapters.tinkoff.grpc_rate_limiter import (
    InProcessTokenBucket,
    SharedRateLimiter,
    build_token_bucket_backend,
)
from domain.exceptions import RateLimitExceeded


def test_inprocess_bucket_allows_up_to_capacity_then_blocks():
    # capacity=rate=3, refill=3/sec → первые 3 acquire мгновенны (retry=0),
    # 4-й возвращает положительный retry_after.
    clock = {"t": 1000.0}
    b = InProcessTokenBucket(now_fn=lambda: clock["t"])
    waits = [b.try_acquire("k", rate=3, period=1) for _ in range(3)]
    assert waits == [0.0, 0.0, 0.0]
    w = b.try_acquire("k", rate=3, period=1)
    assert w > 0.0


def test_inprocess_bucket_refills_over_time():
    clock = {"t": 1000.0}
    b = InProcessTokenBucket(now_fn=lambda: clock["t"])
    for _ in range(3):
        b.try_acquire("k", rate=3, period=1)
    assert b.try_acquire("k", rate=3, period=1) > 0.0  # пусто
    clock["t"] += 1.0  # прошла секунда → +3 токена
    assert b.try_acquire("k", rate=3, period=1) == 0.0


def test_inprocess_keys_isolated():
    b = InProcessTokenBucket()
    assert b.try_acquire("a", rate=1, period=60) == 0.0
    assert b.try_acquire("b", rate=1, period=60) == 0.0  # другой ключ — свой бакет


@pytest.mark.asyncio
async def test_shared_limiter_async_with_blocks_until_token():
    # rate=2/sec; 3-й вход должен подождать ~0.5с и пройти.
    backend = InProcessTokenBucket()
    lim = SharedRateLimiter(backend, key="k", rate=2, period=1, max_wait=5.0)
    async with lim:
        pass
    async with lim:
        pass
    loop = asyncio.get_event_loop()
    start = loop.time()
    async with lim:
        pass
    assert loop.time() - start >= 0.3  # ждал refill, не прошёл мгновенно


@pytest.mark.asyncio
async def test_shared_limiter_raises_when_exceeds_max_wait():
    backend = InProcessTokenBucket()
    # rate=1/60s, max_wait крошечный → 2-й вход не дождётся токена.
    lim = SharedRateLimiter(backend, key="k", rate=1, period=60, max_wait=0.05)
    async with lim:
        pass
    with pytest.raises(RateLimitExceeded):
        async with lim:
            pass


def test_factory_returns_inprocess_when_no_redis(monkeypatch):
    monkeypatch.setattr("adapters.tinkoff.grpc_rate_limiter.settings.REDIS_URL", "", raising=False)
    backend = build_token_bucket_backend()
    assert isinstance(backend, InProcessTokenBucket)
```

> Примечание: проект уже гоняет async-тесты (см. существующий `tests/unit/`); если `pytest-asyncio` режим не `auto`, добавить `@pytest.mark.asyncio`. Проверь как помечены другие async-тесты в репо и следуй тому же стилю (anyio/asyncio).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_grpc_rate_limiter.py -v`
Expected: FAIL — модуль `grpc_rate_limiter` не существует.

- [ ] **Step 3: Implement `grpc_rate_limiter.py`**

```python
# backend/adapters/tinkoff/grpc_rate_limiter.py
"""SYNC-02/03: общий (cross-worker) per-token rate-limiter для T-Bank gRPC.

Проблема: per-process `aiolimiter` под N gunicorn-воркерами даёт N независимых
бакетов на токен → эффективный лимит = N × 150/min, что пробивает потолок
T-Bank 200/min и ведёт к IP-cooldown.

Решение: token-bucket, состояние которого живёт в Redis (atomic Lua, общий для
всех воркеров). Алгоритм — token-bucket с `capacity = rate`, `refill = rate/period`,
что воспроизводит burst-профиль прежнего `aiolimiter`, но shared.

Фолбэк: при отсутствии/сбое Redis — in-process token-bucket. Это деградирует
до прежнего N×rate (ограниченно), но НИКОГДА не fail-open (без лимита вообще),
потому что для rate-лимитера ∞ = бан, а N×rate — восстановимо.

`SharedRateLimiter` — drop-in для `aiolimiter.AsyncLimiter`: вызывающий код
делает `async with services.limiter:` без изменений (operations_client.py).
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Callable, Optional, Protocol

from config import settings
from domain.exceptions import RateLimitExceeded
from logger import get_logger

log = get_logger("tinkoff.grpc_rate_limiter")


def token_key(token: str, *, kind: str) -> str:
    """Стабильный ключ бакета без утечки токена (sha256, не сам токен)."""
    digest = hashlib.sha256(token.encode()).hexdigest()[:32]
    return f"{kind}:{digest}"


class TokenBucketBackend(Protocol):
    async def acquire(self, key: str, *, rate: int, period: int) -> float:
        """Неблокирующая попытка: 0.0 если токен взят сейчас, иначе секунды
        до следующего шанса (retry_after)."""
        ...


class InProcessTokenBucket:
    """Per-process token-bucket. Состояние в dict — общий для токенов В ОДНОМ
    воркере. Используется как degraded-фолбэк и как тест-бэкенд (без Redis).

    `now_fn` инъектируется для детерминированных тестов.
    """

    def __init__(self, now_fn: Callable[[], float] = time.monotonic) -> None:
        self._now = now_fn
        self._state: dict[str, tuple[float, float]] = {}  # key -> (tokens, ts)

    def try_acquire(self, key: str, *, rate: int, period: int) -> float:
        """Синхронная token-bucket попытка (без await — атомарна в asyncio)."""
        now = self._now()
        capacity = float(rate)
        refill = rate / period  # токенов в секунду
        tokens, ts = self._state.get(key, (capacity, now))
        tokens = min(capacity, tokens + (now - ts) * refill)
        if tokens >= 1.0:
            self._state[key] = (tokens - 1.0, now)
            return 0.0
        self._state[key] = (tokens, now)
        return (1.0 - tokens) / refill

    async def acquire(self, key: str, *, rate: int, period: int) -> float:
        return self.try_acquire(key, rate=rate, period=period)


# Atomic token-bucket в Redis. redis.call('TIME') даёт общие часы для всех
# воркеров (без clock-skew). Возвращает retry_after как строку (Lua float→int
# теряет дробь, поэтому tostring).
_LUA_TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
tokens = math.min(capacity, tokens + (now - ts) * refill)
local retry = 0.0
if tokens >= 1.0 then
  tokens = tokens - 1.0
else
  retry = (1.0 - tokens) / refill
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], ttl)
return tostring(retry)
"""


class RedisTokenBucket:
    """Cross-worker token-bucket на redis.asyncio + atomic Lua.

    При ЛЮБОЙ ошибке Redis в рантайме — деградируем на in-process бакет
    (не fail-open). Это конвертирует Redis-сбой в «N×rate per worker», а не
    «без лимита».
    """

    _PREFIX = "tinkoff:rl:"

    def __init__(self, redis_client, *, fallback: InProcessTokenBucket) -> None:
        self._redis = redis_client
        self._script = redis_client.register_script(_LUA_TOKEN_BUCKET)
        self._fallback = fallback

    async def acquire(self, key: str, *, rate: int, period: int) -> float:
        full_key = f"{self._PREFIX}{key}"
        capacity = float(rate)
        refill = rate / period
        ttl = max(period * 2, 2)
        try:
            raw = await self._script(keys=[full_key], args=[capacity, refill, ttl])
        except Exception as exc:  # Redis down/timeout → degrade, не падаем
            log.warning("grpc_rate_limiter: Redis acquire упал (%s) — in-process фолбэк", exc)
            return self._fallback.try_acquire(key, rate=rate, period=period)
        if isinstance(raw, bytes):
            raw = raw.decode()
        return float(raw)


class SharedRateLimiter:
    """`async with`-обёртка над backend — drop-in для aiolimiter.AsyncLimiter.

    На __aenter__ блокируется (paced sleep по retry_after от backend) пока не
    возьмёт токен ИЛИ суммарное ожидание не превысит max_wait → RateLimitExceeded
    (retryable, поднимется в tenacity/orchestrator). __aexit__ — no-op
    (leaky/token-bucket не «освобождает» на выходе).
    """

    def __init__(
        self,
        backend: TokenBucketBackend,
        *,
        key: str,
        rate: int,
        period: int,
        max_wait: float,
    ) -> None:
        self._backend = backend
        self._key = key
        self._rate = rate
        self._period = period
        self._max_wait = max_wait

    async def __aenter__(self) -> "SharedRateLimiter":
        waited = 0.0
        while True:
            retry_after = await self._backend.acquire(
                self._key, rate=self._rate, period=self._period
            )
            if retry_after <= 0.0:
                return self
            if waited + retry_after > self._max_wait:
                raise RateLimitExceeded(
                    message=(
                        f"rate limiter wait>{self._max_wait}s for {self._key}"
                    ),
                    code="LIMITER_MAX_WAIT",
                )
            # Спим не дольше остатка max_wait; маленький cap чтобы перепроверить
            # бакет (другой воркер мог влить токены).
            sleep_s = min(retry_after, self._max_wait - waited, 1.0)
            await asyncio.sleep(sleep_s)
            waited += sleep_s

    async def __aexit__(self, *exc) -> None:
        return None


def build_token_bucket_backend() -> TokenBucketBackend:
    """Factory: Redis-backed если задан REDIS_URL, иначе in-process.

    Зеркалит services.stats_cache.build_stats_cache: при сбое инициализации
    Redis — warn + in-process (degraded), не падаем на старте.
    """
    fallback = InProcessTokenBucket()
    if not settings.REDIS_URL:
        return fallback
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL)
        return RedisTokenBucket(client, fallback=fallback)
    except Exception as exc:
        log.warning(
            "grpc_rate_limiter: REDIS_URL задан, но init упал (%s) — in-process (degraded N×rate)",
            exc,
        )
        return fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_grpc_rate_limiter.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 3: Wire client_factory to the shared limiter

**Files:**
- Modify: `backend/adapters/tinkoff/client_factory.py`
- Test: `backend/tests/unit/test_grpc_rate_limiter.py` (добавить кейс)

Цель: `RateLimitedServices.limiter` и `.broker_report_limiter` становятся `SharedRateLimiter` поверх ОДНОГО backend на процесс. Per-token dicts (`_limiters`, `_broker_report_limiters`) удаляются — `SharedRateLimiter` stateless (состояние в backend/Redis), значит утечки per-token больше нет. **Call-sites в operations_client.py не меняются** (контракт `async with` сохранён).

- [ ] **Step 1: Write the failing test**

Добавить в `backend/tests/unit/test_grpc_rate_limiter.py`:

```python
def test_factory_builds_distinct_limiters_per_kind():
    from adapters.tinkoff.client_factory import TinkoffClientFactory

    f = TinkoffClientFactory()
    ops = f._limiter_for("tok-A", kind="ops")
    rep = f._limiter_for("tok-A", kind="broker_report")
    assert isinstance(ops, SharedRateLimiter)
    assert isinstance(rep, SharedRateLimiter)
    # разные kind → разные ключи (раздельные бакеты)
    assert ops._key != rep._key
    # broker_report лимит жёстче основного
    assert rep._rate < ops._rate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_grpc_rate_limiter.py::test_factory_builds_distinct_limiters_per_kind -v`
Expected: FAIL — `TinkoffClientFactory` не имеет `_limiter_for`.

- [ ] **Step 3: Modify client_factory.py**

(а) Удалить импорт `from aiolimiter import AsyncLimiter` (строка 37) — больше не нужен в этом модуле.

(б) Добавить импорт:
```python
from adapters.tinkoff.grpc_rate_limiter import (
    SharedRateLimiter,
    build_token_bucket_backend,
    token_key,
)
```

(в) В `RateLimitedServices.__init__` тип `limiter`/`broker_report_limiter` теперь `SharedRateLimiter` (поведенчески — drop-in; докстринг/коммент обновить, `__slots__` без изменений). Сигнатура `__init__` без изменений.

(г) Заменить `TinkoffClientFactory.__init__` и `_get_limiter`/`_get_broker_report_limiter`:

```python
    def __init__(self) -> None:
        # SYNC-02: ОДИН общий backend на процесс. SharedRateLimiter'ы stateless
        # (состояние в backend/Redis), поэтому per-token dict больше не нужен —
        # нет утечки лимитеров на токен.
        self._backend = build_token_bucket_backend()

    def _limiter_for(self, token: str, *, kind: str) -> SharedRateLimiter:
        """SharedRateLimiter для (token, kind). kind ∈ {'ops','broker_report'}."""
        if kind == "broker_report":
            rate = settings.TINKOFF_BROKER_REPORT_RATE_LIMIT_PER_MIN
        else:
            rate = settings.TINKOFF_RATE_LIMIT_PER_MIN
        return SharedRateLimiter(
            self._backend,
            key=token_key(token, kind=kind),
            rate=rate,
            period=60,
            max_wait=settings.TINKOFF_LIMITER_MAX_WAIT_SECONDS,
        )
```

(д) В `async_client` заменить получение лимитеров:
```python
        limiter = self._limiter_for(token, kind="ops")
        broker_report_limiter = self._limiter_for(token, kind="broker_report")
```
(остальное тело `async_client` без изменений).

- [ ] **Step 4: Run tests**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_grpc_rate_limiter.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Regression — operations_client тесты не сломались (call-sites не менялись)**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_resilience.py tests/integration/test_orchestrator.py -v`
Expected: PASS (или те же результаты, что до правки — никаких новых падений из-за лимитера).

- [ ] **Step 6: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 4: SYNC-03 — gRPC call-level timeouts

**Files:**
- Modify: `backend/adapters/tinkoff/operations_client.py`
- Test: `backend/tests/unit/test_operations_client_timeout.py`

Зависший RPC держит лимитер-токен + семафор бесконечно. Оборачиваем каждый RPC в `asyncio.wait_for(..., timeout=settings.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS)`. `asyncio.TimeoutError == builtins.TimeoutError` на 3.11+, а `error_mapper.wrap_sdk_errors` уже маппит `TimeoutError → BrokerUnavailable` (retryable) — таймаут пойдёт по штатному retry-пути.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_operations_client_timeout.py
"""SYNC-03: зависший gRPC RPC обрывается call-level таймаутом и поднимается
как BrokerUnavailable (retryable), не вешает лимитер/семафор навсегда."""
from __future__ import annotations

import asyncio

import pytest

from adapters.tinkoff.operations_client import TinkoffOperationsClient
from domain.exceptions import BrokerUnavailable


class _NoopLimiter:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


class _HangingOps:
    async def get_portfolio(self, account_id):
        await asyncio.sleep(60)  # «зависает»


class _Services:
    def __init__(self):
        self.limiter = _NoopLimiter()
        self.broker_report_limiter = _NoopLimiter()
        self.operations = _HangingOps()


@pytest.mark.asyncio
async def test_hanging_rpc_times_out_as_broker_unavailable(monkeypatch):
    monkeypatch.setattr(
        "adapters.tinkoff.operations_client.settings.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS",
        0.05,
        raising=False,
    )
    # tenacity ретраит BrokerUnavailable 5x — урезаем до 1 попытки для скорости.
    monkeypatch.setattr(
        "adapters.tinkoff.operations_client._retry_policy",
        lambda: __import__("tenacity").AsyncRetrying(
            stop=__import__("tenacity").stop_after_attempt(1), reraise=True
        ),
    )
    client = TinkoffOperationsClient(_Services())
    with pytest.raises(BrokerUnavailable):
        await asyncio.wait_for(client.get_portfolio_raw("acc"), timeout=2.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_operations_client_timeout.py -v`
Expected: FAIL — без таймаута тест сам упрётся в outer `wait_for(2.0)` → не `BrokerUnavailable`.

- [ ] **Step 3: Add `_guarded` helper и обернуть все RPC**

В `backend/adapters/tinkoff/operations_client.py`:

(а) Добавить `from config import settings` (если ещё нет — проверить импорты вверху файла).

(б) Добавить приватный helper в класс `TinkoffOperationsClient` (рядом с `__init__`):

```python
    async def _guarded(self, limiter, coro):
        """SYNC-01 (limiter) + SYNC-03 (call deadline) обёртка одного RPC.

        Лимитер-токен берётся на КАЖДЫЙ RPC; сам вызов ограничен по времени
        (зависший RPC иначе держит токен/семафор бесконечно). asyncio.TimeoutError
        == TimeoutError на 3.11+; wrap_sdk_errors маппит его → BrokerUnavailable.
        """
        async with limiter:
            with wrap_sdk_errors():
                return await asyncio.wait_for(
                    coro, settings.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS
                )
```

(в) Переписать каждый `_call()` через `_guarded`. Пример для `fetch_operations_cursor` (строки ~109-115):

```python
        async def _call():
            return await self._guarded(
                self._svc.limiter,
                self._svc.operations.get_operations_by_cursor(request),
            )
```

Аналогично заменить в:
- `get_portfolio_raw` (~173-177): `self._svc.operations.get_portfolio(account_id=account_id)`
- `get_positions_raw` (~185-189): `self._svc.operations.get_positions(account_id=account_id)`
- `generate_broker_report._call` (~234-240): limiter = `self._svc.broker_report_limiter`, coro = `self._svc.operations.get_broker_report(generate_broker_report_request=request)`
- `fetch_broker_report_page._call` (~292-298): limiter = `self._svc.broker_report_limiter`, coro = `self._svc.operations.get_broker_report(get_broker_report_request=request)`
- `get_dividends_foreign_issuer._call` (~463-467): `self._svc.operations.get_dividends_foreign_issuer(request)`

Во всех случаях тело `_call` сводится к одному `return await self._guarded(<limiter>, <coro>)`. Существующая обёртка `async with ...limiter: with wrap_sdk_errors(): return await ...` удаляется (она теперь внутри `_guarded`).

> ВНИМАНИЕ: НЕ оборачивать `_guarded` сам в ещё один `wrap_sdk_errors` — он уже внутри. И НЕ применять `_guarded` к стрим-клиенту (Task 5 — у стримов своя семантика).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_operations_client_timeout.py -v`
Expected: PASS.

- [ ] **Step 5: Regression**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_resilience.py tests/unit/test_error_mapper.py -v`
Expected: PASS (без новых падений).

- [ ] **Step 6: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 5: SYNC-07 — stream limiter scope

**Files:**
- Modify: `backend/adapters/tinkoff/operations_stream_client.py` (`_stream_once`, ~121-137)
- Test: `backend/tests/unit/test_operations_stream_limiter.py`

Сейчас `async with self._svc.limiter:` оборачивает ВЕСЬ `async for response in stream` — на shared (Redis) лимитере это «пинит» поведение на весь lifetime стрима. Нужно: взять ровно ОДИН токен на открытие стрима, дальше читать события вне лимитер-контекста (1 токен/стрим сохраняется, но не держится часами).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_operations_stream_limiter.py
"""SYNC-07: лимитер захватывается ровно 1 раз на открытие стрима, не на каждое
событие и не на весь lifetime."""
from __future__ import annotations

import pytest

from adapters.tinkoff.operations_stream_client import TinkoffOperationsStreamClient


class _CountingLimiter:
    def __init__(self): self.entered = 0
    async def __aenter__(self): self.entered += 1; return self
    async def __aexit__(self, *a): return None


class _FakeStream:
    """Async-iterator из N фейковых событий, каждое с .operation=None
    (extract вернёт None → не маппим домен, нам важен только счётчик limiter)."""
    def __init__(self, n): self._items = [object() for _ in range(n)]
    def __aiter__(self): return self
    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class _OpsStream:
    def __init__(self, n): self._n = n
    def operations_stream(self, request): return _FakeStream(self._n)


class _Services:
    def __init__(self, n):
        self.limiter = _CountingLimiter()
        self.operations_stream = _OpsStream(n)


@pytest.mark.asyncio
async def test_one_limiter_acquire_per_stream_regardless_of_events():
    svc = _Services(n=25)
    client = TinkoffOperationsStreamClient(svc)
    got = [op async for op in client.stream_operations("acc", max_reconnect_attempts=1)]
    assert svc.limiter.entered == 1  # 1 токен на стрим, не 25
    assert got == []  # все события .operation=None → ничего не сэмитили
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_operations_stream_limiter.py -v`
Expected: текущий код держит `async with limiter` вокруг всего цикла → `entered == 1` уже может пройти. **Если тест проходит на старом коде** — переписать ассерт на проверку, что limiter-контекст ВЫШЕЛ до конца чтения (см. ниже усиленный вариант), иначе фиксируем поведение регрессионным тестом и идём к Step 3 для приведения семантики к «acquire только на open». Усиленный тест:

```python
class _CountingLimiter:
    def __init__(self): self.entered = 0; self.exited = 0; self.open_at_exit = None
    async def __aenter__(self): self.entered += 1; return self
    async def __aexit__(self, *a): self.exited += 1; return None
```
И в `_FakeStream.__anext__` при отдаче ПЕРВОГО элемента ассертить, что `limiter.exited == 1` (контекст уже закрыт к началу чтения). На старом коде `exited == 0` во время чтения → FAIL.

- [ ] **Step 3: Modify `_stream_once`**

Заменить тело (`backend/adapters/tinkoff/operations_stream_client.py`, ~125-137):

```python
    async def _stream_once(
        self, broker_account_id: str
    ) -> AsyncIterator[Operation]:
        """Один цикл стрима. SYNC-07: лимитер-токен берётся ТОЛЬКО на открытие
        стрима; долгоживущий read-loop идёт вне лимитер-контекста (иначе на
        shared/Redis лимитере держали бы токен весь lifetime стрима)."""
        from t_tech.invest.schemas import OperationsStreamRequest

        request = OperationsStreamRequest(accounts=[broker_account_id])
        with wrap_sdk_errors():
            # 1 токен на открытие стрима — контекст закрывается сразу.
            async with self._svc.limiter:
                stream = self._svc.operations_stream.operations_stream(request)
            async for response in stream:
                op_proto = self._extract_operation_proto(response)
                if op_proto is None:
                    continue
                yield operation_from_proto(op_proto, account_id=broker_account_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_operations_stream_limiter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 6: SYNC-05 — IpCooldownGate

**Files:**
- Create: `backend/application/sync/ip_cooldown_gate.py`
- Test: `backend/tests/unit/test_ip_cooldown_gate.py`

Глобальный gate: при IP-уровневом cooldown открывается с эскалирующим backoff, оркестратор пропускает весь прогон. Redis-ключ с TTL (cross-worker) + per-process datetime fallback (Redis-down → degraded, но не хуже). fail-open допустим (gate — оптимизация против шторма).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_ip_cooldown_gate.py
"""SYNC-05: глобальный IP-cooldown gate с эскалирующим backoff и
per-process фолбэком при отсутствии/сбое Redis."""
from __future__ import annotations

import pytest

from application.sync.ip_cooldown_gate import IpCooldownGate, build_ip_cooldown_gate


@pytest.mark.asyncio
async def test_inprocess_open_then_is_open():
    clock = {"t": 1000.0}
    g = IpCooldownGate(redis_client=None, base=60, max_seconds=600, now_fn=lambda: clock["t"])
    assert await g.is_open() is False
    secs = await g.open()
    assert secs == 60
    assert await g.is_open() is True
    clock["t"] += 61  # TTL истёк
    assert await g.is_open() is False


@pytest.mark.asyncio
async def test_inprocess_backoff_escalates_and_caps():
    clock = {"t": 0.0}
    g = IpCooldownGate(redis_client=None, base=60, max_seconds=200, now_fn=lambda: clock["t"])
    assert await g.open() == 60     # level 1
    assert await g.open() == 120    # level 2 (60*2)
    assert await g.open() == 200    # level 3 (60*4=240 → cap 200)


@pytest.mark.asyncio
async def test_clear_resets_backoff_level():
    g = IpCooldownGate(redis_client=None, base=60, max_seconds=600, now_fn=lambda: __import__("time").monotonic())
    await g.open(); await g.open()
    await g.clear()
    # после clear эскалация начинается заново с base
    assert await g.open() == 60


@pytest.mark.asyncio
async def test_redis_down_degrades_to_process_state():
    class _FailRedis:
        async def set(self, *a, **k): raise ConnectionError("down")
        async def exists(self, *a, **k): raise ConnectionError("down")
        async def incr(self, *a, **k): raise ConnectionError("down")
        async def expire(self, *a, **k): raise ConnectionError("down")
        async def delete(self, *a, **k): raise ConnectionError("down")
    clock = {"t": 0.0}
    g = IpCooldownGate(redis_client=_FailRedis(), base=60, max_seconds=600, now_fn=lambda: clock["t"])
    secs = await g.open()           # Redis падает → process-fallback
    assert secs == 60
    assert await g.is_open() is True
    clock["t"] += 61
    assert await g.is_open() is False


def test_factory_inprocess_when_no_redis(monkeypatch):
    monkeypatch.setattr("application.sync.ip_cooldown_gate.settings.REDIS_URL", "", raising=False)
    g = build_ip_cooldown_gate()
    assert g._redis is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_ip_cooldown_gate.py -v`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Implement `ip_cooldown_gate.py`**

```python
# backend/application/sync/ip_cooldown_gate.py
"""SYNC-05: глобальный IP-cooldown gate.

Когда T-Bank cooldown'ит весь наш IP (IP-уровневый RESOURCE_EXHAUSTED, не
throttle одного токена), каждый аккаунт продолжает ретраить (tenacity 5x ×
scheduler 60s × ~500 коннекшнов) → retry-шторм ПРОДЛЕВАЕТ outage. Gate
открывается при кросс-коннекшн-сигнале и оркестратор пропускает весь прогон.

Слой НАД per-connection circuit_open_until (БД): gate = «весь IP остывает»,
circuit = «один коннекшн нездоров». Во время global cooldown per-connection
circuit'ы НЕ трогаем (иначе IP-блип массово откроет 500 circuit'ов).

Redis-ключ с TTL = cross-worker; per-process datetime = degraded-фолбэк при
Redis-down. Для gate fail-open допустим — это оптимизация против шторма, а не
последняя линия (per-token лимитер и per-connection circuit остаются).
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from config import settings
from logger import get_logger

log = get_logger("sync.ip_cooldown_gate")


class IpCooldownGate:
    _KEY = "tinkoff:ip_cooldown"
    _LEVEL_KEY = "tinkoff:ip_cooldown:level"

    def __init__(
        self,
        *,
        redis_client=None,
        base: int = 60,
        max_seconds: int = 600,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._redis = redis_client
        self._base = base
        self._max = max_seconds
        self._now = now_fn
        # per-process fallback state
        self._proc_until: float = 0.0
        self._proc_level: int = 0

    def _backoff(self, level: int) -> int:
        return min(self._base * (2 ** (level - 1)), self._max)

    async def is_open(self) -> bool:
        if self._redis is not None:
            try:
                return bool(await self._redis.exists(self._KEY))
            except Exception as exc:
                log.warning("ip_cooldown_gate: Redis exists упал (%s) — process-fallback", exc)
        return self._now() < self._proc_until

    async def open(self) -> int:
        """Открыть/продлить gate с эскалирующим backoff. Возвращает секунды."""
        if self._redis is not None:
            try:
                level = await self._redis.incr(self._LEVEL_KEY)
                await self._redis.expire(self._LEVEL_KEY, self._max * 2)
                secs = self._backoff(int(level))
                await self._redis.set(self._KEY, "1", ex=secs)
                log.warning("ip_cooldown_gate.opened level=%s seconds=%s", level, secs)
                return secs
            except Exception as exc:
                log.warning("ip_cooldown_gate: Redis open упал (%s) — process-fallback", exc)
        # process fallback
        self._proc_level += 1
        secs = self._backoff(self._proc_level)
        self._proc_until = self._now() + secs
        log.warning("ip_cooldown_gate.opened(proc) level=%s seconds=%s", self._proc_level, secs)
        return secs

    async def clear(self) -> None:
        """Чистый прогон — сбросить уровень эскалации (но не форсить закрытие
        активного cooldown: TTL/until сам истечёт)."""
        if self._redis is not None:
            try:
                await self._redis.delete(self._LEVEL_KEY)
                return
            except Exception as exc:
                log.warning("ip_cooldown_gate: Redis clear упал (%s) — process-fallback", exc)
        self._proc_level = 0


def build_ip_cooldown_gate() -> IpCooldownGate:
    """Factory: Redis если REDIS_URL, иначе in-process. Зеркалит build_stats_cache."""
    base = settings.TINKOFF_IP_COOLDOWN_BASE_SECONDS
    max_s = settings.TINKOFF_IP_COOLDOWN_MAX_SECONDS
    if not settings.REDIS_URL:
        return IpCooldownGate(redis_client=None, base=base, max_seconds=max_s)
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL)
        return IpCooldownGate(redis_client=client, base=base, max_seconds=max_s)
    except Exception as exc:
        log.warning("ip_cooldown_gate: REDIS_URL задан, init упал (%s) — in-process", exc)
        return IpCooldownGate(redis_client=None, base=base, max_seconds=max_s)
```

> Примечание по тесту `test_clear_resets_backoff_level`: для in-process пути `clear()` обнуляет `_proc_level`, поэтому следующий `open()` снова даёт `base`. Это совпадает с проверкой.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_ip_cooldown_gate.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 7: Wire orchestrator to the gate

**Files:**
- Modify: `backend/application/sync/orchestrator.py`
- Test: `backend/tests/integration/test_orchestrator.py` (добавить кейсы)

Инъектировать gate в конструктор; проверять `is_open()` ПЕРЕД fan-out; собирать различные connection_id, поймавшие `RateLimitExceeded`, за прогон; если их ≥ threshold → `gate.open()`, иначе `gate.clear()`. **НЕ** писать per-connection circuit во время global cooldown.

- [ ] **Step 1: Write the failing tests**

Добавить в `backend/tests/integration/test_orchestrator.py` (следовать существующему стилю файла — конструирование оркестратора, фейковые repo). Скелет:

```python
@pytest.mark.asyncio
async def test_run_skips_entirely_when_gate_open(monkeypatch):
    class _OpenGate:
        async def is_open(self): return True
        async def open(self): return 60
        async def clear(self): return None

    orch = TinkoffSyncOrchestrator(cooldown_gate=_OpenGate())
    # _select_due_connection_ids НЕ должен вызываться при открытом gate
    called = {"select": False}
    monkeypatch.setattr(
        orch, "_select_due_connection_ids",
        lambda: called.__setitem__("select", True) or [],
    )
    report = await orch.run_due_accounts()
    assert called["select"] is False
    assert report.accounts_considered == 0


@pytest.mark.asyncio
async def test_gate_opens_when_distinct_connections_rate_limited(monkeypatch):
    opened = {"n": 0}
    class _Gate:
        async def is_open(self): return False
        async def open(self): opened["n"] += 1; return 60
        async def clear(self): return None

    orch = TinkoffSyncOrchestrator(cooldown_gate=_Gate())
    monkeypatch.setattr(orch, "_select_due_connection_ids", lambda: [1, 2])

    # оба коннекшна ловят RateLimitExceeded
    from domain.exceptions import RateLimitExceeded
    async def _boom(cid):
        raise RateLimitExceeded(message="ip cooldown", code="RESOURCE_EXHAUSTED")
    monkeypatch.setattr(orch, "_load_connection", lambda cid: _FakeCtx(cid))  # см. helpers файла
    monkeypatch.setattr(orch, "_sync", lambda ctx: _boom(ctx.connection_id))

    await orch.run_due_accounts()
    assert opened["n"] == 1  # 2 различных коннекшна ≥ threshold(2) → gate открыт
```

> Адаптировать helper'ы (`_FakeCtx`, конструирование repo) под то, что уже есть в `tests/integration/test_orchestrator.py`. Если файла-helpers нет — использовать минимальный `_ConnectionCtx` из orchestrator или monkeypatch `_sync` напрямую (как выше), не требуя БД.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/integration/test_orchestrator.py -v -k "gate"`
Expected: FAIL — конструктор не принимает `cooldown_gate`.

- [ ] **Step 3: Modify orchestrator.py**

(а) Импорт:
```python
from application.sync.ip_cooldown_gate import IpCooldownGate, build_ip_cooldown_gate
```

(б) `__init__` — добавить параметр и поле:
```python
    def __init__(
        self,
        *,
        token_repo: Optional[TokenRepository] = None,
        operation_repo: Optional[OperationRepository] = None,
        instrument_repo: Optional[InstrumentRepository] = None,
        session_factory: Callable[[], Session] = SessionLocal,
        max_concurrent: int = 20,
        cooldown_gate: Optional[IpCooldownGate] = None,
    ) -> None:
        ...
        self._cooldown_gate = cooldown_gate or build_ip_cooldown_gate()
        self._min_distinct = settings.TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS
```

(в) `run_due_accounts` — gate-чек + сбор сигнала:
```python
    async def run_due_accounts(self) -> OrchestratorRunReport:
        report = OrchestratorRunReport(started_at=utc_now_naive())

        # SYNC-05: глобальный IP-cooldown — пропускаем весь прогон (storm-stopper).
        if await self._cooldown_gate.is_open():
            log.warning("orchestrator.run_due_accounts: skipped — IP cooldown gate open")
            report.finished_at = utc_now_naive()
            return report

        # per-run набор коннекшнов, словивших RateLimitExceeded (кросс-коннекшн
        # корреляция для IP-уровневого сигнала).
        self._rate_limited_connections: set[int] = set()

        connection_ids = await asyncio.to_thread(self._select_due_connection_ids)
        report.accounts_considered = len(connection_ids)
        if not connection_ids:
            report.finished_at = utc_now_naive()
            await self._cooldown_gate.clear()
            return report

        tasks = [self._guard_one(cid, report) for cid in connection_ids]
        await asyncio.gather(*tasks, return_exceptions=False)

        # SYNC-05: ≥ threshold различных коннекшнов словили rate-limit → IP-уровень.
        if len(self._rate_limited_connections) >= self._min_distinct:
            secs = await self._cooldown_gate.open()
            log.warning(
                "orchestrator: IP cooldown gate opened (%d connections rate-limited), backoff=%ss",
                len(self._rate_limited_connections), secs,
            )
        else:
            await self._cooldown_gate.clear()

        report.finished_at = utc_now_naive()
        log.info(
            "orchestrator.run_due_accounts: synced=%d skipped=%d failed=%d",
            report.accounts_synced, report.accounts_skipped, report.accounts_failed,
        )
        return report
```

(г) `_guard_one` — поймать `RateLimitExceeded` ОТДЕЛЬНО (до `BrokerError`, т.к. подкласс) и записать connection_id:
```python
                try:
                    sync_report = await self._sync(connection_data)
                    report.per_account.append(sync_report)
                    report.accounts_synced += 1
                except CircuitBreakerOpen:
                    report.accounts_skipped += 1
                except RateLimitExceeded:
                    # SYNC-05: сигнал для кросс-коннекшн корреляции. НЕ пишем
                    # per-connection circuit во время потенциального IP-cooldown.
                    report.accounts_failed += 1
                    self._rate_limited_connections.add(connection_id)
                    log.warning("sync rate-limited for connection_id=%s", connection_id)
                except BrokerError as exc:
                    report.accounts_failed += 1
                    log.warning(
                        "sync failed for connection_id=%s: %s — %s",
                        connection_id, type(exc).__name__, exc.message,
                    )
                except Exception:
                    report.accounts_failed += 1
                    log.exception("sync failed unexpectedly for connection_id=%s", connection_id)
```
Убедиться, что `RateLimitExceeded` импортируется (уже есть в orchestrator: `from domain.exceptions import (... RateLimitExceeded ...)`).

> Инициализировать `self._rate_limited_connections = set()` также в `__init__` (на случай прямого вызова `sync_one_account`/`_guard_one` в тестах вне `run_due_accounts`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/integration/test_orchestrator.py -v`
Expected: PASS (старые + 2 новых).

- [ ] **Step 5: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 8: Docs — worker-модель и env-переменные

**Files:**
- Modify: `backend/.business/operations/deployment.md`

- [ ] **Step 1: Append section** в `deployment.md` (после блока «Прод-требования: БД и Redis (Sprint 1A)»):

```markdown
## Прод-требования: gRPC-резилентность (Sprint 1B)

- **REDIS_URL** теперь обслуживает ещё и **общий per-token rate-limit** к T-Bank
  gRPC (SYNC-02). Без Redis каждый воркер держит свой бакет → эффективный лимит
  = N_workers × `TINKOFF_RATE_LIMIT_PER_MIN`, что пробивает потолок T-Bank
  200/min и ведёт к IP-cooldown. **На N>1 воркерах Redis ОБЯЗАТЕЛЕН** для sync.
- **Глобальный IP-cooldown gate** (SYNC-05) живёт в том же Redis (ключ
  `tinkoff:ip_cooldown`). При IP-уровневом RESOURCE_EXHAUSTED оркестратор
  пропускает прогоны с эскалирующим backoff (`TINKOFF_IP_COOLDOWN_BASE_SECONDS`
  → ×2 → cap `TINKOFF_IP_COOLDOWN_MAX_SECONDS`).
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
```

- [ ] **Step 2: Commit** — NO-COMMIT MODE, пропустить.

---

## Task 9: Integration test — Lua token-bucket против реального Redis (CI-only)

**Files:**
- Create: `backend/tests/integration/test_grpc_rate_limiter_redis.py`

Атомарность Lua нельзя проверить на dev (нет Redis). Тест skip'ается без `REDIS_TEST_URL` — на dev зелёный (skipped), в CI с Redis-сервисом реально гоняет.

- [ ] **Step 1: Write the test**

```python
# backend/tests/integration/test_grpc_rate_limiter_redis.py
"""SYNC-02: Lua token-bucket против реального Redis. Skip без REDIS_TEST_URL
(dev без Docker). В CI поднимать redis service и задавать REDIS_TEST_URL."""
from __future__ import annotations

import os

import pytest

REDIS_TEST_URL = os.getenv("REDIS_TEST_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_TEST_URL, reason="REDIS_TEST_URL не задан (нет Redis на dev)"
)


@pytest.mark.asyncio
async def test_redis_bucket_enforces_capacity():
    import redis.asyncio as aioredis
    from adapters.tinkoff.grpc_rate_limiter import InProcessTokenBucket, RedisTokenBucket

    client = aioredis.from_url(REDIS_TEST_URL)
    await client.delete("tinkoff:rl:itest:cap")
    bucket = RedisTokenBucket(client, fallback=InProcessTokenBucket())

    waits = [await bucket.acquire("itest:cap", rate=3, period=60) for _ in range(3)]
    assert waits == [0.0, 0.0, 0.0]
    w = await bucket.acquire("itest:cap", rate=3, period=60)
    assert w > 0.0  # 4-й за минуту — ждать
    await client.delete("tinkoff:rl:itest:cap")
    await client.aclose()
```

- [ ] **Step 2: Verify skip locally**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/integration/test_grpc_rate_limiter_redis.py -v`
Expected: SKIPPED (1 skipped) на dev.

- [ ] **Step 3 (отложено пользователю):** добавить redis-service в `.github/workflows/ci.yml` + `REDIS_TEST_URL=redis://localhost:6379` в env шага тестов. Отметить в плане как TODO для CI-задачи (Sprint 6 observability/CD трогает CI; можно сделать там).

- [ ] **Step 4: Commit** — NO-COMMIT MODE, пропустить.

---

## Final verification (вся Sprint 1B)

- [ ] **Полный backend unit + integration sync-слой:**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m pytest tests/unit tests/integration -q`
Expected: всё зелёное (новые тесты + 536 прежних, без регрессий). Integration Redis-тест — skipped.

- [ ] **App boot smoke (импорт без падений):**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -c "import main; print(len(main.app.routes), 'routes')"`
Expected: печатает число роутов, без ImportError/RuntimeError.

- [ ] **Type-check (если mypy сконфигурирован, Sprint 0):**

Run: `cd backend && PYTHONUTF8=1 python -X utf8 -m mypy adapters/tinkoff/grpc_rate_limiter.py application/sync/ip_cooldown_gate.py`
Expected: без ошибок в новых файлах (или те же baseline-warnings, что в проекте).

- [ ] **Final code review:** запустить `code-reviewer` субагент на полный diff Sprint 1B (idioms/perf/safety, особое внимание: атомарность Lua, отсутствие fail-open в лимитере, порядок except в _guard_one — RateLimitExceeded ДО BrokerError, отсутствие raw-токена в Redis-ключах). Затем `security-reviewer` (токены/PII в логах, Redis-инъекции через ключи).

---

## Exit-критерий Sprint 1B (из спеки)

- [x→проверить] per-token rate-limit общий cross-worker (SYNC-02) — Redis token-bucket + degraded фолбэк.
- [x→проверить] gRPC с таймаутами (SYNC-03) — call-deadline на каждом RPC.
- [x→проверить] global backoff на IP-cooldown (SYNC-05) — gate skip'ает прогон.
- [x→проверить] stream-лимитер 1 токен/стрим (SYNC-07) — захват только на open.
- worker-модель + новые env задокументированы в deployment.md.
- нагрузочный smoke без пробития лимита T-Bank — **отложено** до Sprint 3 (нагрузка) / операторского live-прогона в песочнице (нужен реальный Redis + N воркеров).

## Self-Review checklist (заполнено автором плана)

1. **Spec coverage:** SYNC-02 (Task 2+3), SYNC-03 (Task 4), SYNC-05 (Task 6+7), SYNC-07 (Task 5). Все 4 находки спринта покрыты.
2. **Placeholder scan:** код приведён целиком в каждом шаге; «отложено пользователю» помечено явно (CI redis-service, нагрузочный smoke).
3. **Type consistency:** `try_acquire`/`acquire` (backend), `SharedRateLimiter(key,rate,period,max_wait)`, `_limiter_for(token,kind=)`, `token_key(token,kind=)`, `IpCooldownGate(redis_client,base,max_seconds,now_fn)` / `is_open`/`open`/`clear`, `build_token_bucket_backend()`, `build_ip_cooldown_gate()` — имена согласованы между задачами.

## Открытые риски / заметки для исполнителя

- **pytest-asyncio режим:** проверить, как помечены существующие async-тесты в репо (`asyncio_mode`); если `auto` — `@pytest.mark.asyncio` лишний, если `strict` — обязателен. Привести новые тесты к локальному стилю.
- **RateLimitExceeded retryable:** он в `_RETRYABLE` tenacity (operations_client.py:50). max_wait→RateLimitExceeded будет ретраиться 5x. Это намеренно (transient pressure), а штормы гасит IP-gate. Кросс-аттемпт дедлайн (чтобы near-exhausted deadline не запускал полную цепь) — НЕ делаем в этом спринте (over-engineering); пометка на будущее.
- **Два Redis-клиента:** HTTP-лимитер — sync `RedisStorage` через `RATE_LIMIT_STORAGE_URI`; новый sync-слой — async `redis.asyncio` через `REDIS_URL`. Ключи разнесены префиксами (`tinkoff:rl:`, `tinkoff:ip_cooldown`, vs slowapi). Один Redis-инстанс обслуживает оба — ОК.
- **redis.asyncio lazy:** импорт `redis.asyncio` только в factory при заданном REDIS_URL — dev без Redis не пытается коннектиться.
- **Per-connection circuit_open_until:** в текущем orchestrator коде НЕ пишется в `_guard_one` (только читается в `_select`). Конфликта «gate vs circuit при записи» сейчас нет; если circuit-write добавят позже — гард «не писать circuit во время open gate» уже учтён в комментарии RateLimitExceeded-хэндлера.

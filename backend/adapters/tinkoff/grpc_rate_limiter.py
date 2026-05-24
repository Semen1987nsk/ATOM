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
from typing import Callable, Protocol

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

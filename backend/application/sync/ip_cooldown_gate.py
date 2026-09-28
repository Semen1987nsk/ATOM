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
from typing import Callable

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

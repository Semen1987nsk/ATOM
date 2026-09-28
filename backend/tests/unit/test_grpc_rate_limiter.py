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

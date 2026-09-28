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

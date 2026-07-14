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

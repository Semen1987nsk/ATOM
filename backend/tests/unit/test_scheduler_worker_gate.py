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

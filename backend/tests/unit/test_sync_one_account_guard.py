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

"""AU-stream Phase 1+: tests для StreamTaskManager (lifecycle, idempotency, locks)."""

from __future__ import annotations

import asyncio

import pytest

from application.sync.stream_manager import StreamTaskManager


class TestStreamTaskManagerLocks:
    def test_get_account_lock_creates_once(self):
        m = StreamTaskManager()
        lock1 = m.get_account_lock(42)
        lock2 = m.get_account_lock(42)
        assert lock1 is lock2  # идемпотентно

    def test_different_accounts_have_separate_locks(self):
        m = StreamTaskManager()
        lock_a = m.get_account_lock(1)
        lock_b = m.get_account_lock(2)
        assert lock_a is not lock_b


class TestStreamTaskManagerLifecycle:
    @pytest.mark.asyncio
    async def test_start_task_idempotent(self, monkeypatch):
        """Повторный start_task для того же conn_id — no-op."""
        m = StreamTaskManager()

        # Mock StreamConsumer.run чтобы не открывать настоящий gRPC.
        from application.sync import stream_consumer

        async def fake_run(self):
            await asyncio.sleep(60)  # долго живёт

        monkeypatch.setattr(stream_consumer.StreamConsumer, "run", fake_run)

        await m.start_task(99)
        first = m._tasks[99]
        await m.start_task(99)
        second = m._tasks[99]
        assert first is second  # тот же task

        # Cleanup
        await m.stop_task(99)

    @pytest.mark.asyncio
    async def test_stop_task_safe_when_no_task(self):
        """stop_task на несуществующий conn_id — не падает."""
        m = StreamTaskManager()
        await m.stop_task(999)  # должно тихо вернуться

    @pytest.mark.asyncio
    async def test_stop_task_cancels_running(self, monkeypatch):
        m = StreamTaskManager()
        from application.sync import stream_consumer

        async def fake_run(self):
            await asyncio.sleep(60)

        monkeypatch.setattr(stream_consumer.StreamConsumer, "run", fake_run)

        await m.start_task(101)
        assert m.active_task_count() == 1
        await m.stop_task(101, timeout_s=1.0)
        assert m.active_task_count() == 0

    @pytest.mark.asyncio
    async def test_start_during_shutdown_skipped(self):
        m = StreamTaskManager()
        m._stopping = True
        await m.start_task(1)
        assert m.active_task_count() == 0

    @pytest.mark.asyncio
    async def test_stop_all_parallel(self, monkeypatch):
        m = StreamTaskManager()
        from application.sync import stream_consumer

        async def fake_run(self):
            await asyncio.sleep(60)

        monkeypatch.setattr(stream_consumer.StreamConsumer, "run", fake_run)

        await m.start_task(1)
        await m.start_task(2)
        await m.start_task(3)
        assert m.active_task_count() == 3

        await m.stop_all(timeout_s=2.0)
        assert m.active_task_count() == 0

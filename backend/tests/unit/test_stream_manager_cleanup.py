"""SYNC-11 (Sprint 3, Task 4.3): cleanup _tasks / _account_locks в StreamTaskManager.

Sprint 1B (SYNC-02) убрал утечку `limiters` в `client_factory`. Здесь — оставшаяся
утечка в `StreamTaskManager`:

1. `self._tasks: dict[int, asyncio.Task]` — `_on_done` callback логирует,
   но НЕ удаляет завершённый task из dict. `active_task_count()` фильтрует
   по `not t.done()`, но dict растёт по мере crash/exit consumer'ов.
2. `self._account_locks: dict[int, asyncio.Lock]` — никогда не удаляются.
   После soft-delete BrokerConnection (account по сути deactivated) lock
   остаётся жить весь uptime процесса.

Тесты фиксируют:
- T1: завершённый task пропадает из `_tasks` после короткой паузы
      (_on_done должен сделать pop).
- T2: `release_account_lock(account_id)` явно удаляет lock; идемпотентен.
- T3: `release_account_lock` на несуществующий id не падает.
"""

from __future__ import annotations

import asyncio

import pytest

from application.sync.stream_manager import StreamTaskManager


class TestStreamManagerTasksCleanup:
    @pytest.mark.asyncio
    async def test_completed_task_removed_from_registry(self, monkeypatch):
        """SYNC-11: после завершения consumer'а connection_id должен
        исчезнуть из `_tasks` (не только активный счётчик)."""
        m = StreamTaskManager()
        from application.sync import stream_consumer

        async def fake_run(self):
            # Быстро возвращаемся — task завершится "clean exit".
            await asyncio.sleep(0)

        monkeypatch.setattr(stream_consumer.StreamConsumer, "run", fake_run)

        await m.start_task(777)
        assert 777 in m._tasks  # запуск зарегистрирован

        # Дать event-loop'у дореализовать task и вызвать done-callback.
        for _ in range(20):
            if 777 not in m._tasks:
                break
            await asyncio.sleep(0.01)

        assert 777 not in m._tasks, "completed task not cleaned from _tasks"
        assert m.active_task_count() == 0

    @pytest.mark.asyncio
    async def test_crashed_task_removed_from_registry(self, monkeypatch):
        """Crashed task тоже удаляется из реестра (log+pop, не leak)."""
        m = StreamTaskManager()
        from application.sync import stream_consumer

        async def fake_run(self):
            raise RuntimeError("boom")

        monkeypatch.setattr(stream_consumer.StreamConsumer, "run", fake_run)

        await m.start_task(888)
        assert 888 in m._tasks

        for _ in range(20):
            if 888 not in m._tasks:
                break
            await asyncio.sleep(0.01)

        assert 888 not in m._tasks, "crashed task not cleaned from _tasks"


class TestReleaseAccountLock:
    def test_release_account_lock_removes_entry(self):
        """SYNC-11: `release_account_lock(account_id)` убирает lock из dict."""
        m = StreamTaskManager()
        _ = m.get_account_lock(42)
        assert 42 in m._account_locks

        m.release_account_lock(42)
        assert 42 not in m._account_locks

    def test_release_account_lock_idempotent(self):
        """Повторный вызов не падает (idempotent)."""
        m = StreamTaskManager()
        m.release_account_lock(99)  # не существует — no-op
        m.release_account_lock(99)  # повторно — тоже no-op

    def test_release_one_account_keeps_others(self):
        """release_account_lock не трогает соседние записи."""
        m = StreamTaskManager()
        lock_a = m.get_account_lock(1)
        lock_b = m.get_account_lock(2)

        m.release_account_lock(1)

        assert 1 not in m._account_locks
        assert 2 in m._account_locks
        assert m._account_locks[2] is lock_b
        # после release повторный get_account_lock(1) создаёт НОВЫЙ lock
        new_lock_a = m.get_account_lock(1)
        assert new_lock_a is not lock_a

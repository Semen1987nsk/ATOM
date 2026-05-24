"""StreamTaskManager — AU-stream Phase 1+ component.

Управляет жизнью per-BrokerConnection long-lived asyncio tasks:

- На startup (FastAPI lifespan) → start_all_enabled() поднимает streams
  для всех `BrokerConnection.is_active=True AND stream_enabled=True`.
- На shutdown → stop_all() graceful cancel + await.
- Per-connection idempotent: start_task() ничего не делает если task уже
  запущен; stop_task() безопасен если task'а нет.

Per-account asyncio.Lock используется для координации с cursor-based
sync (TinkoffSyncOrchestrator). Cursor sync acquire'ит lock перед
batch sync — stream consumer ждёт. Stream consumer тоже acquire'ит
lock перед persist каждой operation. Это сериализует write'ы и
устраняет race conditions без table-level locking.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from database import SessionLocal
import models
from logger import get_logger

log = get_logger("application.sync.stream_manager")


class StreamTaskManager:
    """Singleton-like manager. Создаётся один раз в main.py / sync_scheduler."""

    def __init__(self) -> None:
        # connection_id → asyncio.Task (running stream consumer)
        self._tasks: dict[int, asyncio.Task] = {}
        # account_id → asyncio.Lock (для координации с cursor-sync)
        self._account_locks: dict[int, asyncio.Lock] = {}
        self._stopping = False

    # ── per-connection lifecycle ─────────────────────────────────────────

    async def start_task(self, connection_id: int) -> None:
        """Идемпотентно запускает stream consumer для connection_id.

        Если task уже запущен (running, not done) — no-op.
        Если task завершился с ошибкой — перезапускает.
        """
        if self._stopping:
            log.warning("stream_manager.start_skipped_during_shutdown",
                        extra={"connection_id": connection_id})
            return

        existing = self._tasks.get(connection_id)
        if existing is not None and not existing.done():
            log.debug("stream_manager.task_already_running",
                      extra={"connection_id": connection_id})
            return

        # Lazy import — avoid circular (stream_consumer imports stream_manager)
        from application.sync.stream_consumer import StreamConsumer

        consumer = StreamConsumer(connection_id=connection_id, manager=self)
        task = asyncio.create_task(
            consumer.run(),
            name=f"stream_consumer_conn_{connection_id}",
        )
        self._tasks[connection_id] = task

        # Cleanup on done — log unexpected errors
        def _on_done(t: asyncio.Task) -> None:
            if t.cancelled():
                log.info("stream_consumer.cancelled", extra={"connection_id": connection_id})
                return
            exc = t.exception()
            if exc is not None:
                log.error(
                    "stream_consumer.crashed",
                    extra={"connection_id": connection_id, "exc": str(exc)},
                    exc_info=exc,
                )
            else:
                log.info("stream_consumer.exited_clean", extra={"connection_id": connection_id})

        task.add_done_callback(_on_done)
        log.info("stream_consumer.started", extra={"connection_id": connection_id})

    async def stop_task(self, connection_id: int, *, timeout_s: float = 10.0) -> None:
        """Graceful cancel + await. Безопасно вызывать если task'а нет."""
        task = self._tasks.pop(connection_id, None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=timeout_s)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            log.warning("stream_consumer.stop_timeout",
                        extra={"connection_id": connection_id, "timeout_s": timeout_s})
        except Exception:
            log.exception("stream_consumer.stop_failed",
                          extra={"connection_id": connection_id})

    # ── bulk lifecycle ───────────────────────────────────────────────────

    async def start_all_enabled(self) -> int:
        """На startup: найти все active connection с stream_enabled=True
        и запустить stream consumer для каждого. Возвращает кол-во стартованных.

        Защищено от запуска дважды (start_task — идемпотентен).
        """
        count = 0
        session = SessionLocal()
        try:
            conns = (
                session.query(models.BrokerConnection.id)
                .filter(
                    models.BrokerConnection.is_active.is_(True),
                    models.BrokerConnection.stream_enabled.is_(True),
                )
                .all()
            )
            connection_ids = [c[0] for c in conns]
        finally:
            session.close()

        for conn_id in connection_ids:
            await self.start_task(conn_id)
            count += 1

        log.info("stream_manager.start_all_enabled_done", extra={"count": count})
        return count

    async def stop_all(self, *, timeout_s: float = 10.0) -> None:
        """Lifespan shutdown — cancel all stream consumers parallel."""
        self._stopping = True
        connection_ids = list(self._tasks.keys())
        if not connection_ids:
            log.info("stream_manager.stop_all_no_tasks")
            return
        log.info("stream_manager.stop_all_started", extra={"count": len(connection_ids)})
        await asyncio.gather(
            *(self.stop_task(cid, timeout_s=timeout_s) for cid in connection_ids),
            return_exceptions=True,
        )
        self._stopping = False
        log.info("stream_manager.stop_all_done")

    # ── coordination locks ───────────────────────────────────────────────

    def get_account_lock(self, account_id: int) -> asyncio.Lock:
        """Возвращает (создаёт если нет) per-account_id asyncio.Lock.

        Используется и stream consumer'ом перед persist каждой op,
        и cursor-sync orchestrator'ом перед batch sync. Сериализует
        write'ы — нет race conditions, дубликатов или corruption.

        NB: dict mutation в asyncio context safe потому что нет await
        между check и set (atomic).
        """
        lock = self._account_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self._account_locks[account_id] = lock
        return lock

    # ── observability ────────────────────────────────────────────────────

    def active_task_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def active_connection_ids(self) -> list[int]:
        return [cid for cid, t in self._tasks.items() if not t.done()]


# Module-level singleton (как scheduler в sync_scheduler.py).
# Импортируется из main.py lifespan и admin endpoint.
stream_manager = StreamTaskManager()

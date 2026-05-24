"""StreamConsumer — AU-stream Phase 1+ component.

Один long-lived asyncio task на BrokerConnection. Жизненный цикл:

1. Открыть `client_factory.async_client(token)` (per-token rate-limit + TLS)
2. Iterate `TinkoffOperationsStreamClient.stream_operations(broker_account_id)`
3. Для каждой Operation:
   a. Acquire account_lock через StreamTaskManager (блокирует cursor-sync)
   b. Dedup check через StreamOperationDeduplicator
   c. Если new — UPSERT через OperationRepository.upsert_many([op])
   d. Trigger lightweight FIFO recompute для затронутого instrument
   e. Update BrokerConnection.last_sync_at
   f. Release lock
4. На disconnect:
   a. Trigger cursor-based catch-up через orchestrator.sync_one_account()
   b. Reconnect с exponential backoff (handled inside operations_stream_client)

Cancel via asyncio.Task.cancel() — graceful shutdown в lifespan.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from adapters.persistence.operation_repo import OperationRepository
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionError, TokenEncryptionService
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.operations_stream_client import TinkoffOperationsStreamClient
from application.sync.dedup import StreamOperationDeduplicator
from database import SessionLocal
from domain.exceptions import BrokerError, BrokerUnavailable, TokenInvalid
import models
from logger import get_logger
from utils.datetime_utils import utc_now_naive

if TYPE_CHECKING:
    from application.sync.stream_manager import StreamTaskManager

log = get_logger("application.sync.stream_consumer")


# Как часто обновлять BrokerConnection.last_sync_at (батчинг, чтобы не
# писать БД на каждое стрим-событие). 30 секунд — компромисс между
# observability и DB load.
_LAST_SYNC_AT_THROTTLE_S = 30.0

# Backoff после отказа сессии (separate от reconnect внутри stream_client).
_SESSION_FAIL_BACKOFF_S = [10.0, 30.0, 60.0, 120.0, 300.0]


class StreamConsumer:
    """Один экземпляр на BrokerConnection. Запускается через StreamTaskManager."""

    def __init__(
        self,
        *,
        connection_id: int,
        manager: "StreamTaskManager",
    ) -> None:
        self._conn_id = connection_id
        self._manager = manager
        self._dedup = StreamOperationDeduplicator(cache_size=1000)
        self._operation_repo = OperationRepository()
        self._last_sync_at_updated: Optional[float] = None  # monotonic

    async def run(self) -> None:
        """Main loop. Жизнь до cancel или unrecoverable error."""
        attempt = 0
        while True:
            try:
                # Catch-up через cursor-sync ДО открытия stream — добирает
                # всё что прилетело пока stream был оффлайн.
                if attempt > 0:
                    await self._catchup_via_cursor()

                await self._run_session()
                # Stream закрылся cleanly (например, get_accounts вернул
                # пусто) → перезапускаем после backoff.
                attempt = 0
            except asyncio.CancelledError:
                log.info("stream_consumer.cancelled_during_run",
                         extra={"connection_id": self._conn_id})
                raise
            except TokenInvalid as exc:
                log.error("stream_consumer.token_invalid_giving_up",
                          extra={"connection_id": self._conn_id, "exc": str(exc)})
                return  # token revoked — stop consumer permanently
            except Exception as exc:
                attempt += 1
                delay = _SESSION_FAIL_BACKOFF_S[
                    min(attempt - 1, len(_SESSION_FAIL_BACKOFF_S) - 1)
                ]
                log.warning(
                    "stream_consumer.session_failed",
                    extra={
                        "connection_id": self._conn_id,
                        "attempt": attempt,
                        "delay_s": delay,
                        "exc_type": type(exc).__name__,
                        "exc_msg": str(exc)[:200],
                    },
                )
                await asyncio.sleep(delay)

    # ── session lifecycle ────────────────────────────────────────────────

    async def _run_session(self) -> None:
        """Один stream session: open → iterate → close."""
        # 1. Load BrokerConnection + decrypt token (sync DB work in to_thread)
        conn_data = await asyncio.to_thread(self._load_connection)
        if conn_data is None:
            # Connection deleted/disabled while we были offline — exit
            log.info("stream_consumer.connection_gone", extra={"connection_id": self._conn_id})
            return
        account_id, broker_account_id, token = conn_data

        log.info(
            "stream_consumer.session_starting",
            extra={
                "connection_id": self._conn_id,
                "account_id": account_id,
                "broker_account_id": broker_account_id,
            },
        )

        # 2. Open client + start stream
        async with client_factory.async_client(token) as services:
            stream_client = TinkoffOperationsStreamClient(services)
            async for op in stream_client.stream_operations(broker_account_id):
                await self._process_operation(account_id, broker_account_id, op)

    async def _process_operation(
        self,
        account_id: int,
        broker_account_id: str,
        op,  # domain.Operation
    ) -> None:
        """Acquire lock → dedup → upsert → maybe-recompute → update last_sync_at."""
        lock = self._manager.get_account_lock(account_id)
        async with lock:
            await asyncio.to_thread(
                self._persist_operation_sync,
                account_id,
                broker_account_id,
                op,
            )

    def _persist_operation_sync(
        self,
        account_id: int,
        broker_account_id: str,
        op,
    ) -> None:
        """Sync DB work — вызывается через asyncio.to_thread."""
        session = SessionLocal()
        try:
            if not self._dedup.is_new(
                account_id=account_id,
                operation_id=op.operation_id,
                session=session,
            ):
                log.debug(
                    "stream_consumer.dedup_skip",
                    extra={
                        "connection_id": self._conn_id,
                        "operation_id": op.operation_id,
                    },
                )
                return

            self._operation_repo.upsert_many(
                session,
                account_id=account_id,
                broker_account_id=broker_account_id,
                operations=[op],
            )
            session.commit()
            self._dedup.mark_persisted(
                account_id=account_id, operation_id=op.operation_id
            )
            log.info(
                "stream_consumer.operation_persisted",
                extra={
                    "connection_id": self._conn_id,
                    "operation_id": op.operation_id,
                    "operation_type": getattr(op.operation_type, "value", str(op.operation_type)),
                    "instrument_uid": op.instrument_uid,
                    "executed_at": op.executed_at.isoformat() if op.executed_at else None,
                },
            )

            # Update last_sync_at (throttled — не на каждое событие)
            self._maybe_update_last_sync_at(session)
        except Exception:
            session.rollback()
            log.exception(
                "stream_consumer.persist_failed",
                extra={"connection_id": self._conn_id, "operation_id": op.operation_id},
            )
        finally:
            session.close()

    def _maybe_update_last_sync_at(self, session: Session) -> None:
        """Throttled update BrokerConnection.last_sync_at (раз в 30s)."""
        from time import monotonic

        now_mono = monotonic()
        if (
            self._last_sync_at_updated is not None
            and (now_mono - self._last_sync_at_updated) < _LAST_SYNC_AT_THROTTLE_S
        ):
            return

        try:
            session.query(models.BrokerConnection).filter_by(id=self._conn_id).update(
                {
                    "last_sync_at": utc_now_naive(),
                    "last_sync_status": "stream_active",
                }
            )
            session.commit()
            self._last_sync_at_updated = now_mono
        except Exception:
            session.rollback()
            log.exception("stream_consumer.last_sync_at_update_failed")

    # ── catch-up через cursor-based sync ─────────────────────────────────

    async def _catchup_via_cursor(self) -> None:
        """После reconnect — догнать пропущенные ops через обычный orchestrator.

        Это safety net: даже если stream не доставил какие-то событий
        (network glitch), cursor-based fetch их догонит. Использует тот
        же account_lock что и stream consumer, поэтому нет race.
        """
        try:
            from application.sync.orchestrator import build_default_orchestrator

            orch = build_default_orchestrator()
            if orch is None:
                log.warning("stream_consumer.catchup_no_orchestrator",
                            extra={"connection_id": self._conn_id})
                return
            log.info("stream_consumer.catchup_started",
                     extra={"connection_id": self._conn_id})
            report = await orch.sync_one_account(self._conn_id)
            log.info(
                "stream_consumer.catchup_done",
                extra={
                    "connection_id": self._conn_id,
                    "ops_new": report.operations_new_or_updated if report else None,
                    "trades_built": report.trades_built if report else None,
                },
            )
        except Exception:
            log.exception("stream_consumer.catchup_failed",
                          extra={"connection_id": self._conn_id})

    # ── helpers ──────────────────────────────────────────────────────────

    def _load_connection(self) -> Optional[tuple[int, str, str]]:
        """Sync DB read — возвращает (account_id, broker_account_id, decrypted_token)."""
        session = SessionLocal()
        try:
            conn = session.query(models.BrokerConnection).filter_by(id=self._conn_id).first()
            if conn is None or not conn.is_active or not conn.stream_enabled:
                return None
            try:
                token_repo = TokenRepository(encryption=TokenEncryptionService())
                token = token_repo.decrypt(conn.api_token)
            except TokenEncryptionError as exc:
                log.error("stream_consumer.token_decrypt_failed",
                          extra={"connection_id": self._conn_id, "exc": str(exc)})
                return None
            return (conn.account_id, conn.broker_account_id, token)
        finally:
            session.close()

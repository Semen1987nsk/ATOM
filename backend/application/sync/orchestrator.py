"""
TinkoffSyncOrchestrator — координирует sync для нескольких аккаунтов.

Задачи:

* Найти `BrokerConnection`-записи, которым пора синхронизироваться
  (`last_sync_at + sync_interval_minutes <= now`, `circuit_open_until` либо
  null, либо в прошлом).
* Расшифровать токен через `TokenRepository`.
* Запустить `SyncPipeline.run()` с ограничением concurrency.
* Записать `last_audit_at` после успешной/неуспешной попытки.

В PR 5 используется `Semaphore(max_concurrent)` — простой honest bulkhead
на уровне процесса. PR 15 добавит circuit-breaker и tenacity-retry.

Зависимости (для тестируемости) принимаются явно через конструктор.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.persistence.operation_repo import OperationRepository
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from application.sync.pipeline import SyncPipeline, SyncReport
from config import settings
from database import SessionLocal
from domain.exceptions import (
    BrokerError,
    CircuitBreakerOpen,
    RateLimitExceeded,
    TokenInvalid,
)
from logger import get_logger
from models import BrokerConnection, BrokerType
from utils.datetime_utils import utc_now_naive

log = get_logger("sync.orchestrator")


# ── data classes ──────────────────────────────────────────────────────


@dataclass
class OrchestratorRunReport:
    """Итог одного прогона `run_due_accounts()`."""

    started_at: datetime
    finished_at: Optional[datetime] = None
    accounts_considered: int = 0
    accounts_synced: int = 0
    accounts_skipped: int = 0
    accounts_failed: int = 0
    per_account: list[SyncReport] = field(default_factory=list)


# ── orchestrator ──────────────────────────────────────────────────────


class TinkoffSyncOrchestrator:
    def __init__(
        self,
        *,
        token_repo: Optional[TokenRepository] = None,
        operation_repo: Optional[OperationRepository] = None,
        instrument_repo: Optional[InstrumentRepository] = None,
        session_factory: Callable[[], Session] = SessionLocal,
        max_concurrent: int = 20,
    ) -> None:
        self._token_repo = token_repo or TokenRepository(
            encryption=TokenEncryptionService()
        )
        self._operation_repo = operation_repo or OperationRepository()
        self._instrument_repo = instrument_repo or InstrumentRepository()
        self._session_factory = session_factory
        self._semaphore = asyncio.Semaphore(max_concurrent)
        # bulkhead per-connection: одну sync-задачу на одно подключение
        # не запускаем дважды параллельно.
        self._in_flight: set[int] = set()

    # ── публичные методы ──────────────────────────────────────────────

    async def run_due_accounts(self) -> OrchestratorRunReport:
        """
        Вызывается планировщиком (раз в 60 сек). Находит все подключения,
        которым пора синкаться, и запускает `sync_one_account` параллельно
        с лимитом по семафору.
        """
        report = OrchestratorRunReport(started_at=utc_now_naive())
        connection_ids = await asyncio.to_thread(self._select_due_connection_ids)
        report.accounts_considered = len(connection_ids)

        if not connection_ids:
            report.finished_at = utc_now_naive()
            return report

        # Запускаем параллельно с ограничением через семафор.
        tasks = [self._guard_one(cid, report) for cid in connection_ids]
        await asyncio.gather(*tasks, return_exceptions=False)

        report.finished_at = utc_now_naive()
        log.info(
            "orchestrator.run_due_accounts: synced=%d skipped=%d failed=%d",
            report.accounts_synced,
            report.accounts_skipped,
            report.accounts_failed,
        )
        return report

    async def sync_one_account(self, connection_id: int) -> SyncReport:
        """
        Public API для ручного trigger'а (UI / админка). Принимает
        connection_id, сам разрешает context (расшифровка токена и т.п.).
        """
        connection_data = await asyncio.to_thread(self._load_connection, connection_id)
        if connection_data is None:
            raise ValueError(f"BrokerConnection {connection_id} not found or inactive")
        return await self._sync(connection_data)

    # ── внутренняя кухня ──────────────────────────────────────────────

    async def _guard_one(self, connection_id: int, report: OrchestratorRunReport) -> None:
        """Per-connection wrapper: учёт concurrency + статуса."""
        if connection_id in self._in_flight:
            report.accounts_skipped += 1
            return
        self._in_flight.add(connection_id)
        try:
            async with self._semaphore:
                connection_data = await asyncio.to_thread(
                    self._load_connection, connection_id
                )
                if connection_data is None:
                    report.accounts_skipped += 1
                    return
                try:
                    sync_report = await self._sync(connection_data)
                    report.per_account.append(sync_report)
                    report.accounts_synced += 1
                except CircuitBreakerOpen:
                    report.accounts_skipped += 1
                except BrokerError as exc:
                    report.accounts_failed += 1
                    log.warning(
                        "sync failed for connection_id=%s: %s — %s",
                        connection_id,
                        type(exc).__name__,
                        exc.message,
                    )
                except Exception:
                    report.accounts_failed += 1
                    log.exception("sync failed unexpectedly for connection_id=%s", connection_id)
        finally:
            self._in_flight.discard(connection_id)

    async def _sync(self, ctx: "_ConnectionCtx") -> SyncReport:
        # Защита от race condition: токен мог быть отозван между
        # _select_due и _sync.
        if ctx.api_token_ciphertext == "":
            raise TokenInvalid("token was deactivated", code="DEACTIVATED")

        try:
            token_plaintext = self._token_repo.decrypt(ctx.api_token_ciphertext)
        except TokenEncryptionError as exc:
            log.error(
                "decryption failed for connection_id=%s: %s",
                ctx.connection_id,
                exc,
            )
            await asyncio.to_thread(self._mark_failure, ctx.connection_id, "decryption_failed")
            raise

        pipeline = SyncPipeline(
            account_id=ctx.account_id,
            broker_account_id=ctx.broker_account_id,
            token_plaintext=token_plaintext,
            operation_repo=self._operation_repo,
            instrument_repo=self._instrument_repo,
            session_factory=self._session_factory,
        )
        try:
            return await pipeline.run(full_sync=(ctx.sync_cursor is None or ctx.sync_cursor == ""))
        except TokenInvalid:
            # Жирный сигнал: токен отзыван. Деактивируем подключение.
            await asyncio.to_thread(self._deactivate, ctx.connection_id, "token_invalid")
            raise
        except RateLimitExceeded:
            # PR 15: открыть circuit breaker. Пока — счётчик ошибок.
            raise

    # ── работа с БД (синхронная) ──────────────────────────────────────

    def _select_due_connection_ids(self) -> list[int]:
        """SELECT connection_id где пора синкать."""
        now = utc_now_naive()
        session = self._session_factory()
        try:
            query = session.query(BrokerConnection.id).filter(
                BrokerConnection.is_active.is_(True),
                BrokerConnection.auto_sync_enabled.is_(True),
                BrokerConnection.broker == BrokerType.TINKOFF,
            )
            rows = query.all()
            ids: list[int] = []
            for (cid,) in rows:
                # Проверим circuit breaker отдельно для читаемости.
                conn = session.query(BrokerConnection).filter_by(id=cid).first()
                if conn is None:
                    continue
                if conn.circuit_open_until and conn.circuit_open_until > now:
                    continue
                if conn.last_sync_at is None:
                    ids.append(cid)
                    continue
                # last_sync_at + sync_interval_minutes <= now → пора
                from datetime import timedelta

                next_due = conn.last_sync_at + timedelta(
                    minutes=conn.sync_interval_minutes or 60
                )
                if next_due <= now:
                    ids.append(cid)
            return ids
        finally:
            session.close()

    def _load_connection(self, connection_id: int) -> Optional["_ConnectionCtx"]:
        """Снять snapshot нужных полей: после этого session закроется."""
        session = self._session_factory()
        try:
            conn = (
                session.query(BrokerConnection)
                .filter_by(id=connection_id, is_active=True)
                .first()
            )
            if conn is None:
                return None
            return _ConnectionCtx(
                connection_id=conn.id,
                account_id=conn.account_id,
                broker_account_id=conn.broker_account_id,
                api_token_ciphertext=conn.api_token,
                sync_cursor=conn.sync_cursor,
                sync_interval_minutes=conn.sync_interval_minutes,
            )
        finally:
            session.close()

    def _mark_failure(self, connection_id: int, reason: str) -> None:
        session = self._session_factory()
        try:
            conn = session.query(BrokerConnection).filter_by(id=connection_id).first()
            if conn is None:
                return
            conn.last_sync_status = "error"
            conn.last_sync_error = reason[:512]
            conn.last_sync_at = utc_now_naive()
            conn.consecutive_failures = (conn.consecutive_failures or 0) + 1
            session.commit()
        except Exception:
            log.exception("failed to mark failure for connection_id=%s", connection_id)
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def _deactivate(self, connection_id: int, reason: str) -> None:
        session = self._session_factory()
        try:
            conn = session.query(BrokerConnection).filter_by(id=connection_id).first()
            if conn is None:
                return
            conn.is_active = False
            conn.last_sync_status = "error"
            conn.last_sync_error = f"deactivated: {reason}"
            conn.api_token = ""
            session.commit()
            log.warning(
                "deactivated connection_id=%s reason=%s", connection_id, reason
            )
        except Exception:
            log.exception("failed to deactivate connection_id=%s", connection_id)
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()


@dataclass(frozen=True)
class _ConnectionCtx:
    """Snapshot нужных полей BrokerConnection (вне сессии)."""

    connection_id: int
    account_id: int
    broker_account_id: str
    api_token_ciphertext: str
    sync_cursor: Optional[str]
    sync_interval_minutes: int


# ── factory для scheduler-кода ────────────────────────────────────────


def build_default_orchestrator() -> Optional[TinkoffSyncOrchestrator]:
    """
    Создать orchestrator с дефолтными зависимостями. Возвращает None
    если новый sync выключен флагом или мастер-ключ не задан в env.
    """
    if not settings.BROKER_SYNC_V2_ENABLED:
        return None
    try:
        encryption = TokenEncryptionService()
    except TokenEncryptionError as exc:
        log.warning("orchestrator disabled: %s", exc)
        return None
    return TinkoffSyncOrchestrator(
        token_repo=TokenRepository(encryption=encryption),
    )

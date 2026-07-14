"""
TokenRepository — sync SQLAlchemy реализация для PR 4.

Хранит зашифрованные брокерские токены в таблице `broker_connections`
(поле `api_token`, шифрование AES-256-GCM через `TokenEncryptionService`).
Также пишет audit-события в `token_audit_log`.

Архитектурно: domain.repositories.TokenRepository — async Protocol.
Сейчас orchestrator (PR 5) ещё не пишется, FastAPI-роутеры используют
sync `Session` (`Depends(get_db)`). Чтобы не делать масштабный async-
рефакторинг ради одного PR, реализация sync — а из async кода
вызывается через `asyncio.to_thread()`. Когда вся persistence уйдёт
на async (отдельный PR), эту реализацию заменим без изменения контракта.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from adapters.security.token_audit import (
    AuditEvent,
    TokenAuditRecorder,
    hash_user_id,
)
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from logger import get_logger
from models import BrokerConnection, BrokerType
from utils.datetime_utils import utc_now_naive

log = get_logger("token_repo")


class TokenRepository:
    """
    Минимальный CRUD для зашифрованных токенов в БД.

    Не открывает session сам — ожидает session-фабрику (для тестов) или
    sync `Session` snapshot (для FastAPI dependency).
    """

    def __init__(
        self,
        encryption: TokenEncryptionService,
        *,
        audit: TokenAuditRecorder | None = None,
    ) -> None:
        self._enc = encryption
        self._audit = audit or TokenAuditRecorder()

    # ── encrypt/decrypt без работы с БД ────────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        return self._enc.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        return self._enc.decrypt(ciphertext)

    # ── CRUD на broker_connections ─────────────────────────────────────

    def store(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: str,
        plaintext_token: str,
        scope: str = "read-only",
        sync_interval_minutes: int = 60,
    ) -> BrokerConnection:
        """
        Сохранить новый токен. Шифрование выполняется здесь, plaintext
        в БД НЕ попадает ни в каком виде.

        Если для этого `(account_id, broker_account_id)` уже есть запись —
        обновляем её (rotate token), включая деактивированную (SYNC-01:
        реконнект после отозванного токена реактивирует ту же строку —
        INSERT упал бы на UNIQUE (account_id, broker, broker_account_id)).
        Иначе создаём новую.
        """
        existing: BrokerConnection | None = (
            session.query(BrokerConnection)
            .filter(
                BrokerConnection.account_id == account_id,
                BrokerConnection.broker_account_id == broker_account_id,
            )
            .order_by(BrokerConnection.is_active.desc())
            .first()
        )

        ciphertext = self._enc.encrypt(plaintext_token)
        now = utc_now_naive()

        if existing is not None:
            reactivated = not existing.is_active
            existing.is_active = True
            existing.api_token = ciphertext
            existing.key_id = self._enc.current_key_id
            existing.updated_at = now
            existing.last_sync_error = None
            existing.consecutive_failures = 0
            existing.circuit_open_until = None
            connection = existing
            verb = "reactivated" if reactivated else "rotated"
            log.info(f"{verb} token for account_id={account_id}, broker_account_id={broker_account_id}")
        else:
            connection = BrokerConnection(
                account_id=account_id,
                broker=BrokerType.TINKOFF,
                api_token=ciphertext,
                broker_account_id=broker_account_id,
                is_active=True,
                auto_sync_enabled=True,
                sync_interval_minutes=sync_interval_minutes,
                total_synced_trades=0,
                key_id=self._enc.current_key_id,
                consecutive_failures=0,
                created_at=now,
                updated_at=now,
            )
            session.add(connection)
            log.info(f"stored new token for account_id={account_id}, broker_account_id={broker_account_id}")

        session.flush()  # получить id, не коммитить (commit — на вызывающей стороне)
        return connection

    def get_decrypted(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Достать и расшифровать токен. Возвращает None если активного
        подключения нет.

        Поднимает `TokenEncryptionError` при `key_id` для которого
        мастер-ключ отсутствует в env — это сигнал что ключ ротирован,
        а мы запустились без старого MASTER_KEY_<N>_B64.
        """
        query = session.query(BrokerConnection).filter(
            BrokerConnection.account_id == account_id,
            BrokerConnection.is_active.is_(True),
        )
        if broker_account_id:
            query = query.filter(BrokerConnection.broker_account_id == broker_account_id)

        connection = query.first()
        if connection is None:
            return None
        if not connection.api_token:
            return None
        return self._enc.decrypt(connection.api_token)

    def deactivate(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: Optional[str] = None,
        reason: str = "user_request",
    ) -> bool:
        """
        Мягкое удаление: is_active=False + затираем api_token.

        Возвращает True если что-то деактивировано.
        """
        query = session.query(BrokerConnection).filter(
            BrokerConnection.account_id == account_id,
            BrokerConnection.is_active.is_(True),
        )
        if broker_account_id:
            query = query.filter(BrokerConnection.broker_account_id == broker_account_id)

        connection = query.first()
        if connection is None:
            return False

        connection.is_active = False
        connection.api_token = ""  # затираем зашифрованный токен
        connection.last_sync_error = f"deactivated: {reason}"
        connection.updated_at = utc_now_naive()
        log.info(
            f"deactivated connection id={connection.id} account_id={account_id} reason={reason!r}"
        )
        return True

    def update_last_audit_at(
        self,
        session: Session,
        *,
        connection_id: int,
        at: datetime | None = None,
    ) -> None:
        """Обновить `last_audit_at` после каждого audit-record (опционально)."""
        connection = session.query(BrokerConnection).filter(
            BrokerConnection.id == connection_id
        ).first()
        if connection is None:
            return
        connection.last_audit_at = at or utc_now_naive()

    # ── audit log ──────────────────────────────────────────────────────

    def log_usage(
        self,
        *,
        account_id: int,
        method: str,
        endpoint: str,
        status_code: int,
        latency_ms: int,
        user_id: Optional[int] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        """Записать факт использования токена. Сам токен НЕ логируется."""
        event = AuditEvent(
            account_id=account_id,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=latency_ms,
            user_id_hash=hash_user_id(user_id) if user_id is not None else None,
            error_detail=error_detail,
        )
        self._audit.record(event)


__all__ = ["TokenRepository", "TokenEncryptionError"]

"""
Audit log использования брокерского токена.

Принцип: каждый вызов к Tinkoff API (через наши клиенты) должен оставлять
след в таблице `token_audit_log` — кто, когда, какой метод, сколько занял,
какой статус. Сам токен НЕ сохраняется ни в каком виде.

Используется в orchestrator/pipeline (PR 5+): обёртка вокруг каждого
external call.

Реализация умышленно sync (SQLAlchemy 1.x-style session): аудит-запись —
маленькая транзакция, асинхронные нюансы оверкилл; вызываем через
`asyncio.to_thread()` из async кода когда нужно.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from time import monotonic
from typing import Iterator, Optional

from sqlalchemy.orm import Session

from database import SessionLocal
from logger import get_logger
from models import TokenAuditLogORM
from utils.datetime_utils import utc_now_naive

log = get_logger("token_audit")


# ────────────────────────────────────────────────────────────────────────


def hash_user_id(user_id: int | str) -> str:
    """SHA-256 hash без соли (соль не нужна — мы маскируем PII в логах,
    а не защищаем пароли). Возвращает hex 64 символа."""
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEvent:
    account_id: int
    method: str
    endpoint: str
    status_code: int
    latency_ms: int
    user_id_hash: Optional[str] = None
    error_detail: Optional[str] = None


class TokenAuditRecorder:
    """
    Пишет события в `token_audit_log`. Использовать как singleton.

    Опционально принимает session_factory для тестов — иначе берёт
    глобальный `database.SessionLocal`.
    """

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or SessionLocal

    def record(self, event: AuditEvent) -> None:
        """Синхронная запись одной audit-строки."""
        session: Session = self._session_factory()
        try:
            row = TokenAuditLogORM(
                account_id=event.account_id,
                user_id_hash=event.user_id_hash,
                method=event.method,
                endpoint=event.endpoint,
                status_code=event.status_code,
                latency_ms=event.latency_ms,
                error_detail=(event.error_detail[:512] if event.error_detail else None),
                created_at=utc_now_naive(),
            )
            session.add(row)
            session.commit()
        except Exception as exc:
            # Audit log НЕ должен падать каскадом и валить sync. Логируем
            # и продолжаем — в худшем случае потеряем audit-запись.
            log.warning(f"audit insert failed: {exc}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()


# ── helper для измерения latency ───────────────────────────────────────


@contextmanager
def measure_latency() -> Iterator[dict]:
    """
    `with measure_latency() as m: ...`  — потом `m['latency_ms']` готов.

    Использование (внутри клиента или pipeline):

        rec = TokenAuditRecorder()
        with measure_latency() as m:
            try:
                result = await client.fetch_operations_cursor(...)
                status = 0  # gRPC OK
            except BrokerError as exc:
                status = grpc_status_code_int(exc)
                raise
            finally:
                rec.record(AuditEvent(account_id=..., method="fetch_operations_cursor",
                                       endpoint=client_factory.endpoint,
                                       status_code=status,
                                       latency_ms=m['latency_ms'],
                                       error_detail=...))
    """
    start = monotonic()
    box: dict = {"latency_ms": 0}
    try:
        yield box
    finally:
        box["latency_ms"] = int((monotonic() - start) * 1000)

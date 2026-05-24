"""
PR 26 — Admin audit log helpers.

Все admin actions пишутся в `admin_audit_log` через `audit_admin_action()`.
Используется в `routers/admin.py` и `routers/payments.py` (impersonate, refunds).

Принципы:
- Записываем actor, action, target, details, IP, User-Agent.
- НЕ записываем токены, пароли, payment_id, raw PII.
- Если запись падает — НЕ ломаем основной endpoint (best-effort), но
  логируем в Sentry.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

import models
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("admin_audit")


def audit_admin_action(
    db: Session,
    *,
    actor_user_id: int,
    action: str,
    target_user_id: Optional[int] = None,
    target_account_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Записать admin-действие в audit log. Best-effort — не падает."""
    try:
        ip = None
        ua = None
        if request is not None:
            # X-Forwarded-For respect — но truncate (256-char limit).
            ip = (
                request.headers.get("x-forwarded-for", "")
                .split(",")[0]
                .strip()
                or (request.client.host if request.client else None)
            )
            if ip:
                ip = ip[:64]
            ua = request.headers.get("user-agent", "")[:256] or None

        entry = models.AdminAuditLogORM(
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            target_account_id=target_account_id,
            details=_sanitize_details(details),
            ip_address=ip,
            user_agent=ua,
            created_at=utc_now_naive(),
        )
        db.add(entry)
        db.commit()
    except Exception:
        log.exception(
            "admin_audit write failed (action=%s actor=%s target_user=%s)",
            action,
            actor_user_id,
            target_user_id,
        )
        try:
            db.rollback()
        except Exception:
            pass


# Список ключей, которые НИКОГДА не должны попасть в audit details.
_SENSITIVE_KEYS = frozenset({
    "password",
    "hashed_password",
    "token",
    "api_token",
    "encrypted_token",
    "secret",
    "authorization",
    "x-csrf-token",
    "session",
    "cookie",
})


def _sanitize_details(details: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Удаляем sensitive ключи из details. Recursive shallow."""
    if not details:
        return details
    out: dict[str, Any] = {}
    for k, v in details.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "[REDACTED]"
        elif isinstance(v, dict):
            out[k] = _sanitize_details(v)
        else:
            out[k] = v
    return out

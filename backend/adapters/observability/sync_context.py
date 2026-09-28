"""
Sync-scoped context for logging and Sentry breadcrumbs.

Использование (в pipeline.py):

    from adapters.observability.sync_context import bind_sync_context, clear_sync_context

    async def run(...):
        sync_id = uuid.uuid4().hex[:12]
        bind_sync_context(sync_id=sync_id, account_id=self._account_id, broker_account_id=self._broker_account_id)
        try:
            ...
        finally:
            clear_sync_context()

Что даёт:

1. `LogRecord.sync_id`, `LogRecord.account_id_hash` доступны в форматтере
   логов (если formatter использует %(sync_id)s).
2. Sentry scope получает те же ключи через `sentry_sdk.set_tag(...)` —
   и каждое последующее событие в этом scope содержит их.

PII: `account_id` хешируется (sha256, первые 12 символов) — мы не пишем
сам user_id в логи Sentry. Tinkoff `broker_account_id` числовой и не PII.
"""

from __future__ import annotations

import contextvars
import hashlib
import logging
from typing import Any, Optional

# contextvars обновляются строго в рамках async-контекста, не утекают
# между задачами.
_sync_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "empirik_sync_id", default=None
)
_account_hash_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "empirik_account_hash", default=None
)
_broker_account_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "empirik_broker_account", default=None
)


def _hash_account_id(account_id: int | str) -> str:
    return hashlib.sha256(str(account_id).encode("utf-8")).hexdigest()[:12]


def bind_sync_context(
    *,
    sync_id: str,
    account_id: int,
    broker_account_id: str,
) -> dict[contextvars.ContextVar, contextvars.Token]:
    """
    Установить контекст. Возвращает tokens для последующего `reset`.
    Также проставляет Sentry tags, если SDK инициализирован.
    """
    tokens = {
        _sync_id_var: _sync_id_var.set(sync_id),
        _account_hash_var: _account_hash_var.set(_hash_account_id(account_id)),
        _broker_account_var: _broker_account_var.set(broker_account_id),
    }

    # Sentry: ставим теги только если SDK уже инициализирован.
    try:
        import sentry_sdk  # type: ignore

        if sentry_sdk.Hub.current.client is not None:
            scope = sentry_sdk.Hub.current.scope
            scope.set_tag("sync_id", sync_id)
            scope.set_tag("account_hash", _hash_account_id(account_id))
            scope.set_tag("broker_account_id", broker_account_id)
    except Exception:
        # observability не должна валить основной flow
        pass

    return tokens


def clear_sync_context(tokens: dict[contextvars.ContextVar, contextvars.Token]) -> None:
    """Откатить значения в исходное состояние (None) при выходе из pipeline.run()."""
    for var, tok in tokens.items():
        try:
            var.reset(tok)
        except Exception:
            pass
    # Sentry tags не reset'им — они привязаны к текущему request scope,
    # пересоздадутся при следующем pipeline.

    try:
        import sentry_sdk  # type: ignore

        if sentry_sdk.Hub.current.client is not None:
            scope = sentry_sdk.Hub.current.scope
            for key in ("sync_id", "account_hash", "broker_account_id"):
                scope.remove_tag(key)
    except Exception:
        pass


def current_sync_context() -> dict[str, Any]:
    """Snapshot текущего контекста — для extra'ов или повторной передачи."""
    return {
        "sync_id": _sync_id_var.get(),
        "account_hash": _account_hash_var.get(),
        "broker_account_id": _broker_account_var.get(),
    }


class SyncContextFilter(logging.Filter):
    """
    Logging filter, добавляющий sync_id / account_hash / broker_account_id
    в каждую запись логгера. Использовать в `dictConfig` или вручную:

        logger.addFilter(SyncContextFilter())

    Если context не задан — поля будут "-".
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.sync_id = _sync_id_var.get() or "-"  # type: ignore[attr-defined]
        record.account_hash = _account_hash_var.get() or "-"  # type: ignore[attr-defined]
        record.broker_account_id = _broker_account_var.get() or "-"  # type: ignore[attr-defined]
        return True

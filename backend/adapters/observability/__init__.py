"""
Observability helpers (PR 16):

* `sync_context` — bind/unbind контекстных полей (sync_id, account_hash)
  для всех log-записей внутри одного pipeline-вызова.

Сейчас (PR 16) используем легковесную обёртку над contextvars + std logging.
При желании можно перейти на structlog без изменения вызывающего кода.
"""

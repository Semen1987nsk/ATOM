"""PERF-08a: composite-индексы для горячих запросов.

Revision ID: 0027_perf_indexes
Revises: 0026_auth_hardening
Create Date: 2026-05-26 00:00:00.000000

Sprint 3, Task 3.1.

1. `ix_operations_state_type_executed` на operations(state, operation_type,
   executed_at). Использует pipeline.py при расчёте варм-маржи
   (where state='executed' AND operation_type IN (...)) и capital_service.

2. `ix_access_log_status_created` на access_log(status_code, created_at).
   Использует admin-роут `/admin/errors/recent`:
   `where status_code >= 400 ORDER BY created_at DESC`.

GIN на `Trade.tags` — отдельная задача 3.2.

Postgres-ветка: `CREATE INDEX CONCURRENTLY IF NOT EXISTS` внутри
`autocommit_block()`, чтобы не блокировать таблицы под нагрузкой
(access_log на проде может вырасти до >1M строк).

SQLite-ветка (dev): обычный `op.create_index` — CONCURRENTLY там нет,
блокировка таблицы на момент создания индекса для dev-БД допустима.

idempotency:
  * Postgres — `IF NOT EXISTS` / `IF EXISTS`.
  * SQLite — alembic op.create_index/drop_index без if-clauses; повторный
    apply не происходит на чистой истории, а тестовый roundtrip
    (up→down→up) гарантирован конструкцией миграции, не флагом.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0027_perf_indexes"
down_revision: Union[str, Sequence[str], None] = "0026_auth_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_OPERATIONS = "ix_operations_state_type_executed"
_INDEX_ACCESS_LOG = "ix_access_log_status_created"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        # CREATE INDEX CONCURRENTLY обязан выполняться вне транзакции —
        # alembic предоставляет autocommit_block() для этого.
        with op.get_context().autocommit_block():
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                f"{_INDEX_OPERATIONS} "
                "ON operations (state, operation_type, executed_at)"
            )
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                f"{_INDEX_ACCESS_LOG} "
                "ON access_log (status_code, created_at)"
            )
    else:
        op.create_index(
            _INDEX_OPERATIONS,
            "operations",
            ["state", "operation_type", "executed_at"],
            unique=False,
        )
        op.create_index(
            _INDEX_ACCESS_LOG,
            "access_log",
            ["status_code", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(
                f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_ACCESS_LOG}"
            )
            op.execute(
                f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_OPERATIONS}"
            )
    else:
        op.drop_index(_INDEX_ACCESS_LOG, table_name="access_log")
        op.drop_index(_INDEX_OPERATIONS, table_name="operations")

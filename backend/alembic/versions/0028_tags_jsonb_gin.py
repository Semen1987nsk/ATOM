"""PERF-08b: Trade.tags JSON→JSONB + GIN-индекс (Postgres-only).

Revision ID: 0028_tags_jsonb_gin
Revises: 0027_perf_indexes
Create Date: 2026-05-26 00:00:00.000000

Sprint 3, Task 3.2. Перевод `trades.tags` на JSONB на проде позволяет
заменить медленный Python-loop в `/stats?tag=...` (загружает все трейды
аккаунта и фильтрует в питоне) на SQL-предикат `tags @> '["FOMO"]'`.

GIN-индекс `ix_trades_tags_gin` (jsonb_path_ops) — компактнее обычного
GIN и поддерживает только containment-запросы (что нам и нужно).

SQLite-ветка — no-op: `JSON` колонка остаётся как есть, в роутере
сохранён Python-loop fallback (см. routers/stats.py).

Postgres-ветка использует:
  * `ALTER COLUMN ... TYPE JSONB USING tags::jsonb` — миграция данных
    in-place. SQL `JSON` → `JSONB` совместимы при кастинге через `::jsonb`.
  * `CREATE INDEX CONCURRENTLY IF NOT EXISTS` внутри `autocommit_block()`,
    чтобы не блокировать таблицу `trades` под нагрузкой.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0028_tags_jsonb_gin"
down_revision: Union[str, Sequence[str], None] = "0027_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_TAGS_GIN = "ix_trades_tags_gin"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite (dev/tests): JSON остаётся, GIN не нужен.
        return

    op.alter_column(
        "trades",
        "tags",
        type_=postgresql.JSONB(),
        postgresql_using="tags::jsonb",
    )
    # CREATE INDEX CONCURRENTLY обязан выполняться вне транзакции.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            f"{_INDEX_TAGS_GIN} "
            "ON trades USING GIN (tags jsonb_path_ops)"
        )


def downgrade() -> None:
    if not _is_postgres():
        return

    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_TAGS_GIN}")
    op.alter_column(
        "trades",
        "tags",
        type_=postgresql.JSON(),
        postgresql_using="tags::json",
    )

"""phase1: trade dedup constraint, composite index, leverage/r_multiple precision

Revision ID: a1b2c3d4e5f6
Revises: 798ef8d328bd
Create Date: 2026-05-04 00:00:00.000000

Phase 1 fixes:
1. UniqueConstraint(account_id, symbol, entry_at, direction) — защита от дублей
   при гонках при импорте. Раньше дедуп жил только в Python.
2. Composite index (account_id, entry_at, exit_at) — частый паттерн в
   stats / analytics: WHERE account_id = ? ORDER BY entry_at в диапазоне.
3. leverage Float -> Numeric(10,6); r_multiple Float -> Numeric(10,6) —
   финансовые величины не должны храниться как Float (накопление ошибок
   при умножениях).

ВНИМАНИЕ: перед apply этой миграции нужно убедиться, что в trades нет
дубликатов по ключу (account_id, symbol, entry_at, direction), иначе
CREATE UNIQUE INDEX упадёт. Скрипт upgrade() сначала чистит дубликаты,
оставляя строку с минимальным id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '798ef8d328bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Перед добавлением UniqueConstraint удаляем существующие дубликаты,
    #    оставляя строку с минимальным id (самую раннюю запись).
    op.execute(sa.text("""
        DELETE FROM trades
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY account_id, symbol, entry_at, direction
                           ORDER BY id ASC
                       ) AS rn
                FROM trades
            ) ranked
            WHERE rn > 1
        )
    """))

    # 2. UniqueConstraint на (account_id, symbol, entry_at, direction).
    #    SQLite требует batch_alter_table для ADD CONSTRAINT.
    with op.batch_alter_table('trades') as batch_op:
        batch_op.create_unique_constraint(
            'uq_trades_dedup',
            ['account_id', 'symbol', 'entry_at', 'direction'],
        )

    # 3. Composite index под stats/analytics-запросы.
    op.create_index(
        'ix_trades_account_entry_exit',
        'trades',
        ['account_id', 'entry_at', 'exit_at'],
    )

    # 4. leverage Float → Numeric(10,6). r_multiple Float → Numeric(10,6).
    #    SQLite не поддерживает ALTER COLUMN TYPE напрямую — batch_alter_table
    #    создаст временную таблицу, скопирует данные и переименует.
    with op.batch_alter_table('trades') as batch_op:
        batch_op.alter_column(
            'leverage',
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=10, scale=6),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'r_multiple',
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=10, scale=6),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('trades') as batch_op:
        batch_op.alter_column(
            'r_multiple',
            existing_type=sa.Numeric(precision=10, scale=6),
            type_=sa.Float(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'leverage',
            existing_type=sa.Numeric(precision=10, scale=6),
            type_=sa.Float(),
            existing_nullable=True,
        )

    op.drop_index('ix_trades_account_entry_exit', table_name='trades')

    with op.batch_alter_table('trades') as batch_op:
        batch_op.drop_constraint('uq_trades_dedup', type_='unique')

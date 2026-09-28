"""Inspect-гарды для идемпотентных миграций (DATA-01).

0001_initial_baseline строит ФИНАЛЬНУЮ схему через Base.metadata.create_all
из текущих models.py. Поэтому на чистой БД все объекты, которые миграции
0002+ добавляют, уже существуют. Каждая миграция обязана проверять
существование объекта перед create/drop — эти helpers дают единый способ.

Импорт из миграций: `from _guards import has_column, ...` — env.py добавляет
каталог alembic/ в sys.path до загрузки version-скриптов.
"""
from __future__ import annotations

import sqlalchemy as sa


def has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def has_index(bind, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return index in {ix["name"] for ix in inspector.get_indexes(table)}


def has_unique_constraint(bind, table: str, name: str) -> bool:
    """Именованный UNIQUE constraint. На SQLite unique иногда отражается
    как unique-индекс — проверяем оба источника."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    constraint_names = {
        uc["name"] for uc in inspector.get_unique_constraints(table)
    }
    if name in constraint_names:
        return True
    unique_index_names = {
        ix["name"] for ix in inspector.get_indexes(table) if ix.get("unique")
    }
    return name in unique_index_names


def missing_columns(bind, table: str, columns: dict) -> dict:
    """Подмножество columns (name → sa.Column), которых нет в table."""
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(table)}
    return {name: col for name, col in columns.items() if name not in existing}

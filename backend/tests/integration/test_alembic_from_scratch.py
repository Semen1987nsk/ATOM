"""DATA-01: `alembic upgrade head` обязан проходить на ПУСТОЙ БД.

Sprint 6.5, Batch 4. Исторически цепочка ломалась: 0001 строит ФИНАЛЬНУЮ
схему через `Base.metadata.create_all` (включая uq_trades_dedup_v2), после
чего 0006 падал на drop несуществующего `uq_trades_dedup`, а 0007+ — на
duplicate column. Лечение: все миграции 0002+ идемпотентны через
inspect-гарды (alembic/_guards.py).

Два инварианта:
  1. upgrade head на пустом SQLite-файле проходит без исключений;
  2. итоговая схема эквивалентна create_all-схеме из текущих models.py
     (мягкое сравнение: множества таблиц и колонок по именам, без типов).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

# Бэкенд должен быть в sys.path, чтобы env.py смог импортнуть `models`/`config`.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _make_alembic_cfg(db_url: str):
    """Alembic Config с переопределённым URL — env.py читает sqlalchemy.url."""
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture
def sqlite_url(tmp_path, monkeypatch):
    """Изолированная sqlite-БД + подмена DATABASE_URL для env.py."""
    db_file = tmp_path / "alembic_from_scratch.sqlite"
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)

    import config

    monkeypatch.setattr(config.settings, "DATABASE_URL", url, raising=False)
    return url


def test_upgrade_head_on_empty_db(sqlite_url):
    """Чистая БД → `alembic upgrade head` без исключений и version=head."""
    from alembic import command
    from alembic.script import ScriptDirectory

    cfg = _make_alembic_cfg(sqlite_url)
    command.upgrade(cfg, "head")  # не должно бросить

    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = create_engine(sqlite_url)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).fetchone()
    engine.dispose()
    assert row is not None, "alembic_version пуста после upgrade head"
    assert row[0] == head, f"version_num={row[0]!r}, ожидали head={head!r}"


def test_migrated_schema_matches_create_all(sqlite_url, tmp_path):
    """Схема после upgrade head ≡ create_all-схеме (таблицы + колонки)."""
    from alembic import command

    from models import Base

    # --- путь 1: миграции с нуля ---
    cfg = _make_alembic_cfg(sqlite_url)
    command.upgrade(cfg, "head")
    migrated = create_engine(sqlite_url)

    # --- путь 2: эталон из текущих моделей ---
    ref_file = tmp_path / "create_all_reference.sqlite"
    reference = create_engine(f"sqlite:///{ref_file.as_posix()}")
    Base.metadata.create_all(bind=reference)

    mig_inspector = sa.inspect(migrated)
    ref_inspector = sa.inspect(reference)

    mig_tables = set(mig_inspector.get_table_names()) - {"alembic_version"}
    ref_tables = set(ref_inspector.get_table_names())

    assert ref_tables - mig_tables == set(), (
        f"После миграций отсутствуют таблицы: {sorted(ref_tables - mig_tables)}"
    )
    assert mig_tables - ref_tables == set(), (
        f"Миграции создали лишние таблицы: {sorted(mig_tables - ref_tables)}"
    )

    mismatches = {}
    for table in sorted(ref_tables):
        mig_cols = {c["name"] for c in mig_inspector.get_columns(table)}
        ref_cols = {c["name"] for c in ref_inspector.get_columns(table)}
        if mig_cols != ref_cols:
            mismatches[table] = {
                "missing": sorted(ref_cols - mig_cols),
                "extra": sorted(mig_cols - ref_cols),
            }
    assert mismatches == {}, f"Расхождения колонок: {mismatches}"

    migrated.dispose()
    reference.dispose()

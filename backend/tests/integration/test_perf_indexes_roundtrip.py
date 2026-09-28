"""PERF-08a: alembic roundtrip для миграции 0027_perf_indexes на SQLite.

Sprint 3, Task 3.1. Проверяем что миграция:
  * применяется поверх pre-stamped 0026 (upgrade head → 0027),
  * откатывается без ошибок (downgrade -1 → 0026),
  * применяется повторно (upgrade head) — нет дубликат-конфликтов.

Также проверяем, что после upgrade оба новых индекса физически существуют
в sqlite_master, а после downgrade — исчезают.

Почему не «upgrade head с нуля»: миграция 0006_pr7_trade_unique_with_exit
ломает чистый upgrade на SQLite (batch_alter_table.drop_constraint на
несуществующем `uq_trades_dedup`). Это pre-existing bug, не относится к
PERF-08a. Поэтому стартуем со схемы из `models.Base.metadata.create_all`,
помечаем БД как уже-на-0026 через `alembic stamp`, и тестируем именно
upgrade 0026 → 0027 → 0026 → 0027.

Postgres-ветка `CREATE INDEX CONCURRENTLY` отдельно не тестируется
(требует живого PG-инстанса в CI); SQLite-roundtrip достаточен для
поведенческого регресса композитных индексов и down-логики.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

# Бэкенд должен быть в sys.path, чтобы env.py смог импортнуть `models`/`config`.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


REVISION_PERF = "0027_perf_indexes"
REVISION_PREV = "0026_auth_hardening"

INDEX_OPERATIONS = "ix_operations_state_type_executed"
INDEX_ACCESS_LOG = "ix_access_log_status_created"


def _make_alembic_cfg(db_url: str):
    """Alembic Config с переопределённым URL — env.py читает sqlalchemy.url."""
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _index_exists(engine, name: str) -> bool:
    """sqlite_master содержит запись для нашего индекса?"""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": name},
        ).fetchone()
        return row is not None


@pytest.fixture
def sqlite_url(tmp_path, monkeypatch):
    """Изолированная sqlite-БД + подмена DATABASE_URL для env.py.

    env.py читает `settings.DATABASE_URL` — патчим os.environ + уже
    созданный `config.settings`.
    """
    db_file = tmp_path / "alembic_roundtrip.sqlite"
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)

    import config

    monkeypatch.setattr(config.settings, "DATABASE_URL", url, raising=False)
    return url


def test_alembic_0027_roundtrip_sqlite(sqlite_url):
    """upgrade 0026→0027 → downgrade 0026 → upgrade 0027, всё зелёное.

    Фокус теста — миграция 0027 в изоляции. Таргетим upgrade именно на
    0027 (не на head), чтобы позднее добавленные head-миграции (0028+)
    не мешали проверке down-step'а.
    """
    from alembic import command

    from models import Base

    cfg = _make_alembic_cfg(sqlite_url)
    engine = create_engine(sqlite_url)

    # 0. Готовим схему «как-будто после 0026». Базовый upgrade с zero
    # сломан pre-existing багом в 0006 — обходим через create_all + stamp.
    Base.metadata.create_all(bind=engine)
    # Сносим именно ТЕ индексы, которые добавит 0027 — Base.metadata.create_all
    # уже создал бы их из models.py, если бы они там были (в текущей версии
    # моделей композитных нет, так что чистый старт; стрэйф-чек защитный).
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX_OPERATIONS}"))
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX_ACCESS_LOG}"))
    command.stamp(cfg, REVISION_PREV)

    # 1. upgrade 0027 — единственный шаг 0026 → 0027.
    command.upgrade(cfg, REVISION_PERF)
    assert _index_exists(engine, INDEX_OPERATIONS), (
        f"{INDEX_OPERATIONS} должен существовать после upgrade {REVISION_PERF}"
    )
    assert _index_exists(engine, INDEX_ACCESS_LOG), (
        f"{INDEX_ACCESS_LOG} должен существовать после upgrade {REVISION_PERF}"
    )

    # 2. downgrade → 0026, индексы исчезают.
    command.downgrade(cfg, REVISION_PREV)
    assert not _index_exists(engine, INDEX_OPERATIONS), (
        f"{INDEX_OPERATIONS} должен исчезнуть после downgrade {REVISION_PREV}"
    )
    assert not _index_exists(engine, INDEX_ACCESS_LOG), (
        f"{INDEX_ACCESS_LOG} должен исчезнуть после downgrade {REVISION_PREV}"
    )

    # 3. upgrade 0027 ещё раз — повторное применение без конфликтов.
    command.upgrade(cfg, REVISION_PERF)
    assert _index_exists(engine, INDEX_OPERATIONS)
    assert _index_exists(engine, INDEX_ACCESS_LOG)

    engine.dispose()


def test_alembic_0028_roundtrip_sqlite(sqlite_url):
    """PERF-08b: миграция 0028 на SQLite = no-op (JSON остаётся, GIN не нужен).

    Проверяем что upgrade 0027→0028 и downgrade 0028→0027 проходят без ошибок,
    а композитные индексы из 0027 не страдают.
    """
    from alembic import command

    from models import Base

    cfg = _make_alembic_cfg(sqlite_url)
    engine = create_engine(sqlite_url)

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX_OPERATIONS}"))
        conn.execute(text(f"DROP INDEX IF EXISTS {INDEX_ACCESS_LOG}"))
    command.stamp(cfg, REVISION_PREV)

    # 0026 → 0027 → 0028 (head)
    command.upgrade(cfg, "head")
    assert _index_exists(engine, INDEX_OPERATIONS)
    assert _index_exists(engine, INDEX_ACCESS_LOG)

    # downgrade 0028 → 0027 на SQLite — no-op, индексы 0027 уцелели.
    command.downgrade(cfg, REVISION_PERF)
    assert _index_exists(engine, INDEX_OPERATIONS)
    assert _index_exists(engine, INDEX_ACCESS_LOG)

    # upgrade head повторно — без конфликтов.
    command.upgrade(cfg, "head")
    assert _index_exists(engine, INDEX_OPERATIONS)
    assert _index_exists(engine, INDEX_ACCESS_LOG)

    engine.dispose()

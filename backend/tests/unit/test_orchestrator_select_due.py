"""SYNC-10: `_select_due_connection_ids` делает один SELECT, не 1+N.

Раньше код делал первый SELECT по списку id и затем перебирал id'шники
с отдельным `session.query(BrokerConnection).filter_by(id=cid).first()`
на каждый → 1+N запросов при N подключениях.

После рефакторинга — один SELECT отдаёт ВСЕ нужные колонки сразу
(`id`, `circuit_open_until`, `last_sync_at`, `sync_interval_minutes`),
дальше фильтрация в Python.

Тест меряет реальное количество SQL запросов через
`event.listen(engine, "before_cursor_execute", ...)`.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from application.sync.orchestrator import TinkoffSyncOrchestrator
from models import Account, Base, BrokerConnection, BrokerType, User
from utils.datetime_utils import utc_now_naive


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def engine_and_factory(tmp_path: Path):
    """Изолированный SQLite engine + session_factory."""
    db_path = tmp_path / "test_select_due.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield engine, Session
    engine.dispose()


@pytest.fixture
def seed_50_broker_connections(engine_and_factory):
    """Заполняем 50 BrokerConnection с разными due-условиями.

    Расклад:
    - 25 без `last_sync_at` (всегда due);
    - 15 с last_sync_at = now - 3h, interval=60 (due);
    - 10 с last_sync_at = now - 10min, interval=60 (НЕ due).

    Возвращаем (engine, Session, total, expected_due_count).
    """
    engine, Session = engine_and_factory
    now = utc_now_naive()
    expected_due = 0

    with Session() as session:
        user = User(email="sync10@test.local", name="t", is_active=1)
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        session.add(account)
        session.flush()

        for i in range(50):
            if i < 25:
                last_sync_at = None
                interval = 60
                is_due = True
            elif i < 40:
                last_sync_at = now - timedelta(hours=3)
                interval = 60
                is_due = True
            else:
                last_sync_at = now - timedelta(minutes=10)
                interval = 60
                is_due = False

            conn = BrokerConnection(
                account_id=account.id,
                broker=BrokerType.TINKOFF,
                broker_account_id=f"acc-{i}",
                api_token=f"ct-{i}",
                is_active=True,
                auto_sync_enabled=True,
                last_sync_at=last_sync_at,
                sync_interval_minutes=interval,
            )
            session.add(conn)
            if is_due:
                expected_due += 1
        session.commit()

    return engine, Session, 50, expected_due


@pytest.fixture
def query_counter(engine_and_factory):
    """Считает сколько SQL запросов выполнил engine во время теста."""
    engine, _ = engine_and_factory
    counts = {"n": 0, "stmts": []}

    def _count(_conn, _cursor, statement, *_args, **_kw):
        counts["n"] += 1
        counts["stmts"].append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", _count)


# ── tests ────────────────────────────────────────────────────────────


def test_select_due_runs_single_query(seed_50_broker_connections, query_counter):
    """50 broker connections → один SELECT (не 51)."""
    engine, Session, total, expected_due = seed_50_broker_connections
    assert total == 50

    orchestrator = TinkoffSyncOrchestrator(session_factory=Session)

    # Сбрасываем счётчик после setup'а фикстуры (там были INSERT'ы).
    query_counter["n"] = 0
    query_counter["stmts"].clear()

    ids = orchestrator._select_due_connection_ids()

    assert len(ids) == expected_due, (
        f"expected {expected_due} due connections, got {len(ids)}"
    )
    assert query_counter["n"] == 1, (
        f"N+1 leak: expected 1 SELECT, got {query_counter['n']}. "
        f"Statements: {query_counter['stmts']}"
    )


def test_select_due_respects_circuit_open(engine_and_factory, query_counter):
    """Подключение с circuit_open_until > now пропускается; SELECT всё ещё один."""
    engine, Session = engine_and_factory
    now = utc_now_naive()

    with Session() as session:
        user = User(email="circuit@test.local", name="t", is_active=1)
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        session.add(account)
        session.flush()
        # 2 due, у одного circuit открыт
        conn_a = BrokerConnection(
            account_id=account.id,
            broker=BrokerType.TINKOFF,
            broker_account_id="A",
            api_token="t-a",
            is_active=True,
            auto_sync_enabled=True,
            last_sync_at=None,
            sync_interval_minutes=60,
            circuit_open_until=now + timedelta(hours=1),
        )
        conn_b = BrokerConnection(
            account_id=account.id,
            broker=BrokerType.TINKOFF,
            broker_account_id="B",
            api_token="t-b",
            is_active=True,
            auto_sync_enabled=True,
            last_sync_at=None,
            sync_interval_minutes=60,
        )
        session.add_all([conn_a, conn_b])
        session.commit()
        expected_id = conn_b.id

    orchestrator = TinkoffSyncOrchestrator(session_factory=Session)
    query_counter["n"] = 0
    query_counter["stmts"].clear()

    ids = orchestrator._select_due_connection_ids()

    assert ids == [expected_id]
    assert query_counter["n"] == 1, (
        f"expected 1 SELECT, got {query_counter['n']}: {query_counter['stmts']}"
    )


def test_select_due_filters_inactive_user(engine_and_factory, query_counter):
    """User.is_active != 1 → подключения этого юзера пропускаются."""
    engine, Session = engine_and_factory

    with Session() as session:
        # Активный юзер
        u_active = User(email="active@test.local", name="t", is_active=1)
        # Деактивированный юзер
        u_inactive = User(email="inactive@test.local", name="t", is_active=0)
        session.add_all([u_active, u_inactive])
        session.flush()
        a_active = Account(user_id=u_active.id, name="A", currency="RUB")
        a_inactive = Account(user_id=u_inactive.id, name="B", currency="RUB")
        session.add_all([a_active, a_inactive])
        session.flush()

        conn_active = BrokerConnection(
            account_id=a_active.id,
            broker=BrokerType.TINKOFF,
            broker_account_id="A",
            api_token="t-a",
            is_active=True,
            auto_sync_enabled=True,
            last_sync_at=None,
            sync_interval_minutes=60,
        )
        conn_inactive = BrokerConnection(
            account_id=a_inactive.id,
            broker=BrokerType.TINKOFF,
            broker_account_id="B",
            api_token="t-b",
            is_active=True,
            auto_sync_enabled=True,
            last_sync_at=None,
            sync_interval_minutes=60,
        )
        session.add_all([conn_active, conn_inactive])
        session.commit()
        expected_id = conn_active.id

    orchestrator = TinkoffSyncOrchestrator(session_factory=Session)
    query_counter["n"] = 0
    query_counter["stmts"].clear()

    ids = orchestrator._select_due_connection_ids()

    assert ids == [expected_id]
    assert query_counter["n"] == 1

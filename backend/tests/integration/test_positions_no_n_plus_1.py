"""PERF-06: /trades/positions делает константное число SQL-запросов,
не N+1 на каждую открытую позицию.

До правки в `routers/trades.py::read_position_trades` для каждой открытой группы
делался отдельный `db.query(PositionORM).filter(...).first()`. При 30 открытых
позициях это ≥30 round-trip'ов в Postgres вместо одного `IN`-запроса.

Тест считает `before_cursor_execute` события на test-engine и требует,
чтобы общее число SQL-запросов было ≤ 10 при 30 открытых позициях.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from fastapi.testclient import TestClient

from main import app
from models import Account, Base, PositionORM, Trade, TradeDirection, User
from database import get_db
import auth_service


@pytest.fixture
def test_app_with_counter():
    """In-memory app + counter SQL-запросов на test-engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    counts = {"n": 0, "active": False}

    def _count(*_args, **_kw):
        if counts["active"]:
            counts["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db_session = TestingSessionLocal()
    try:
        yield {
            "client": TestClient(app),
            "db": db_session,
            "counts": counts,
        }
    finally:
        db_session.close()
        event.remove(engine, "before_cursor_execute", _count)
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def _setup_user(db):
    u = User(
        email="perf06@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
        is_admin=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(user_id=u.id, name="Main", currency="RUB")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, acc, token


def _seed_30_open_positions(db, account_id: int):
    """Создаёт 30 открытых трейдов с уникальными instrument_uid + parallel
    PositionORM-rows для каждой позиции."""
    base = datetime(2026, 5, 1, 10, 0)
    for i in range(30):
        uid = f"uid-instr-{i:02d}"
        db.add(
            Trade(
                account_id=account_id,
                symbol=f"INSTR{i:02d}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                quantity=Decimal("10"),
                entry_at=base,
                exit_at=None,  # open
                currency="RUB",
                data_source="tinkoff_v2",
                instrument_uid=uid,
                position_id=1000 + i,
                commission=Decimal("0"),
            )
        )
        db.add(
            PositionORM(
                account_id=account_id,
                instrument_uid=uid,
                instrument_type="share",
                quantity=10,
                avg_entry_price=Decimal("100"),
                current_price=Decimal("105"),
                unrealized_pnl=Decimal("50"),
                currency="rub",
            )
        )
    db.commit()


def test_position_trades_no_n_plus_1(test_app_with_counter):
    """30 открытых позиций → SQL-запросов должно быть ≤ 10, не 30+.

    До правки PERF-06: ~32 (1 трейды + 30 PositionORM + auth + access_log).
    После: ≤ 10 (трейды + один IN + auth + access_log + sundry).
    """
    db = test_app_with_counter["db"]
    client = test_app_with_counter["client"]
    counts = test_app_with_counter["counts"]

    _, acc, token = _setup_user(db)
    _seed_30_open_positions(db, acc.id)

    # Начинаем считать только запросы запроса /trades/positions, не seed-инсерты.
    counts["n"] = 0
    counts["active"] = True
    try:
        resp = client.get(
            "/trades/positions?status=open",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        counts["active"] = False

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 30, f"ожидали 30 открытых позиций, получили {len(body)}"

    # Smoke-check: unrealized_pnl действительно прокинут (50 на каждую позицию).
    assert all(p["unrealized_pnl"] == pytest.approx(50.0) for p in body), (
        "unrealized_pnl должен браться из префетченных PositionORM"
    )

    assert counts["n"] <= 10, (
        f"PERF-06: ожидали ≤10 SQL-запросов, получили {counts['n']} "
        f"(N+1 по PositionORM не починен)"
    )

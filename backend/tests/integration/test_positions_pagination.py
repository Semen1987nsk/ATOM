"""PERF-10: /trades/positions выполняет реальную пагинацию по группам.

До правки skip/limit передавались параметрами, но slice применялся
финально над уже построенным списком из ~5000 PositionTrade — это
не давало ни latency, ни memory выигрыша.

Тесты проверяют:
1. limit=10 возвращает ровно 10 групп при наличии 30.
2. skip=10 не пересекается с skip=0 (страницы дизъюнктны).
3. skip=0 + skip=10 + skip=20 (limit=10 каждая) покрывают все 30
   уникальных position_id без потерь.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
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
def client_with_db():
    """In-memory app + session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

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
        }
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def _setup_user(db):
    u = User(
        email="perf10-pos@test.com",
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


def _seed_30_positions(db, account_id: int, *, closed: bool = True):
    """Создаёт 30 позиций с уникальными position_id, разнесёнными
    по времени (entry_at сдвигается на i часов вперёд от base).
    """
    base = datetime(2026, 5, 1, 10, 0)
    for i in range(30):
        uid = f"uid-pp-{i:02d}"
        entry = base + timedelta(hours=i)
        exit_at = entry + timedelta(hours=1) if closed else None
        exit_price = Decimal("110") if closed else None
        db.add(
            Trade(
                account_id=account_id,
                symbol=f"PP{i:02d}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=exit_price,
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=exit_at,
                currency="RUB",
                data_source="tinkoff_v2",
                instrument_uid=uid,
                position_id=2000 + i,
                commission=Decimal("0"),
                pnl=Decimal("100") if closed else None,
                net_pnl=Decimal("100") if closed else None,
            )
        )
        if not closed:
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


def test_positions_pagination_returns_limit(client_with_db):
    """limit=10 → ровно 10 групп (не 30)."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_30_positions(db, acc.id, closed=True)

    resp = client.get(
        "/trades/positions?limit=10&skip=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 10, f"limit=10 должно вернуть 10 групп, вернуло {len(body)}"


def test_positions_pagination_skip_offsets_disjoint(client_with_db):
    """skip=0 и skip=10 — дизъюнктны по position_id."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_30_positions(db, acc.id, closed=True)

    h = {"Authorization": f"Bearer {token}"}
    page1 = client.get("/trades/positions?limit=10&skip=0", headers=h).json()
    page2 = client.get("/trades/positions?limit=10&skip=10", headers=h).json()
    page3 = client.get("/trades/positions?limit=10&skip=20", headers=h).json()

    ids1 = {p["position_id"] for p in page1}
    ids2 = {p["position_id"] for p in page2}
    ids3 = {p["position_id"] for p in page3}

    assert len(ids1) == 10
    assert len(ids2) == 10
    assert len(ids3) == 10
    assert not (ids1 & ids2), "page1 и page2 пересекаются"
    assert not (ids2 & ids3), "page2 и page3 пересекаются"
    assert not (ids1 & ids3), "page1 и page3 пересекаются"
    # Объединение покрывает все 30 уникальных позиций (2000..2029).
    assert ids1 | ids2 | ids3 == {2000 + i for i in range(30)}


def test_positions_pagination_with_status_open(client_with_db):
    """status=open + limit=5 — пагинация поверх отфильтрованных групп."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    # 10 open + 20 closed.
    _seed_30_positions(db, acc.id, closed=False)
    h = {"Authorization": f"Bearer {token}"}

    resp = client.get("/trades/positions?status=open&limit=5&skip=0", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 5
    assert all(p["status"] == "open" for p in body)


def test_positions_pagination_skip_beyond_returns_empty(client_with_db):
    """skip > total → пустой список."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_30_positions(db, acc.id, closed=True)

    h = {"Authorization": f"Bearer {token}"}
    resp = client.get("/trades/positions?limit=10&skip=100", headers=h)
    assert resp.status_code == 200
    assert resp.json() == []

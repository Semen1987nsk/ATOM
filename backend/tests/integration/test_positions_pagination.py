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


def _seed_3_positions(db, account_id: int):
    """3 закрытых round-trip'а с разными position_id + instrument_uid."""
    base = datetime(2026, 5, 1, 10, 0)
    for i in range(3):
        entry = base + timedelta(hours=i)
        db.add(
            Trade(
                account_id=account_id,
                symbol=f"S3{i}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(hours=1),
                currency="RUB",
                data_source="tinkoff_v2",
                instrument_uid=f"uid-s3-{i}",
                position_id=3000 + i,
                commission=Decimal("0"),
                pnl=Decimal("100"),
                net_pnl=Decimal("100"),
            )
        )
    db.commit()


def test_positions_pagination_returns_page_of_groups(client_with_db):
    """S2-10: /trades/positions?limit=2 возвращает ровно 2 position-группы
    (страница ключей в SQL), а не все. Регресс-гард на пагинацию по
    (instrument_uid, position_id)."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_3_positions(db, acc.id)
    h = {"Authorization": f"Bearer {token}"}

    resp = client.get("/trades/positions?status=all&skip=0&limit=2", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2

    resp2 = client.get("/trades/positions?status=all&skip=2&limit=2", headers=h)
    assert resp2.status_code == 200, resp2.text
    assert len(resp2.json()) == 1


def test_positions_legacy_manual_trade_appears(client_with_db):
    """S2-10 regression: manual/legacy round-trip без position_id И без
    instrument_uid (как создаёт POST /trades/) должен появляться в
    /trades/positions — раньше SQL-фильтр .isnot(None) его молча ронял."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    db.add(
        Trade(
            account_id=acc.id,
            symbol="MANUAL",
            direction=TradeDirection.LONG,
            entry_price=Decimal("100"),
            exit_price=Decimal("120"),
            quantity=Decimal("5"),
            entry_at=datetime(2026, 5, 1, 10, 0),
            exit_at=datetime(2026, 5, 1, 12, 0),
            currency="RUB",
            data_source="manual",
            instrument_uid=None,
            position_id=None,
            commission=Decimal("0"),
            pnl=Decimal("100"),
            net_pnl=Decimal("100"),
        )
    )
    db.commit()
    h = {"Authorization": f"Bearer {token}"}

    resp = client.get("/trades/positions?status=all&skip=0&limit=50", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1, f"legacy manual trade выпал из выдачи: {body}"
    assert body[0]["symbol"] == "MANUAL"
    # position_id fallback → Trade.id (legacy: каждая сделка своя позиция).
    assert body[0]["position_id"] is not None


def test_positions_legacy_and_grouped_paginate_together(client_with_db):
    """S2-10: legacy (NULL-ключ) и grouped-позиции пагинируются в одной
    странице по общему порядку last_activity — legacy не выпадает и не
    дублируется на границах страниц."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_3_positions(db, acc.id)  # 3 grouped, entry 10:00/11:00/12:00
    # legacy-сделка с самой поздней активностью → должна идти первой.
    db.add(
        Trade(
            account_id=acc.id,
            symbol="LEG",
            direction=TradeDirection.LONG,
            entry_price=Decimal("100"),
            exit_price=Decimal("120"),
            quantity=Decimal("5"),
            entry_at=datetime(2026, 5, 1, 14, 0),
            exit_at=datetime(2026, 5, 1, 15, 0),
            currency="RUB",
            data_source="manual",
            instrument_uid=None,
            position_id=None,
            commission=Decimal("0"),
            pnl=Decimal("100"),
            net_pnl=Decimal("100"),
        )
    )
    db.commit()
    h = {"Authorization": f"Bearer {token}"}

    all_body = client.get(
        "/trades/positions?status=all&skip=0&limit=50", headers=h
    ).json()
    assert len(all_body) == 4, f"ожидалось 4 позиции (3 grouped + 1 legacy): {all_body}"

    # Дизъюнктность страниц: 3 страницы по 2 покрывают все 4 без пересечений.
    p1 = client.get("/trades/positions?status=all&skip=0&limit=2", headers=h).json()
    p2 = client.get("/trades/positions?status=all&skip=2&limit=2", headers=h).json()
    assert len(p1) == 2 and len(p2) == 2
    syms1 = {p["symbol"] for p in p1}
    syms2 = {p["symbol"] for p in p2}
    assert not (syms1 & syms2), f"страницы пересекаются: {syms1} & {syms2}"
    assert syms1 | syms2 == {"LEG", "S30", "S31", "S32"}

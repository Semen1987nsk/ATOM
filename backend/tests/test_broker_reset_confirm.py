"""
S1-08: POST /broker/connections/{id}/reset без подтверждения не должен молча
удалять sync-сделки (и их ручные аннотации notes/tags/mood/discipline/
confidence/setup_id/screenshot_url).

Поведенческие тесты через TestClient + реальную БД (не source-grep):
- без confirm_data_loss=true -> 409, сделка и аннотации остаются в БД.
- с confirm_data_loss=true -> 200, сделка (sync-данные) удаляется как раньше.
"""

import os
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from models import Account, Base, BrokerConnection, BrokerType, Trade, TradeDirection, User
from database import get_db
import auth_service


@pytest.fixture
def test_app():
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
    yield {"client": TestClient(app), "db": db_session, "Session": TestingSessionLocal}
    db_session.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _make_user(db, email="user@test.com"):
    u = User(
        email=email,
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
    return u, acc


def _auth_headers(user):
    token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _make_connection(db, account):
    conn = BrokerConnection(
        account_id=account.id,
        broker=BrokerType.TINKOFF,
        api_token="dummy-token",
        broker_account_id="BR-1",
        is_active=True,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def _make_annotated_sync_trade(db, account):
    t = Trade(
        account_id=account.id,
        symbol="SBER",
        direction=TradeDirection.LONG,
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quantity=Decimal("10"),
        notes="важная заметка про сделку",
        mood=5,
        discipline=4,
        confidence=3,
        data_source="tinkoff_v2",
        entry_at=__import__("datetime").datetime(2026, 1, 1, 10, 0, 0),
        exit_at=__import__("datetime").datetime(2026, 1, 1, 12, 0, 0),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestResetConfirmationGate:
    def test_reset_without_confirmation_returns_409_and_preserves_trade(self, test_app):
        db = test_app["db"]
        user, account = _make_user(db)
        conn = _make_connection(db, account)
        trade = _make_annotated_sync_trade(db, account)

        r = test_app["client"].post(
            f"/broker/connections/{conn.id}/reset",
            headers=_auth_headers(user),
        )

        assert r.status_code == 409
        assert "confirm_data_loss" in r.json()["detail"] or "потер" in r.json()["detail"].lower()

        # Сделка и аннотации всё ещё в БД — reset не выполнился.
        still_there = db.query(Trade).filter(Trade.id == trade.id).first()
        assert still_there is not None
        assert still_there.notes == "важная заметка про сделку"
        assert still_there.mood == 5

    def test_reset_with_confirmation_deletes_sync_trade(self, test_app, monkeypatch):
        db = test_app["db"]
        user, account = _make_user(db)
        conn = _make_connection(db, account)
        trade = _make_annotated_sync_trade(db, account)

        # reset_account() открывает свой собственный SessionLocal() (см.
        # tools/reset_broker_account.py) — не переопределённую тестовую БД
        # через FastAPI Depends. Подменяем его на тестовый sessionmaker,
        # чтобы проверить реальное удаление, а не только HTTP-статус.
        import tools.reset_broker_account as reset_mod

        monkeypatch.setattr(reset_mod, "SessionLocal", test_app["Session"])

        r = test_app["client"].post(
            f"/broker/connections/{conn.id}/reset?confirm_data_loss=true",
            headers=_auth_headers(user),
        )

        assert r.status_code == 200
        assert r.json()["trades_deleted"] == 1

        gone = db.query(Trade).filter(Trade.id == trade.id).first()
        assert gone is None

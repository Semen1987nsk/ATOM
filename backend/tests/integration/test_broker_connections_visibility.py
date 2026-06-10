"""
SYNC-01 (Sprint 6.5, Batch 6): отозванный токен не должен приводить к
молчаливому исчезновению подключения.

Orchestrator при TokenInvalid делает _deactivate (is_active=False,
api_token="", last_sync_error="deactivated: token_invalid"). Раньше
GET /broker/connections фильтровал is_active=True — деактивированное
подключение исчезало из UI и ReconnectBanner никогда не срабатывал.

Проверяем:
* неактивное подключение ВОЗВРАЩАЕТСЯ в GET /broker/connections
  с needs_reconnect=true и причиной (last_sync_error),
* активное подключение — needs_reconnect=false,
* токен (даже затёртый) не попадает в response payload.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth_service
from database import get_db
from main import app
from models import Account, Base, BrokerConnection, BrokerType, User


@pytest.fixture
def test_app():
    """Fresh in-memory DB per test (паттерн из test_pr26_endpoints)."""
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
    yield {"client": TestClient(app), "db": db_session}
    db_session.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _make_user(db, email="user@test.com"):
    u = User(
        email=email,
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
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
    token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return {"Authorization": f"Bearer {token}"}


def _make_connection(db, account_id, *, is_active=True, **overrides):
    conn = BrokerConnection(
        account_id=account_id,
        broker=BrokerType.TINKOFF,
        api_token=overrides.pop("api_token", "ciphertext-stub"),
        broker_account_id=overrides.pop("broker_account_id", "2000000001"),
        is_active=is_active,
        auto_sync_enabled=True,
        sync_interval_minutes=60,
        total_synced_trades=0,
        **overrides,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def test_inactive_connection_returned_with_needs_reconnect(test_app):
    """Деактивированное (отозванный токен) подключение видно юзеру с причиной."""
    db = test_app["db"]
    user, acc = _make_user(db)
    conn = _make_connection(
        db,
        acc.id,
        is_active=False,
        api_token="",  # затёрт orchestrator._deactivate
        last_sync_status="error",
        last_sync_error="deactivated: token_invalid",
    )

    r = test_app["client"].get("/broker/connections", headers=_auth_headers(user))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1, "неактивное подключение должно вернуться в списке"
    item = items[0]
    assert item["id"] == conn.id
    assert item["is_active"] is False
    assert item["needs_reconnect"] is True
    assert item["last_sync_error"] == "deactivated: token_invalid"


def test_active_connection_needs_reconnect_false(test_app):
    db = test_app["db"]
    user, acc = _make_user(db)
    _make_connection(db, acc.id, is_active=True)

    r = test_app["client"].get("/broker/connections", headers=_auth_headers(user))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["is_active"] is True
    assert items[0]["needs_reconnect"] is False


def test_active_and_inactive_both_returned(test_app):
    db = test_app["db"]
    user, acc = _make_user(db)
    _make_connection(db, acc.id, is_active=True, broker_account_id="111")
    _make_connection(
        db,
        acc.id,
        is_active=False,
        api_token="",
        broker_account_id="222",
        last_sync_error="deactivated: token_invalid",
    )

    r = test_app["client"].get("/broker/connections", headers=_auth_headers(user))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    by_acc = {i["broker_account_id"]: i for i in items}
    assert by_acc["111"]["needs_reconnect"] is False
    assert by_acc["222"]["needs_reconnect"] is True


def test_token_never_in_response(test_app):
    """api_token (даже шифротекст) не должен утекать в payload."""
    db = test_app["db"]
    user, acc = _make_user(db)
    _make_connection(db, acc.id, is_active=True, api_token="ciphertext-secret")

    r = test_app["client"].get("/broker/connections", headers=_auth_headers(user))
    assert r.status_code == 200
    body = r.text
    assert "api_token" not in body
    assert "ciphertext-secret" not in body

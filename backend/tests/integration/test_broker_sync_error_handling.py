"""
Defense-in-depth: непредвиденные ошибки в broker-эндпоинтах НЕ должны рвать
HTTP-соединение («Failed to fetch» в браузере), а возвращать структурный
ответ — как это уже делает плановый sync через orchestrator._guard_one.

Покрываем:
* sync_now: любой неожиданный exception (ValueError/KeyError/DB) → HTTP 500
  (ловился только Token/RateLimit/BrokerError — остальное рвало коннект).
* get_portfolio: неожиданный exception при вызове/парсинге → HTTP 502
  (раньше — необёрнутый коннект-дроп).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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


def _user_account_conn(db):
    u = User(
        email="syncerr@test.com",
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
    conn = BrokerConnection(
        account_id=acc.id,
        broker=BrokerType.TINKOFF,
        api_token="ciphertext-stub",
        broker_account_id="2135909232",
        is_active=True,
        auto_sync_enabled=True,
        sync_interval_minutes=60,
        total_synced_trades=0,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return u, acc, conn


def _auth_headers(user):
    token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return {"Authorization": f"Bearer {token}"}


def test_sync_now_converts_unexpected_error_to_500(test_app):
    """ValueError из orchestrator → чистый 500, а не оборванный коннект."""
    db = test_app["db"]
    user, acc, conn = _user_account_conn(db)

    fake_orch = MagicMock()
    fake_orch.sync_one_account = AsyncMock(side_effect=ValueError("boom unexpected"))

    with patch("routers.broker.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.broker.build_default_orchestrator", return_value=fake_orch
    ):
        r = test_app["client"].post(
            f"/broker/connections/{conn.id}/sync", headers=_auth_headers(user)
        )

    assert r.status_code == 500, f"ожидали чистый 500, получили {r.status_code}"
    assert "detail" in r.json()


def test_get_portfolio_converts_unexpected_error_to_502(test_app):
    """Неожиданная ошибка SDK/парсинга портфеля → чистый 502, не коннект-дроп."""
    db = test_app["db"]
    user, acc, conn = _user_account_conn(db)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_async_client(_token):
        yield MagicMock()

    fake_ops = MagicMock()
    fake_ops.get_portfolio_raw = AsyncMock(side_effect=RuntimeError("grpc parse boom"))

    with patch("routers.broker.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.broker._token_repo"
    ) as mock_repo, patch(
        "routers.broker.client_factory.async_client", side_effect=_fake_async_client
    ), patch(
        "routers.broker.TinkoffOperationsClient", return_value=fake_ops
    ):
        mock_repo.return_value.get_decrypted.return_value = "t.fake"
        r = test_app["client"].get(
            "/broker/portfolio", headers=_auth_headers(user)
        )

    assert r.status_code == 502, f"ожидали чистый 502, получили {r.status_code}"
    assert "detail" in r.json()


def test_get_portfolio_broken_token_returns_410_not_502(test_app):
    """Lock границы: deliberate HTTPException (410, токен повреждён) НЕ должна
    проглатываться catch-all'ом get_portfolio и превращаться в 502/500.
    Регрессия-замок для restructure (парсинг ушёл под guarded-try)."""
    db = test_app["db"]
    user, acc, conn = _user_account_conn(db)

    with patch("routers.broker.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.broker._token_repo"
    ) as mock_repo:
        mock_repo.return_value.get_decrypted.return_value = ""  # повреждённый токен
        r = test_app["client"].get("/broker/portfolio", headers=_auth_headers(user))

    assert r.status_code == 410, (
        f"410 (повреждённый токен) не должен стать 502/500, получили {r.status_code}"
    )

"""S4-04: /broker/portfolio должен отдавать top-level unrealized_pnl и
резолвленные ticker/name позиций (не FIGI-коды) для PortfolioCard.tsx.
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

import auth_service
from database import get_db
from main import app
from models import Account, Base, BrokerConnection, BrokerType, InstrumentORM, User

INSTRUMENT_UID = "sber-uid-123"


def _money(value: float):
    m = MagicMock()
    m.units = int(value)
    m.nano = int(round((value - int(value)) * 1e9))
    return m


@pytest.fixture
def client_with_broker_portfolio():
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
    db = TestingSessionLocal()

    user = User(
        email="portfolio-shape@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    account = Account(
        user_id=user.id,
        name="Main",
        currency="RUB",
        initial_balance=Decimal("0"),
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    conn = BrokerConnection(
        account_id=account.id,
        broker=BrokerType.TINKOFF,
        api_token="ciphertext-stub",
        broker_account_id="2135909232",
        is_active=True,
        auto_sync_enabled=True,
        sync_interval_minutes=60,
        total_synced_trades=0,
    )
    db.add(conn)

    db.add(
        InstrumentORM(
            uid=INSTRUMENT_UID,
            figi="BBG004730N88",
            ticker="SBER",
            instrument_type="share",
            name="Сбербанк",
        )
    )
    db.commit()

    token = auth_service.create_access_token({"sub": str(user.id), "email": user.email})

    try:
        yield {"client": TestClient(app), "token": token}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def _call_portfolio(client, token):
    @asynccontextmanager
    async def _fake_async_client(_token):
        yield MagicMock()

    position = MagicMock()
    position.figi = "BBG004730N88"
    position.instrument_uid = INSTRUMENT_UID
    position.instrument_type = "share"
    position.quantity = _money(10)
    position.average_position_price = _money(250.0)
    position.current_price = _money(262.345)
    position.expected_yield_fifo = _money(123.45)

    portfolio = MagicMock()
    portfolio.total_amount_portfolio = _money(2623.45)
    portfolio.total_amount_currencies = _money(0.0)
    portfolio.total_amount_shares = _money(2623.45)
    portfolio.total_amount_bonds = _money(0.0)
    portfolio.total_amount_etf = _money(0.0)
    portfolio.total_amount_futures = _money(0.0)
    portfolio.total_amount_options = _money(0.0)
    portfolio.positions = [position]

    fake_ops = MagicMock()
    fake_ops.get_portfolio_raw = AsyncMock(return_value=portfolio)

    with patch("routers.broker.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.broker.TokenRepository"
    ) as mock_repo, patch(
        "routers.broker.client_factory.async_client", side_effect=_fake_async_client
    ), patch(
        "routers.broker.TinkoffOperationsClient", return_value=fake_ops
    ):
        mock_repo.return_value.get_decrypted.return_value = "t.fake"
        return client.get("/broker/portfolio", headers={"Authorization": f"Bearer {token}"})


def test_portfolio_response_shape_has_unrealized_and_name(client_with_broker_portfolio):
    client = client_with_broker_portfolio["client"]
    token = client_with_broker_portfolio["token"]

    resp = _call_portfolio(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "unrealized_pnl" in body, "top-level unrealized_pnl обязателен для PortfolioCard"
    assert body["unrealized_pnl"] == 123.45
    pos = body["positions"][0]
    assert pos["ticker"] == "SBER"
    assert pos["name"] == "Сбербанк"
    assert "figi" in pos  # FIGI сохранён отдельным полем

"""ADR-0010 fix-wave: anchor-adjusted cash/ROI consumers (C1, C2).

После ADR-0010 каждый cash-truth/ROI consumer обязан вычитать
effective_deposits = net_deposits + initial_balance (восстановленный стартовый
якорь broker-счёта с неполной историей), а не голый net_deposits. Иначе
дашборд показывает скорректированные числа, а эти эндпойнты — старые ложные.

C1 — /real-pnl/        : real_pnl = current_balance - (net_deposit + initial_balance)
C2 — /deposits/balance : broker_pnl = broker_balance - (net_deposit + initial_balance)

Каждый кейс проверяется дважды:
  * anchored broker account (initial_balance > 0) → число вычитает якорь;
  * zero-anchor account (initial_balance == 0)    → число неизменно (regression-lock).
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
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
from models import (
    Account,
    BalanceSnapshot,
    Base,
    BrokerConnection,
    BrokerType,
    OperationORM,
    User,
)

ANCHOR = 104_376.0
NET_DEPOSIT = 8_556.0
CURRENT_BALANCE = 32_938.0


@pytest.fixture
def client_with_db():
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
        yield {"client": TestClient(app), "db": db_session}
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def _user_account(db, *, initial_balance: float):
    u = User(
        email=f"anchor-consumer-{initial_balance}@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(
        user_id=u.id,
        name="Main",
        currency="RUB",
        initial_balance=Decimal(str(initial_balance)),
    )
    if initial_balance > 0:
        acc.initial_balance_source = "inferred_anchor"
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
    token = auth_service.create_access_token({"sub": str(u.id), "email": u.email})
    return u, acc, token


def _seed_net_deposit(db, account_id: int, amount: float = NET_DEPOSIT):
    db.add(
        OperationORM(
            account_id=account_id,
            broker_account_id="2135909232",
            operation_id=f"op-input-{account_id}",
            operation_type="input",  # NET_DEPOSIT
            state="executed",
            payment_units=int(amount),
            payment_nano=0,
            payment_currency="rub",
            executed_at=datetime(2026, 6, 24, 10, 0),
        )
    )
    db.commit()


def _money(value: float):
    m = MagicMock()
    m.units = int(value)
    m.nano = int(round((value - int(value)) * 1e9))
    return m


# --------------------------------------------------------------------------- C1
def _call_real_pnl(client, token):
    @asynccontextmanager
    async def _fake_async_client(_token):
        yield MagicMock()

    portfolio = MagicMock()
    portfolio.total_amount_portfolio = _money(CURRENT_BALANCE)
    portfolio.total_amount_currencies = _money(0.0)

    fake_ops = MagicMock()
    fake_ops.get_portfolio_raw = AsyncMock(return_value=portfolio)

    with patch("routers.real_pnl.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.real_pnl.TokenRepository"
    ) as mock_repo, patch(
        "routers.real_pnl.client_factory.async_client", side_effect=_fake_async_client
    ), patch(
        "routers.real_pnl.TinkoffOperationsClient", return_value=fake_ops
    ):
        mock_repo.return_value.get_decrypted.return_value = "t.fake"
        return client.get("/real-pnl/", headers={"Authorization": f"Bearer {token}"})


def test_c1_real_pnl_subtracts_anchor_for_anchored_account(client_with_db):
    db, client = client_with_db["db"], client_with_db["client"]
    _, acc, token = _user_account(db, initial_balance=ANCHOR)
    _seed_net_deposit(db, acc.id)

    resp = _call_real_pnl(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # real_pnl = 32938 - (8556 + 104376) = -80 (а не ложно-положительное +24382).
    expected = CURRENT_BALANCE - (NET_DEPOSIT + ANCHOR)
    assert body["real_pnl"] == pytest.approx(round(expected, 2), abs=0.01)
    eff = NET_DEPOSIT + ANCHOR
    assert body["roi"] == pytest.approx(round(expected / eff * 100, 2), abs=0.01)


def test_c1_real_pnl_unchanged_for_zero_anchor(client_with_db):
    db, client = client_with_db["db"], client_with_db["client"]
    _, acc, token = _user_account(db, initial_balance=0.0)
    _seed_net_deposit(db, acc.id)

    resp = _call_real_pnl(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # initial_balance == 0 → прежняя формула current - net_deposit.
    expected = CURRENT_BALANCE - NET_DEPOSIT
    assert body["real_pnl"] == pytest.approx(round(expected, 2), abs=0.01)
    assert body["roi"] == pytest.approx(round(expected / NET_DEPOSIT * 100, 2), abs=0.01)


# --------------------------------------------------------------------------- C2
def _seed_broker_balance_snapshot(db, account_id: int, balance: float = CURRENT_BALANCE):
    db.add(
        BalanceSnapshot(
            account_id=account_id,
            date=datetime(2026, 6, 25, 18, 0),
            balance=balance,
            source="tinkoff_api",
        )
    )
    db.commit()


def test_c2_deposits_broker_pnl_subtracts_anchor_for_anchored_account(client_with_db):
    db, client = client_with_db["db"], client_with_db["client"]
    _, acc, token = _user_account(db, initial_balance=ANCHOR)
    _seed_net_deposit(db, acc.id)
    _seed_broker_balance_snapshot(db, acc.id)

    resp = client.get("/deposits/balance", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance_source"] == "broker_live"
    # broker_pnl = 32938 - (net_deposit + 104376). net_deposit здесь считается из
    # CapitalOperation/DepositHistory (manual-ветка пуста) → 0, поэтому проверяем
    # инвариант: broker_pnl == broker_balance - (net_deposit + anchor).
    net_deposit = body["net_deposit"]
    expected = CURRENT_BALANCE - (net_deposit + ANCHOR)
    assert body["broker_pnl"] == pytest.approx(round(expected, 2), abs=0.01)
    assert body["total_pnl"] == pytest.approx(round(expected, 2), abs=0.01)


def test_c2_deposits_broker_pnl_unchanged_for_zero_anchor(client_with_db):
    db, client = client_with_db["db"], client_with_db["client"]
    _, acc, token = _user_account(db, initial_balance=0.0)
    _seed_net_deposit(db, acc.id)
    _seed_broker_balance_snapshot(db, acc.id)

    resp = client.get("/deposits/balance", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance_source"] == "broker_live"
    net_deposit = body["net_deposit"]
    # initial_balance == 0 → broker_pnl == broker_balance - net_deposit (без сдвига).
    expected = CURRENT_BALANCE - net_deposit
    assert body["broker_pnl"] == pytest.approx(round(expected, 2), abs=0.01)

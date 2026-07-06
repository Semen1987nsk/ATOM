"""S2-06: ROI-база anchored брокер-счёта = anchor + Σ NET_DEPOSIT(OperationORM),
БЕЗ двойного счёта якоря. Раньше get_net_deposit_as_of при пустой DepositHistory
возвращал сам initial_balance → база = anchor+anchor.

Oracle acc#2: anchor 99095 + Σ NET_DEPOSIT 8556 = 107651 (НЕ 198190).
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import database
from main import app
from models import Account, Base, OperationORM, Trade, TradeDirection, User


@pytest.fixture
def client_and_acc():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides.clear()
    from services.stats_cache import stats_cache as _sc
    _sc.clear()
    app.dependency_overrides[database.get_db] = _override
    s = TestingSession()
    u = User(email="roi@test.com", hashed_password="x", is_active=1)
    s.add(u); s.commit()
    acc = Account(user_id=u.id, name="Main", currency="RUB",
                  initial_balance=Decimal("99095"), initial_balance_source="inferred_anchor")
    acc.last_portfolio_value = Decimal("32938")
    s.add(acc); s.commit()
    # Σ NET_DEPOSIT = 8556 через OperationORM (тип input).
    s.add(OperationORM(account_id=acc.id, broker_account_id="B1", operation_id="d1",
                       operation_type="input", state="executed",
                       payment_units=8556, payment_nano=0, executed_at=datetime(2026, 6, 24)))
    s.add(Trade(account_id=acc.id, symbol="MXI", direction=TradeDirection.LONG,
                entry_price=Decimal("1"), quantity=Decimal("1"),
                entry_at=datetime(2026, 1, 5), exit_at=datetime(2026, 2, 5),
                pnl=Decimal("-100"), net_pnl=Decimal("-100")))
    s.commit()
    yield s, acc, u
    app.dependency_overrides.clear()
    s.close()


def test_broker_roi_base_no_double_anchor(client_and_acc, monkeypatch):
    s, acc, u = client_and_acc
    import auth_service
    # get_current_user резолвится через Depends(...) на декораторе → правим через
    # dependency_overrides. get_account_id вызывается напрямую в теле → monkeypatch.
    app.dependency_overrides[auth_service.get_current_user] = lambda: u
    monkeypatch.setattr(auth_service, "get_account_id", lambda db, user: acc.id)
    client = TestClient(app)
    resp = client.get("/stats/?period=all", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    body = resp.json()
    # period_start_balance = 99095 + 8556 = 107651, НЕ 198190 (99095*2).
    assert abs(body["period_start_balance"] - 107651) < 2.0


@pytest.fixture
def client_and_acc_withdrawal():
    """Как client_and_acc, но с OUTPUT-операцией (отрицательный payment_units).

    Net withdrawals > deposits → signed Σ NET_DEPOSIT < 0. Signed != abs здесь,
    поэтому именно эта фикстура ловит расхождение sign-convention, которого не
    видно на acc#2 (только заводы, signed == abs)."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides.clear()
    # stats_cache — module-level TTL cache, ключ = account_id+period+fingerprint.
    # Оба теста используют account_id=1 с идентичным trade-fingerprint → без
    # сброса второй тест получит cached ответ первого (107651 вместо 110539).
    from services.stats_cache import stats_cache as _sc
    _sc.clear()
    app.dependency_overrides[database.get_db] = _override
    s = TestingSession()
    u = User(email="roiw@test.com", hashed_password="x", is_active=1)
    s.add(u); s.commit()
    acc = Account(user_id=u.id, name="Main", currency="RUB",
                  initial_balance=Decimal("99095"), initial_balance_source="inferred_anchor")
    acc.last_portfolio_value = Decimal("32938")
    s.add(acc); s.commit()
    # Завод +8556, затем вывод -20000 → signed Σ = -11444, abs = 11444.
    s.add(OperationORM(account_id=acc.id, broker_account_id="B1", operation_id="d1",
                       operation_type="input", state="executed",
                       payment_units=8556, payment_nano=0, executed_at=datetime(2026, 6, 24)))
    s.add(OperationORM(account_id=acc.id, broker_account_id="B1", operation_id="w1",
                       operation_type="output", state="executed",
                       payment_units=-20000, payment_nano=0, executed_at=datetime(2026, 6, 25)))
    s.add(Trade(account_id=acc.id, symbol="MXI", direction=TradeDirection.LONG,
                entry_price=Decimal("1"), quantity=Decimal("1"),
                entry_at=datetime(2026, 1, 5), exit_at=datetime(2026, 2, 5),
                pnl=Decimal("-100"), net_pnl=Decimal("-100")))
    s.commit()
    yield s, acc, u
    app.dependency_overrides.clear()
    s.close()


def test_broker_roi_base_parity_with_baseline_on_withdrawal(client_and_acc_withdrawal, monkeypatch):
    """S2-06 + S3-14: /stats/period_start_balance должен совпадать с
    anchor + get_net_deposits_baseline_from_db — ЗНАКОВАЯ Σ NET_DEPOSIT (вывод
    средств уменьшает базу), согласованная с pnl_health effective_deposits и
    drawdown_baseline. Locks sign-convention: signed 99095 + (8556−20000) =
    87651; ошибочный abs дал бы 99095 + 11444 = 110539 (вывод «увеличивал» базу)."""
    s, acc, u = client_and_acc_withdrawal
    import auth_service
    from analytics._common_baseline import get_net_deposits_baseline_from_db

    app.dependency_overrides[auth_service.get_current_user] = lambda: u
    monkeypatch.setattr(auth_service, "get_account_id", lambda db, user: acc.id)

    baseline = get_net_deposits_baseline_from_db(s, acc.id)  # signed = -11444
    expected = float(acc.initial_balance) + float(baseline)  # 99095 + (-11444) = 87651

    client = TestClient(app)
    resp = client.get("/stats/?period=all", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200
    body = resp.json()
    # Паритет endpoint ↔ signed baseline. Abs-версия (баг) дала бы 110539.
    assert abs(body["period_start_balance"] - expected) < 2.0
    assert abs(body["period_start_balance"] - 87651) < 2.0

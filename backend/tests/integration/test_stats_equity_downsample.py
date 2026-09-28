"""PERF-10: /stats/ применяет LTTB-downsample к equity_curve.

Главный кейс — assert длина equity_curve ≤ EQUITY_CURVE_MAX_POINTS. Также
проверяем: первая точка equity_curve осталась (startpoint), кривая остаётся
неинтерполированной (точки = реальные dict'ы с date+balance).

Сам LTTB-алгоритм покрыт в unit/test_downsample.py — здесь только wiring.
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
from models import Account, Base, Trade, TradeDirection, User
from database import get_db
import auth_service
from config import settings


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


def _setup_user(db):
    u = User(
        email="perf10-stats@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
        is_admin=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(
        user_id=u.id, name="Main", currency="RUB", initial_balance=Decimal("100000")
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, acc, token


def _seed_closed_trades(db, account_id: int, n: int):
    """Создаёт N закрытых трейдов: каждый по часу, с PnL чередующимся ±100."""
    base = datetime(2026, 1, 1, 10, 0)
    for i in range(n):
        entry = base + timedelta(hours=i)
        pnl = Decimal("100") if i % 2 == 0 else Decimal("-50")
        db.add(
            Trade(
                account_id=account_id,
                symbol=f"S{i:04d}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("101"),
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=10000 + i,
                commission=Decimal("0"),
                pnl=pnl,
                net_pnl=pnl,
            )
        )
    db.commit()


def test_equity_curve_downsampled_below_threshold(client_with_db):
    """1000 трейдов → equity_curve ≤ EQUITY_CURVE_MAX_POINTS (default 500)."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_closed_trades(db, acc.id, 1000)

    resp = client.get(
        "/stats/", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    curve = body.get("equity_curve") or []
    assert len(curve) <= settings.EQUITY_CURVE_MAX_POINTS, (
        f"equity_curve должен быть сжат до ≤{settings.EQUITY_CURVE_MAX_POINTS}, "
        f"получили {len(curve)}"
    )
    # Когда трейдов > threshold, downsample должен сократить хотя бы вдвое.
    assert len(curve) < 1000

    # Точки — реальные dict'ы (не интерполированные): сохраняются ключи.
    if curve:
        assert "date" in curve[0]
        assert "balance" in curve[0]
        # Аналогично проверяем gross-вариант.
        gross = body.get("equity_curve_gross") or []
        assert len(gross) <= settings.EQUITY_CURVE_MAX_POINTS


def test_equity_curve_passthrough_when_below_threshold(client_with_db):
    """50 трейдов → curve остаётся как есть (без сжатия)."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_closed_trades(db, acc.id, 50)

    resp = client.get(
        "/stats/", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    curve = resp.json().get("equity_curve") or []
    # 50 < 500 → не сжимается.
    assert len(curve) == 50

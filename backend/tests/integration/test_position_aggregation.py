"""TR1.1: integration tests для расширенной aggregation в /trades/positions.

Покрытие:
- pnl_pct: % от entry_value (primary), fallback на price×qty
- r_multiple: realized / Σ risk_amount; dash если no risk
- MAE/MFE: min/max across executions
- has_notes / has_screenshot: indicator booleans
- Inherited journaling fields: confidence, mood, stop_loss, take_profit
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import (
    Base, User, Account, Trade, TradeDirection,
)
from database import get_db
import auth_service
from utils.datetime_utils import utc_now_naive


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


def _setup_user(db):
    u = User(
        email="trader@test.com",
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


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_trade(db, account_id, **kwargs):
    """Helper для создания Trade с дефолтами. instrument_uid задан по умолчанию
    чтобы position_id grouping работал (см. routers/trades.py:groups key)."""
    defaults = dict(
        symbol="SBER",
        direction=TradeDirection.LONG,
        entry_price=Decimal("100"),
        quantity=Decimal("10"),
        entry_at=datetime(2026, 5, 1, 10, 0),
        currency="RUB",
        data_source="tinkoff_v2",
        instrument_uid="uid-sber-test",
        position_id=1,
        commission=Decimal("0"),
    )
    defaults.update(kwargs)
    t = Trade(account_id=account_id, **defaults)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_pnl_pct_closed_long_primary_entry_value(test_app):
    """Closed long с entry_value=10000, net_pnl=+500 → pnl_pct = +5%."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    _make_trade(
        db, acc.id,
        position_id=1,
        entry_price=Decimal("100"),
        exit_price=Decimal("105"),
        quantity=Decimal("100"),
        entry_at=datetime(2026, 5, 1, 10, 0),
        exit_at=datetime(2026, 5, 1, 12, 0),
        pnl=Decimal("500"),
        net_pnl=Decimal("500"),
        entry_value=Decimal("10000"),
        exit_value=Decimal("10500"),
    )

    r = client.get("/trades/positions?status=all", headers=_auth_headers(token))
    assert r.status_code == 200
    positions = r.json()
    assert len(positions) == 1
    p = positions[0]
    assert p["pnl_pct"] == pytest.approx(5.0, abs=0.01)
    assert p["realized_pnl"] == pytest.approx(500.0)
    assert p["status"] == "closed"


def test_pnl_pct_fallback_when_no_entry_value(test_app):
    """Если entry_value=None — fallback на weighted_entry × |total_qty|."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    # Legacy-style trade без entry_value
    _make_trade(
        db, acc.id,
        position_id=2,
        entry_price=Decimal("50"),
        exit_price=Decimal("55"),
        quantity=Decimal("200"),
        entry_at=datetime(2026, 5, 1, 10, 0),
        exit_at=datetime(2026, 5, 1, 11, 0),
        pnl=Decimal("1000"),
        net_pnl=Decimal("1000"),
        entry_value=None,
        exit_value=None,
    )

    r = client.get("/trades/positions", headers=_auth_headers(token))
    assert r.status_code == 200
    p = r.json()[0]
    # Fallback: 1000 / (50 × 200) × 100 = 10%
    assert p["pnl_pct"] == pytest.approx(10.0, abs=0.01)


def test_r_multiple_with_risk_amount(test_app):
    """2 closed trades с risk_amount=100 каждая, realized=+300 → r_multiple=+1.5R."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    for i, (price_in, price_out, pnl_val) in enumerate(
        [(100, 110, 100), (90, 110, 200)]
    ):
        _make_trade(
            db, acc.id,
            position_id=3 + i,
            entry_price=Decimal(price_in),
            exit_price=Decimal(price_out),
            quantity=Decimal("10"),
            entry_at=datetime(2026, 5, 1, 10 + i, 0),
            exit_at=datetime(2026, 5, 1, 11 + i, 0),
            net_pnl=Decimal(pnl_val),
            risk_amount=Decimal("100"),
            entry_value=Decimal(price_in * 10),
        )

    r = client.get("/trades/positions?status=closed", headers=_auth_headers(token))
    positions = r.json()
    assert len(positions) == 2  # different position_id → 2 positions
    # Each position has r_multiple = pnl / risk
    pnls_by_r = {p["r_multiple"] for p in positions}
    assert 1.0 in pnls_by_r  # 100 / 100
    assert 2.0 in pnls_by_r  # 200 / 100


def test_r_multiple_none_when_no_risk(test_app):
    """Trade без risk_amount → r_multiple=None (dash в UI)."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    _make_trade(
        db, acc.id,
        position_id=5,
        exit_price=Decimal("110"),
        exit_at=datetime(2026, 5, 1, 12, 0),
        net_pnl=Decimal("100"),
        risk_amount=None,  # не задан
    )

    r = client.get("/trades/positions", headers=_auth_headers(token))
    p = r.json()[0]
    assert p["r_multiple"] is None
    assert p["total_risk_amount"] is None


def test_mae_mfe_min_max_aggregation(test_app):
    """3 executions с MAE=[95, 92, 94] → mae=92; MFE=[108, 115, 110] → mfe=115."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    mae_values = [Decimal("95"), Decimal("92"), Decimal("94")]
    mfe_values = [Decimal("108"), Decimal("115"), Decimal("110")]
    for i in range(3):
        _make_trade(
            db, acc.id,
            position_id=6,  # все три — одна позиция
            entry_at=datetime(2026, 5, 1, 10 + i, 0),
            mae_price=mae_values[i],
            mfe_price=mfe_values[i],
        )

    r = client.get("/trades/positions", headers=_auth_headers(token))
    p = r.json()[0]
    assert p["mae_price"] == pytest.approx(92.0)
    assert p["mfe_price"] == pytest.approx(115.0)
    assert p["execution_count"] == 3
    assert p["is_scale_in"] is True


def test_indicators_has_screenshot_has_notes(test_app):
    """has_screenshot=True если any execution имеет screenshot_url;
    has_notes=True если first.notes != пустая."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    # Position 7: ни screenshot, ни notes
    _make_trade(db, acc.id, position_id=7, notes=None, screenshot_url=None)

    # Position 8: notes есть, screenshot нет
    _make_trade(
        db, acc.id,
        position_id=8,
        entry_at=datetime(2026, 5, 2, 10, 0),
        notes="Хороший сетап, после пробоя",
        screenshot_url=None,
    )

    # Position 9: screenshot только на втором execution
    _make_trade(
        db, acc.id,
        position_id=9,
        entry_at=datetime(2026, 5, 3, 10, 0),
        screenshot_url=None,
    )
    _make_trade(
        db, acc.id,
        position_id=9,
        entry_at=datetime(2026, 5, 3, 11, 0),
        screenshot_url="/uploads/screenshot.png",
    )

    r = client.get("/trades/positions", headers=_auth_headers(token))
    positions = r.json()
    by_pid = {p["position_id"]: p for p in positions}

    assert by_pid[7]["has_notes"] is False
    assert by_pid[7]["has_screenshot"] is False

    assert by_pid[8]["has_notes"] is True
    assert by_pid[8]["has_screenshot"] is False

    assert by_pid[9]["has_notes"] is False
    assert by_pid[9]["has_screenshot"] is True  # any() across executions


def test_journaling_fields_inherited_from_first_execution(test_app):
    """confidence, mood, stop_loss наследуются от первого execution в группе."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    _make_trade(
        db, acc.id,
        position_id=10,
        entry_at=datetime(2026, 5, 4, 10, 0),
        confidence=4,
        mood=5,
        discipline=3,
        timeframe="1H",
        stop_loss=Decimal("90"),
        take_profit=Decimal("120"),
        entry_reason="Pullback в EMA50",
    )
    _make_trade(
        db, acc.id,
        position_id=10,
        entry_at=datetime(2026, 5, 4, 11, 0),
        confidence=2,  # игнорируется (не первый)
        mood=1,
        stop_loss=Decimal("85"),
    )

    r = client.get("/trades/positions", headers=_auth_headers(token))
    p = r.json()[0]
    assert p["confidence"] == 4
    assert p["mood"] == 5
    assert p["discipline"] == 3
    assert p["timeframe"] == "1H"
    assert p["stop_loss"] == pytest.approx(90.0)
    assert p["take_profit"] == pytest.approx(120.0)
    assert p["entry_reason"] == "Pullback в EMA50"


def test_pnl_pct_short_position(test_app):
    """SHORT: вход 100, выход 90 → pnl=+1000 (профит от падения).
    pnl_pct = 1000 / 10000 × 100 = +10%."""
    db = test_app["db"]
    client = test_app["client"]
    _, acc, token = _setup_user(db)

    _make_trade(
        db, acc.id,
        position_id=11,
        direction=TradeDirection.SHORT,
        entry_price=Decimal("100"),
        exit_price=Decimal("90"),
        quantity=Decimal("100"),
        exit_at=datetime(2026, 5, 5, 11, 0),
        net_pnl=Decimal("1000"),
        entry_value=Decimal("10000"),
    )

    r = client.get("/trades/positions", headers=_auth_headers(token))
    p = r.json()[0]
    assert p["direction"] == "short"
    assert p["pnl_pct"] == pytest.approx(10.0, abs=0.01)

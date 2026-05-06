"""
Tests for /review/ (Daily Review CRUD).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from models import Base, User, Account, Trade, TradeDirection, DailyReview  # noqa: E402
from database import get_db  # noqa: E402
import auth_service  # noqa: E402


@pytest.fixture(scope="function")
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


@pytest.fixture
def user_with_trades(test_app):
    db = test_app["db"]
    user = User(
        email="rev@example.com",
        name="Rev",
        hashed_password=auth_service.get_password_hash("testpass1234"),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    account = Account(user_id=user.id, name="Acc", initial_balance=Decimal("0"), currency="RUB")
    db.add(account)
    db.commit()
    db.refresh(account)

    # Две сделки 1 апреля, одна — 2 апреля
    t1 = Trade(
        account_id=account.id, symbol="SBER", direction=TradeDirection.LONG,
        entry_price=Decimal("300"), exit_price=Decimal("305"), quantity=Decimal("100"),
        entry_at=datetime(2026, 4, 1, 10, 0), exit_at=datetime(2026, 4, 1, 12, 0),
        pnl=Decimal("500"), net_pnl=Decimal("490"), currency="RUB",
        setup_name="Пробой",
    )
    t2 = Trade(
        account_id=account.id, symbol="GAZP", direction=TradeDirection.SHORT,
        entry_price=Decimal("140"), exit_price=Decimal("142"), quantity=Decimal("50"),
        entry_at=datetime(2026, 4, 1, 14, 0), exit_at=datetime(2026, 4, 1, 16, 0),
        pnl=Decimal("-100"), net_pnl=Decimal("-110"), currency="RUB",
    )
    t3 = Trade(
        account_id=account.id, symbol="LKOH", direction=TradeDirection.LONG,
        entry_price=Decimal("5300"), exit_price=Decimal("5400"), quantity=Decimal("10"),
        entry_at=datetime(2026, 4, 2, 10, 0), exit_at=datetime(2026, 4, 2, 12, 0),
        pnl=Decimal("1000"), net_pnl=Decimal("980"), currency="RUB",
    )
    db.add_all([t1, t2, t3])
    db.commit()
    return {"user": user, "account": account, "trades": [t1, t2, t3]}


@pytest.fixture
def auth_headers(user_with_trades):
    user = user_with_trades["user"]
    token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


class TestReviewGet:
    def test_get_returns_trades_of_the_day(self, test_app, user_with_trades, auth_headers):
        client = test_app["client"]
        r = client.get("/review/?date=2026-04-01", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["date"] == "2026-04-01"
        assert body["reflection"] == ""
        assert body["intention"] == ""
        assert body["rating"] is None
        assert len(body["trades"]) == 2
        assert {t["symbol"] for t in body["trades"]} == {"SBER", "GAZP"}
        assert body["summary"]["total_trades"] == 2
        assert body["summary"]["wins"] == 1
        assert body["summary"]["losses"] == 1
        assert body["summary"]["total_pnl"] == 400.0

    def test_get_other_day_isolated(self, test_app, user_with_trades, auth_headers):
        client = test_app["client"]
        r = client.get("/review/?date=2026-04-02", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert len(body["trades"]) == 1
        assert body["trades"][0]["symbol"] == "LKOH"

    def test_get_invalid_date_400(self, test_app, user_with_trades, auth_headers):
        client = test_app["client"]
        r = client.get("/review/?date=not-a-date", headers=auth_headers)
        assert r.status_code == 400


class TestReviewSave:
    def test_save_creates_new_review(self, test_app, user_with_trades, auth_headers):
        client = test_app["client"]
        r = client.post(
            "/review/",
            headers=auth_headers,
            json={
                "date": "2026-04-01",
                "reflection": "Импульсная сессия. Один трейд по плану, один на эмоциях.",
                "intention": "Не входить до 11:00",
                "rating": 4,
                "trade_reflections": {"1": "Чёткий пробой уровня"},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reflection"].startswith("Импульсная")
        assert body["intention"] == "Не входить до 11:00"
        assert body["rating"] == 4
        # Per-trade reflection возвращается в trades[].reflection
        sber = next(t for t in body["trades"] if t["symbol"] == "SBER")
        assert sber["reflection"] == "Чёткий пробой уровня"

    def test_save_merges_trade_reflections(self, test_app, user_with_trades, auth_headers):
        """При повторном сохранении одной сделки остальные не должны пропасть."""
        client = test_app["client"]
        # Первое сохранение — комментарий по trade #1
        client.post("/review/", headers=auth_headers, json={
            "date": "2026-04-01", "trade_reflections": {"1": "Trade-1 comment"}
        })
        # Второе сохранение — только trade #2
        r = client.post("/review/", headers=auth_headers, json={
            "date": "2026-04-01", "trade_reflections": {"2": "Trade-2 comment"}
        })
        assert r.status_code == 200
        body = r.json()
        sber = next(t for t in body["trades"] if t["id"] == 1)
        gazp = next(t for t in body["trades"] if t["id"] == 2)
        # Оба коммента должны сохраниться (merge, не replace)
        assert sber["reflection"] == "Trade-1 comment"
        assert gazp["reflection"] == "Trade-2 comment"

    def test_save_rating_validation(self, test_app, user_with_trades, auth_headers):
        client = test_app["client"]
        # rating > 5 → 422
        r = client.post("/review/", headers=auth_headers, json={"date": "2026-04-01", "rating": 7})
        assert r.status_code == 422
        # rating < 1 → 422
        r = client.post("/review/", headers=auth_headers, json={"date": "2026-04-01", "rating": 0})
        assert r.status_code == 422

    def test_save_date_format_validation(self, test_app, user_with_trades, auth_headers):
        client = test_app["client"]
        r = client.post("/review/", headers=auth_headers, json={"date": "01.04.2026"})
        assert r.status_code == 422

    def test_save_idempotent_one_row_per_day(self, test_app, user_with_trades, auth_headers):
        """UniqueConstraint(account_id, date) — повторный POST апдейтит, не дублирует."""
        client = test_app["client"]
        client.post("/review/", headers=auth_headers, json={"date": "2026-04-01", "reflection": "v1"})
        r = client.post("/review/", headers=auth_headers, json={"date": "2026-04-01", "reflection": "v2"})
        assert r.status_code == 200
        assert r.json()["reflection"] == "v2"

        db = test_app["db"]
        # В БД должна быть РОВНО одна запись.
        count = db.query(DailyReview).filter(
            DailyReview.account_id == user_with_trades["account"].id,
            DailyReview.date == "2026-04-01",
        ).count()
        assert count == 1

    def test_review_unauthenticated(self, test_app, user_with_trades):
        client = test_app["client"]
        r = client.get("/review/?date=2026-04-01")
        assert r.status_code in (401, 403)

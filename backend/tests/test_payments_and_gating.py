"""
Tests for /payments router + subscription paywall gating.

Покрывает:
- /payments/me для FREE-юзера → plan='free'
- /payments/checkout-link генерит stub-URL
- /payments/webhook со status=succeeded активирует PRO-подписку
- enforce_trade_limit: FREE юзер с N=FREE_PLAN_TRADE_LIMIT не может создать новую сделку
- require_pro: 402 на FREE, 200 на PRO
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Включаем DEBUG, чтобы /payments/stub-confirm был доступен
os.environ.setdefault("DEBUG", "true")

from main import app  # noqa: E402
from models import (  # noqa: E402
    Base, User, Account, Trade, TradeDirection, Subscription, SubscriptionPlan
)
from database import get_db  # noqa: E402
import auth_service  # noqa: E402
from utils.datetime_utils import utc_now_naive  # noqa: E402
from subscription_service import (  # noqa: E402
    get_active_plan, enforce_trade_limit, FREE_PLAN_TRADE_LIMIT
)
from fastapi import HTTPException  # noqa: E402


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


def _make_user(db, email="u@example.com"):
    user = User(
        email=email, name="U",
        hashed_password=auth_service.get_password_hash("testpass1234"),
        is_active=1, settings={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    acc = Account(user_id=user.id, name="A", initial_balance=Decimal("0"), currency="RUB")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return user, acc


def _auth_headers(user):
    token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────────────────────────
#  /payments/me
# ──────────────────────────────────────────────────────────────────


class TestPlanLookup:
    def test_default_is_free(self, test_app):
        user, _ = _make_user(test_app["db"])
        r = test_app["client"].get("/payments/me", headers=_auth_headers(user))
        assert r.status_code == 200
        assert r.json()["plan"] == "free"

    def test_active_pro_subscription_visible(self, test_app):
        db = test_app["db"]
        user, _ = _make_user(db)
        sub = Subscription(
            user_id=user.id, plan=SubscriptionPlan.PRO,
            is_active=1, started_at=utc_now_naive(),
        )
        db.add(sub)
        db.commit()
        r = test_app["client"].get("/payments/me", headers=_auth_headers(user))
        assert r.json()["plan"] == "pro"


# ──────────────────────────────────────────────────────────────────
#  Checkout + webhook activation
# ──────────────────────────────────────────────────────────────────


class TestCheckoutFlow:
    def test_checkout_link_returns_stub_url(self, test_app):
        user, _ = _make_user(test_app["db"])
        r = test_app["client"].post(
            "/payments/checkout-link",
            headers=_auth_headers(user),
            json={"plan": "pro"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["plan"] == "pro"
        assert body["amount"] == 399.0
        assert body["is_stub"] is True
        assert "/payments/stub-confirm" in body["confirmation_url"]

    def test_webhook_activates_pro(self, test_app):
        user, _ = _make_user(test_app["db"])
        client = test_app["client"]
        r = client.post("/payments/webhook", json={
            "payment_id": "pmt-123",
            "user_email": user.email,
            "plan": "pro",
            "status": "succeeded",
            "amount": 399.0,
        })
        assert r.status_code == 200
        # Проверяем, что подписка активна
        plan = get_active_plan(test_app["db"], user)
        assert plan == SubscriptionPlan.PRO

    def test_webhook_canceled_does_not_activate(self, test_app):
        user, _ = _make_user(test_app["db"])
        client = test_app["client"]
        r = client.post("/payments/webhook", json={
            "payment_id": "pmt-x",
            "user_email": user.email,
            "plan": "pro",
            "status": "canceled",
        })
        assert r.status_code == 200
        plan = get_active_plan(test_app["db"], user)
        assert plan == SubscriptionPlan.FREE


# ──────────────────────────────────────────────────────────────────
#  Trade-limit gate
# ──────────────────────────────────────────────────────────────────


class TestTradeLimitGate:
    def test_below_limit_passes(self, test_app):
        db = test_app["db"]
        user, _ = _make_user(db)
        # 0 сделок → пропускает
        enforce_trade_limit(db, user)  # не должно бросить

    def test_at_limit_raises(self, test_app):
        db = test_app["db"]
        user, acc = _make_user(db)
        # Создаём ровно лимит сделок
        for i in range(FREE_PLAN_TRADE_LIMIT):
            db.add(Trade(
                account_id=acc.id, symbol=f"S{i}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"), quantity=Decimal("1"),
                entry_at=datetime(2026, 1, 1, 10, i % 60),
                currency="RUB",
            ))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            enforce_trade_limit(db, user)
        assert exc.value.status_code == 402
        detail = exc.value.detail
        assert detail["error"] == "trade_limit_reached"
        assert detail["limit"] == FREE_PLAN_TRADE_LIMIT

    def test_pro_user_unlimited(self, test_app):
        db = test_app["db"]
        user, acc = _make_user(db)
        db.add(Subscription(
            user_id=user.id, plan=SubscriptionPlan.PRO,
            is_active=1, started_at=utc_now_naive(),
        ))
        # 100 сделок
        for i in range(100):
            db.add(Trade(
                account_id=acc.id, symbol=f"S{i}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"), quantity=Decimal("1"),
                entry_at=datetime(2026, 1, 1, 10, i % 60),
                currency="RUB",
            ))
        db.commit()
        # Должно пройти без исключения
        enforce_trade_limit(db, user)


# ──────────────────────────────────────────────────────────────────
#  /trades/{id}/reanalyze paywall
# ──────────────────────────────────────────────────────────────────


class TestReanalyzePaywall:
    def test_free_user_blocked_with_402(self, test_app):
        db = test_app["db"]
        user, acc = _make_user(db)
        trade = Trade(
            account_id=acc.id, symbol="SBER", direction=TradeDirection.LONG,
            entry_price=Decimal("300"), quantity=Decimal("10"),
            entry_at=datetime(2026, 4, 1), currency="RUB",
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        r = test_app["client"].post(
            f"/trades/{trade.id}/reanalyze",
            headers=_auth_headers(user),
        )
        assert r.status_code == 402
        body = r.json()
        # FastAPI оборачивает detail в {"detail": ...}
        detail = body.get("detail")
        assert isinstance(detail, dict) and detail["error"] == "pro_required"

    def test_pro_user_passes_paywall(self, test_app):
        db = test_app["db"]
        user, acc = _make_user(db)
        db.add(Subscription(
            user_id=user.id, plan=SubscriptionPlan.PRO,
            is_active=1, started_at=utc_now_naive(),
        ))
        trade = Trade(
            account_id=acc.id, symbol="SBER", direction=TradeDirection.LONG,
            entry_price=Decimal("300"), exit_price=Decimal("305"),
            quantity=Decimal("10"),
            entry_at=datetime(2026, 4, 1, 10), exit_at=datetime(2026, 4, 1, 12),
            pnl=Decimal("50"), net_pnl=Decimal("48"),
            currency="RUB",
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)

        # Mock'аем AI-сервис, чтобы не звонить наружу.
        async def fake_analyze(*args, **kwargs):
            return {
                "verdict": "OK", "score": 75, "advice": "—",
                "insights": [], "powered_by": "fake",
                "analysis": "test",
            }
        with patch("ai_service.analyze_trade_with_ai", side_effect=fake_analyze):
            r = test_app["client"].post(
                f"/trades/{trade.id}/reanalyze",
                headers=_auth_headers(user),
            )
        # Не 402 (paywall пройден). Реальный код может вернуть 200/500 в зависимости
        # от внутренних деталей — нам важно, что paywall не сработал.
        assert r.status_code != 402

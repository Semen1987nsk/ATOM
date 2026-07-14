"""
S1-10: refund/webhook не должен затрагивать чужие данные и не должен ронять
500 на кривом (но подписанном) payload.

1. `_deactivate_subscription` обновляла `Payment.status` по одному
   `external_id` без `filter(user_id)` — при коллизии external_id между
   юзерами деактивировался (и помечался REFUNDED) чужой Payment.
2. `int(user_id)` из webhook-metadata без try/except — невалидный
   `user_id` ронял 500 вместо 400.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DEBUG", "true")

from main import app  # noqa: E402
from models import Base, User, Account, Payment, PaymentStatus  # noqa: E402
from database import get_db  # noqa: E402
import auth_service  # noqa: E402
from utils.datetime_utils import utc_now_naive  # noqa: E402


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


class TestRefundScopedByUser:
    def test_deactivate_subscription_does_not_touch_other_user_payment(self, test_app):
        """Два юзера с Payment на один и тот же external_id (коллизия/рассинхрон).
        Refund по этому external_id для юзера A не должен трогать Payment юзера B.
        """
        db = test_app["db"]
        victim, _ = _make_user(db, "victim@example.com")
        attacker, _ = _make_user(db, "attacker@example.com")

        for u in (victim, attacker):
            db.add(Payment(
                user_id=u.id, amount=399, currency="RUB",
                status=PaymentStatus.COMPLETED, external_id="shared-ext",
                payment_method="yookassa", completed_at=utc_now_naive(),
            ))
        db.commit()

        from routers.payments import _deactivate_subscription
        _deactivate_subscription(db, attacker, "shared-ext")
        db.expire_all()

        victim_pmt = db.query(Payment).filter(Payment.user_id == victim.id).one()
        assert victim_pmt.status == PaymentStatus.COMPLETED, \
            "чужой Payment не должен помечаться REFUNDED"

        attacker_pmt = db.query(Payment).filter(Payment.user_id == attacker.id).one()
        assert attacker_pmt.status == PaymentStatus.REFUNDED, \
            "Payment самого юзера должен быть помечен REFUNDED"


class TestWebhookBadUserId:
    def test_invalid_user_id_in_metadata_returns_400_not_500(self, test_app):
        client = test_app["client"]
        r = client.post("/payments/webhook", json={
            "event": "payment.succeeded",
            "object": {
                "id": "x",
                "status": "succeeded",
                "amount": {"value": "1"},
                "metadata": {"user_id": "not-a-number", "plan": "pro"},
            },
        })
        assert r.status_code == 400, r.text

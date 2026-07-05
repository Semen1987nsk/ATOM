"""
Атомарная идемпотентность платёжного webhook (/payments/webhook).

YooKassa повторяет webhook до 30 раз, пока не получит 200. Если активация
подписки происходит ДО записи payment_attempts (замок по UNIQUE(external_id)),
ретрай-webhook с тем же payment_id может вызвать ДВОЙНУЮ активацию.

Контракт: два идентичных webhook подряд → ровно одна Subscription и один Payment.
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
from models import (  # noqa: E402
    Base, User, Account, Subscription, Payment, SubscriptionPlan, PaymentStatus,
    PaymentAttemptORM,
)
from utils.datetime_utils import utc_now_naive  # noqa: E402
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


class TestWebhookIdempotency:
    def test_duplicate_succeeded_webhook_activates_once(self, test_app):
        db = test_app["db"]
        user, _ = _make_user(db)
        client = test_app["client"]

        payload = {
            "payment_id": "pmt-dup-1",
            "user_email": user.email,
            "plan": "pro",
            "status": "succeeded",
            "amount": 399.0,
        }

        r1 = client.post("/payments/webhook", json=payload)
        assert r1.status_code == 200, r1.text

        # Идентичный ретрай (тот же payment_id) — YooKassa повторяет до 30 раз.
        r2 = client.post("/payments/webhook", json=payload)
        assert r2.status_code == 200, r2.text

        # Ровно одна подписка и один платёж — без двойной активации.
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        assert len(subs) == 1, f"ожидалась 1 Subscription, получено {len(subs)}"
        assert subs[0].plan == SubscriptionPlan.PRO
        assert subs[0].is_active == 1

        payments = db.query(Payment).filter(Payment.external_id == "pmt-dup-1").all()
        assert len(payments) == 1, f"ожидался 1 Payment, получено {len(payments)}"
        assert payments[0].status == PaymentStatus.COMPLETED

    def test_existing_attempt_lock_blocks_activation(self, test_app):
        """Замок уже взят конкурентным запросом (строка payment_attempts существует)
        с ЛЮБЫМ статусом → второй webhook не активирует подписку повторно.

        Воспроизводит реальный дефект: старый check `existing.status == target_status`
        пропускал активацию, если у уже-взятого замка статус отличался (напр. pending),
        → двойная активация. Замок = сам INSERT по UNIQUE(external_id), не сверка статуса.
        """
        db = test_app["db"]
        user, _ = _make_user(db)
        client = test_app["client"]

        # Конкурентный запрос уже вставил замок (другой/промежуточный статус).
        db.add(PaymentAttemptORM(
            external_id="pmt-lock-1",
            user_id=user.id,
            amount_rub=Decimal("399.0"),
            status="pending",
            created_at=utc_now_naive(),
        ))
        db.commit()

        r = client.post("/payments/webhook", json={
            "payment_id": "pmt-lock-1",
            "user_email": user.email,
            "plan": "pro",
            "status": "succeeded",
            "amount": 399.0,
        })
        assert r.status_code == 200, r.text

        # Замок уже был взят → подписка НЕ должна активироваться повторно.
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        assert len(subs) == 0, f"ожидалось 0 Subscription (замок взят), получено {len(subs)}"
        payments = db.query(Payment).filter(Payment.external_id == "pmt-lock-1").all()
        assert len(payments) == 0, f"ожидалось 0 Payment (замок взят), получено {len(payments)}"

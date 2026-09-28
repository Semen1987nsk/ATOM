"""refund.succeeded без metadata.user_id должен находить юзера по исходному
Payment (external_id == payment_id) и деактивировать его подписку."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DEBUG", "true")

from main import app
from models import Base, User, Subscription, SubscriptionPlan
from database import get_db
import auth_service


@pytest.fixture()
def app_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TS = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _o():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _o
    db = TS()
    yield TestClient(app), db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def test_refund_without_metadata_userid_finds_user(app_db):
    client, db = app_db
    u = User(email="p@e.com", name="P", hashed_password=auth_service.get_password_hash("password12345"), is_active=1, settings={})
    db.add(u); db.commit(); db.refresh(u)

    # Активируем через succeeded (создаётся Payment external_id=pmt-9).
    r1 = client.post("/payments/webhook", json={
        "event": "payment.succeeded",
        "object": {"id": "pmt-9", "status": "succeeded", "amount": {"value": "399.00"},
                   "metadata": {"user_id": str(u.id), "plan": "pro"}},
    })
    assert r1.status_code == 200, r1.text

    # Refund БЕЗ metadata.user_id — резолв через исходный Payment.
    r2 = client.post("/payments/webhook", json={
        "event": "refund.succeeded",
        "object": {"id": "rfnd-9", "payment_id": "pmt-9", "status": "succeeded", "amount": {"value": "399.00"}},
    })
    assert r2.status_code == 200, r2.text
    db.expire_all()
    subs = db.query(Subscription).filter(Subscription.user_id == u.id).all()
    assert all(s.is_active == 0 for s in subs)

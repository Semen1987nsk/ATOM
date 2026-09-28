"""
POST дубля сделки должен возвращать 409 (а не 500).

Дубль ловит UniqueConstraint uq_trades_dedup_v2
(account_id, symbol, entry_at, exit_at, direction, data_source) — models.py.
Регрессия: голый db.commit() в create_trade пробрасывал IntegrityError
наружу → FastAPI отдавал 500. Ожидаемое поведение — 409.

Заметка про NULL: в стандартном SQL (и SQLite, и PostgreSQL) NULL в UNIQUE
считаются различными, поэтому два ОТКРЫТЫХ трейда (exit_at IS NULL) НЕ
конфликтуют. Реальный дубль с коллизией возникает на пути закрытия
(is_closing): повторное закрытие проставляет одинаковый exit_at двум
записям с идентичным ключом → IntegrityError на db.commit() (~стр. 211).
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from models import Base, User, Account, Trade, TradeDirection  # noqa: E402
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


def _make_user(db):
    user = User(
        email="dup@example.com",
        name="Dup",
        hashed_password=auth_service.get_password_hash("testpass1234"),
        is_active=1,
        settings={},
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
    token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return {"Authorization": f"Bearer {token}"}


def test_duplicate_trade_returns_409_not_500(test_app):
    """POST одинаковой закрывающей сделки дважды → второй ответ 409, не 500."""
    db = test_app["db"]
    client = test_app["client"]
    user, acc = _make_user(db)

    entry_at = "2025-01-01T10:00:00"

    # Два ОТКРЫТЫХ LONG'а с идентичным dedup-ключом (exit_at=NULL → не конфликтуют).
    for _ in range(2):
        db.add(
            Trade(
                account_id=acc.id,
                symbol="SBER",
                direction=TradeDirection.LONG,
                entry_price=Decimal("300"),
                quantity=Decimal("10"),
                entry_at=datetime.fromisoformat(entry_at),
                data_source="manual",
            )
        )
    db.commit()

    closing_payload = {
        "symbol": "SBER",
        "direction": "short",
        "entry_price": 310.0,
        "quantity": 10,
        "entry_at": "2025-01-02T10:00:00",
    }

    # Первое закрытие: закрывает первый открытый LONG (проставляет exit_at).
    r1 = client.post("/trades/", json=closing_payload, headers=_auth_headers(user))
    assert r1.status_code == 200, r1.text

    # Повторное закрытие: закрывает второй LONG тем же exit_at → коллизия
    # uq_trades_dedup_v2. Должен быть 409, НЕ 500.
    r2 = client.post("/trades/", json=closing_payload, headers=_auth_headers(user))
    assert r2.status_code == 409, f"expected 409, got {r2.status_code}: {r2.text}"

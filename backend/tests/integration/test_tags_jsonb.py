"""PERF-08b: tag-фильтр в `/stats/` — через SQL на Postgres (JSONB + GIN),
Python-fallback на SQLite.

Sprint 3, Task 3.2. Тесты гоняются на SQLite (in-memory), поэтому здесь
проверяем семантику фильтра (что Python-fallback после декларации
`JSON().with_variant(JSONB(), 'postgresql')` не сломан) и идемпотентность
относительно регистра тегов в legacy-поведении.

Postgres-ветка (`tags @> '[tag]'`) тестируется отдельно при наличии
живого PG-инстанса; здесь — поведенческий регресс fallback'а.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Бэкенд в sys.path, чтобы импортнуть main/models/auth_service.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from main import app  # noqa: E402
from models import Base, User, Account, Trade, TradeDirection  # noqa: E402
from database import get_db  # noqa: E402
import auth_service  # noqa: E402


TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_app():
    engine = create_engine(
        TEST_DATABASE_URL,
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


@pytest.fixture
def test_user(test_app):
    db = test_app["db"]
    user = User(
        email="tags@example.com",
        name="Tags User",
        hashed_password=auth_service.get_password_hash("pwd123!!"),
        is_active=1,
        is_admin=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    account = Account(user_id=user.id, name="A", balance=0, currency="RUB")
    db.add(account)
    db.commit()
    db.refresh(account)
    return user, account


@pytest.fixture
def auth_headers(test_user):
    user, _ = test_user
    token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_trades_with_tags(test_app, test_user):
    """5 закрытых трейдов: 2 с тегом FOMO, 1 с Trend, 2 без тегов."""
    db = test_app["db"]
    _, account = test_user

    from datetime import datetime, timedelta

    base = datetime(2025, 1, 1, 10, 0, 0)
    # В подвыборку tag=FOMO попадают AAA, BBB, CCC. Среди них есть и
    # прибыльные, и убыточный (CCC) — нужно чтобы advanced-stats
    # сосчитал profit_factor/recovery_factor как число (UNDEFINED=None
    # сломал бы pydantic-валидацию response, это pre-existing schema-bug,
    # не связан с PERF-08b).
    specs = [
        ("AAA", ["FOMO"], 100.0),
        ("BBB", ["FOMO", "Trend"], 50.0),
        ("CCC", ["FOMO"], -30.0),  # убыточный → drawdown появляется
        ("DDD", ["Trend"], 20.0),
        ("EEE", None, 10.0),  # None → default=list = []
    ]
    for i, (symbol, tags, pnl) in enumerate(specs):
        kwargs = dict(
            account_id=account.id,
            symbol=symbol,
            direction=TradeDirection.LONG,
            entry_price=100,
            exit_price=110,
            quantity=10,
            entry_at=base + timedelta(hours=i),
            exit_at=base + timedelta(hours=i, minutes=30),
            pnl=pnl,
            net_pnl=pnl,
            commission=0,
        )
        if tags is not None:
            kwargs["tags"] = tags
        db.add(Trade(**kwargs))
    db.commit()
    return account


def test_stats_with_tag_filter_returns_only_matching(
    test_app, auth_headers, seed_trades_with_tags
):
    """SQLite-fallback: ?tag=FOMO учитывает только трейды с этим тегом.

    Семантика case-insensitive сохранена в Python-loop. После задачи
    Trade.tags объявлен dialect-aware (`JSON().with_variant(JSONB(), 'postgresql')`),
    но на SQLite это всё ещё JSON-колонка → fallback в роутере отрабатывает.
    """
    client = test_app["client"]
    resp = client.get("/stats/?tag=FOMO", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # В выдаче ожидаем 3 трейда (AAA + BBB + CCC) с tag=FOMO,
    # total_pnl = 100 + 50 - 30 = 120.
    assert body["total_trades"] == 3
    assert body["total_pnl"] == pytest.approx(120.0)


def test_stats_with_tag_filter_case_insensitive_on_sqlite(
    test_app, auth_headers, seed_trades_with_tags
):
    """SQLite-fallback оставлен case-insensitive (legacy-поведение).

    Postgres-путь (`tags @> '[tag]'`) — case-sensitive (см. concerns в diff).
    """
    client = test_app["client"]
    resp = client.get("/stats/?tag=fomo", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_trades"] == 3


def test_stats_with_tag_filter_no_match(test_app, auth_headers, seed_trades_with_tags):
    """Несуществующий тег → 0 трейдов, без падений."""
    client = test_app["client"]
    resp = client.get("/stats/?tag=DoesNotExist", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_trades"] == 0

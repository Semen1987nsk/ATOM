"""Контракт: скриншот отдаётся ТОЛЬКО через authenticated GET /trades/{id}/screenshot,
а публичный static /uploads мёртв. Фронт (S1-12) должен строить URL из этого маршрута,
а не из trade.screenshot_url (тот остаётся флагом наличия '/uploads/screenshots/<file>').
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import Base, User, Account, Trade, TradeDirection
from database import get_db
import auth_service

UPLOAD_DIR = Path("uploads/screenshots")


def test_static_uploads_route_absent():
    client = TestClient(app)
    # Публичный static-mount удалён — маршрут не зарегистрирован.
    resp = client.get("/uploads/screenshots/whatever.png")
    assert resp.status_code == 404


def test_trade_screenshot_route_registered():
    # Authenticated-маршрут существует (без токена → 401, не 404).
    client = TestClient(app)
    resp = client.get("/trades/1/screenshot")
    assert resp.status_code in (401, 403), f"ожидался auth-guard, получено {resp.status_code}"


# ==================== OWNERSHIP (S1-03) ====================
#
# Паттерн фикстур — как в test_pr26_endpoints.py (test_app с override get_db,
# _make_user, _auth_headers). Реальные коды подтверждены чтением
# routers/trades.py:899-948: владелец с существующим screenshot_url и файлом
# на диске → 200 FileResponse; сделка не найдена ИЛИ найдена, но принадлежит
# другому account_id (запрос отфильтрован по account_id) → 404 "Скриншот не
# найден" (единая ветка, отдельного 403 в коде нет).


@pytest.fixture
def test_app():
    """Fresh DB per test (тот же паттерн, что test_pr26_endpoints.py)."""
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


def _make_user(db, email):
    u = User(
        email=email,
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(user_id=u.id, name="Main", currency="RUB")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return u, acc


def _auth_headers(user):
    token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return {"Authorization": f"Bearer {token}"}


def _make_trade_with_screenshot(db, account, filename):
    """Кладёт реальный PNG на диск и создаёт Trade со screenshot_url на него."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fpath = UPLOAD_DIR / filename
    fpath.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    trade = Trade(
        account_id=account.id,
        symbol="SBER",
        direction=TradeDirection.LONG,
        entry_price=100.0,
        quantity=10,
        entry_at=datetime(2025, 1, 1, 10, 0, 0),
        screenshot_url=f"/uploads/screenshots/{filename}",
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade, fpath


def test_owner_gets_200_with_file_content(test_app):
    """Владелец с валидным токеном на СВОЮ сделку со скриншотом → 200 + содержимое."""
    db = test_app["db"]
    owner, acc = _make_user(db, "owner@test.com")
    trade, fpath = _make_trade_with_screenshot(db, acc, "owner_probe.png")

    try:
        resp = test_app["client"].get(
            f"/trades/{trade.id}/screenshot",
            headers=_auth_headers(owner),
        )
        assert resp.status_code == 200
        assert resp.content == fpath.read_bytes()
    finally:
        fpath.unlink(missing_ok=True)


def test_foreign_user_gets_404_on_other_users_trade(test_app):
    """Другой аутентифицированный пользователь на ЧУЖУЮ сделку → 404.

    routers/trades.py фильтрует Trade по (id, account_id=свой account_id) —
    для чужой сделки query не находит строку (`if not trade or not
    trade.screenshot_url: raise HTTPException(404)`), т.е. чужой запрос
    неотличим от несуществующей сделки — именно так и должно быть (не течёт
    информация о существовании чужой сделки через другой статус-код).
    """
    db = test_app["db"]
    owner, owner_acc = _make_user(db, "owner2@test.com")
    trade, fpath = _make_trade_with_screenshot(db, owner_acc, "foreign_probe.png")

    stranger, _ = _make_user(db, "stranger@test.com")

    try:
        resp = test_app["client"].get(
            f"/trades/{trade.id}/screenshot",
            headers=_auth_headers(stranger),
        )
        assert resp.status_code == 404
    finally:
        fpath.unlink(missing_ok=True)

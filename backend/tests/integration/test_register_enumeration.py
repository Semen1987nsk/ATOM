"""
S4-11 / B1 — /auth/register не должен раскрывать факт существования email.

VERIFICATION-FIRST: обе ветки (новый и существующий email) отдают БАЙТ-
идентичный нейтральный 202 БЕЗ авто-логина. Атакующий не может отличить
существующий email от свободного ни по коду, ни по телу, ни по наличию
Set-Cookie (CWE-204). Новый юзер создаётся в БД (is_active), но сессия
НЕ выдаётся — сначала подтверждение email.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from main import app
from models import Base, User
from database import get_db
import auth_service


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


@pytest.fixture
def seed_user(test_app):
    db = test_app["db"]
    u = User(
        email="exists@example.com",
        hashed_password=auth_service.get_password_hash("verylongpassword123"),
        is_active=1,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_register_does_not_leak_existing_email(test_app, seed_user):
    resp = test_app["client"].post(
        "/auth/register",
        json={
            "email": "exists@example.com",
            "password": "verylongpassword123",
            "pd_consent": True,
        },
    )
    # Не должно быть отличимого 400 «Email уже зарегистрирован».
    assert resp.status_code == 202
    assert "уже зарегистрирован" not in resp.text


def test_register_fresh_and_existing_are_byte_identical(test_app, seed_user):
    """B1: fresh email и existing email → идентичные (status, body, no Set-Cookie)."""
    client = test_app["client"]

    fresh = client.post(
        "/auth/register",
        json={
            "email": "brand-new@example.com",
            "password": "verylongpassword123",
            "pd_consent": True,
        },
    )
    existing = client.post(
        "/auth/register",
        json={
            "email": "exists@example.com",
            "password": "verylongpassword123",
            "pd_consent": True,
        },
    )

    # Статус идентичен.
    assert fresh.status_code == 202
    assert existing.status_code == fresh.status_code

    # НИ ОДНА ветка не ставит cookie — авто-логина нет.
    assert "set-cookie" not in {k.lower() for k in fresh.headers.keys()}
    assert "set-cookie" not in {k.lower() for k in existing.headers.keys()}

    # Тело идентично байт-в-байт.
    assert fresh.json() == existing.json()


def test_register_creates_user_without_session(test_app):
    """Happy-path: новый юзер создан (is_active), но сессия НЕ выдана."""
    client = test_app["client"]
    db = test_app["db"]

    resp = client.post(
        "/auth/register",
        json={
            "email": "new-user@example.com",
            "password": "verylongpassword123",
            "pd_consent": True,
        },
    )
    assert resp.status_code == 202
    # Нет access-cookie → юзер НЕ залогинен.
    assert auth_service.ACCESS_TOKEN_COOKIE_NAME not in resp.cookies

    # Но юзер создан в БД и активен.
    created = db.query(User).filter(User.email == "new-user@example.com").first()
    assert created is not None
    assert created.is_active == 1

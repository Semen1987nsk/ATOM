"""
S4-11 — /auth/register не должен раскрывать факт существования email.

Прямой ответ 400 «Email уже зарегистрирован» позволял перечислять
зарегистрированные почты. Ответ на существующий email должен быть
неотличим (по коду и телу) от нейтрального успешного ответа.
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
    assert resp.status_code in (200, 202)
    assert "уже зарегистрирован" not in resp.text

"""S4-29: PATCH /admin/users/{id}/feature-flags отклоняет неизвестные имена флагов."""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from main import app
from models import Base, User, Account
from database import get_db
import auth_service


@pytest.fixture
def test_app():
    """Fresh in-memory DB per test."""
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


def _make_user(db, email, is_admin=False):
    u = User(
        email=email,
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
        is_admin=1 if is_admin else 0,
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


@pytest.fixture
def seed_user(test_app):
    user, _ = _make_user(test_app["db"], "target@test.com")
    return user


@pytest.fixture
def admin_client(test_app):
    admin, _ = _make_user(test_app["db"], "admin@test.com", is_admin=True)
    test_app["client"].headers.update(_auth_headers(admin))
    return test_app["client"]


def test_unknown_flag_rejected(admin_client, seed_user):
    resp = admin_client.patch(
        f"/admin/users/{seed_user.id}/feature-flags",
        json={"totally-unknown-flag": True},
    )
    assert resp.status_code == 400


def test_known_flag_accepted(admin_client, seed_user):
    from routers.admin import ALLOWED_FEATURE_FLAGS
    known = next(iter(ALLOWED_FEATURE_FLAGS))
    resp = admin_client.patch(
        f"/admin/users/{seed_user.id}/feature-flags",
        json={known: True},
    )
    assert resp.status_code == 200

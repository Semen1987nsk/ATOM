"""S4-16: имперсонация — запрет имперсонации админов + блок деструктивных операций.

Покрытие:
- Нельзя имперсонировать пользователя с is_admin=True (403).
- Под impersonation-токеном деструктивная DELETE /auth/me запрещена (403, non-repudiation).
- Под impersonation-токеном запрещён PII-экспорт GET /auth/me/export (403).
- Под impersonation-токеном запрещена смена пароля POST /auth/change-password (403).
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


def test_cannot_impersonate_admin(test_app):
    db = test_app["db"]
    admin, _ = _make_user(db, "admin@test.com", is_admin=True)
    target_admin, _ = _make_user(db, "other-admin@test.com", is_admin=True)

    resp = test_app["client"].post(
        f"/admin/users/{target_admin.id}/impersonate",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


def test_destructive_op_blocked_under_impersonation(test_app):
    db = test_app["db"]
    admin, _ = _make_user(db, "admin@test.com", is_admin=True)
    target, _ = _make_user(db, "target@test.com")

    imp_token = auth_service.create_access_token(
        data={
            "sub": str(target.id),
            "email": target.email,
            "impersonated_by": admin.id,
        }
    )
    resp = test_app["client"].request(
        "DELETE",
        "/auth/me",
        headers={"Authorization": f"Bearer {imp_token}"},
        json={"password": "pass1234", "reason": "test"},
    )
    assert resp.status_code == 403
    assert "имперсонац" in resp.json()["detail"].lower()


def _impersonation_headers(db, target_email="target@test.com"):
    admin, _ = _make_user(db, "admin@test.com", is_admin=True)
    target, _ = _make_user(db, target_email)
    imp_token = auth_service.create_access_token(
        data={
            "sub": str(target.id),
            "email": target.email,
            "impersonated_by": admin.id,
        }
    )
    return {"Authorization": f"Bearer {imp_token}"}


def test_pii_export_blocked_under_impersonation(test_app):
    headers = _impersonation_headers(test_app["db"])
    resp = test_app["client"].get("/auth/me/export", headers=headers)
    assert resp.status_code == 403
    assert "имперсонац" in resp.json()["detail"].lower()


def test_change_password_blocked_under_impersonation(test_app):
    headers = _impersonation_headers(test_app["db"])
    resp = test_app["client"].post(
        "/auth/change-password",
        headers=headers,
        json={"old_password": "pass1234", "new_password": "newpass123456"},
    )
    assert resp.status_code == 403
    assert "имперсонац" in resp.json()["detail"].lower()


def test_2fa_enable_blocked_under_impersonation(test_app):
    # I2 (CWE-285): имперсонирующий админ не должен менять 2FA чужого аккаунта.
    headers = _impersonation_headers(test_app["db"])
    resp = test_app["client"].post("/auth/2fa/enable", headers=headers)
    assert resp.status_code == 403
    assert "имперсонац" in resp.json()["detail"].lower()


def test_2fa_disable_blocked_under_impersonation(test_app):
    # I2 (CWE-285): отключение 2FA под impersonation-токеном запрещено.
    headers = _impersonation_headers(test_app["db"])
    resp = test_app["client"].post(
        "/auth/2fa/disable",
        headers=headers,
        json={"code": "000000"},
    )
    assert resp.status_code == 403
    assert "имперсонац" in resp.json()["detail"].lower()


def test_2fa_verify_blocked_under_impersonation(test_app):
    # I2 (CWE-285): активация 2FA (totp_enabled=True) под impersonation-токеном запрещена.
    headers = _impersonation_headers(test_app["db"])
    resp = test_app["client"].post(
        "/auth/2fa/verify",
        headers=headers,
        json={"code": "000000"},
    )
    assert resp.status_code == 403
    assert "имперсонац" in resp.json()["detail"].lower()

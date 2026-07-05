"""2FA-enforcement на входе. При totp_enabled логин без валидного кода = 401,
финальная пара токенов не выдаётся. Без 2FA — вход как раньше.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DEBUG", "true")

from main import app
from models import Base, User
from database import get_db
import auth_service


@pytest.fixture()
def app_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TS = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    db = TS()
    yield TestClient(app), db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _user(db, enabled, secret=None):
    u = User(
        email="a@b.com", name="A",
        hashed_password=auth_service.get_password_hash("password12345"),
        is_active=1, settings={},
        totp_enabled=enabled, totp_secret=secret,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_login_without_2fa_succeeds(app_db):
    client, db = app_db
    _user(db, enabled=False)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345"})
    assert r.status_code == 200, r.text


def test_login_with_2fa_missing_code_rejected(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345"})
    assert r.status_code == 401, r.text


def test_login_with_2fa_valid_code_succeeds(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    code = pyotp.TOTP(secret).now()
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": code})
    assert r.status_code == 200, r.text


def test_login_with_2fa_wrong_code_rejected(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": "000000"})
    assert r.status_code == 401, r.text

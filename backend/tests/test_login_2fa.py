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
    # S1-06c: сигнал должен быть машиночитаемым (detail.totp_required=true),
    # а не brittle-match по тексту detail-строки — фронт по нему решает,
    # показывать ли поле ввода кода вместо голой ошибки "неверный пароль".
    # Формат detail-dict уже используется в кодовой базе (см. pro_required
    # в subscription_service.py) — FastAPI кладёт exc.detail как есть под
    # ключ "detail" в JSON-теле ответа.
    body = r.json()
    assert isinstance(body.get("detail"), dict), r.text
    assert body["detail"].get("totp_required") is True, r.text


def test_login_with_2fa_valid_code_succeeds(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    code = pyotp.TOTP(secret).now()
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": code})
    assert r.status_code == 200, r.text


def test_login_with_2fa_code_replay_rejected(app_db):
    # S4-10 regression: login-эндпоинт обязан персистить totp_last_used_step
    # между запросами (db.commit). Тот же валидный код второй раз → 401
    # totp_required. RED без db.commit() в /auth/login (шаг не сохранился бы).
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    code = pyotp.TOTP(secret).now()

    r1 = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": code})
    assert r1.status_code == 200, r1.text

    r2 = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": code})
    assert r2.status_code == 401, r2.text
    body = r2.json()
    assert isinstance(body.get("detail"), dict), r2.text
    assert body["detail"].get("totp_required") is True, r2.text


def test_login_with_2fa_wrong_code_rejected(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": "000000"})
    assert r.status_code == 401, r.text
    # Неверный (но присутствующий) код — тоже 2FA-required сигнал, юзер
    # остаётся на шаге ввода кода, не откатывается к email/password форме.
    body = r.json()
    assert isinstance(body.get("detail"), dict), r.text
    assert body["detail"].get("totp_required") is True, r.text


def test_login_wrong_password_has_no_totp_required_flag(app_db):
    client, db = app_db
    _user(db, enabled=False)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong-password"})
    assert r.status_code == 401, r.text
    # Обычный неверный пароль НЕ должен нести totp_required — иначе фронт
    # ошибочно покажет поле кода для юзера без включённой 2FA. detail тут
    # остаётся простой строкой (как раньше), не dict.
    body = r.json()
    assert not isinstance(body.get("detail"), dict), r.text


def test_login_wrong_password_with_2fa_enabled_has_no_totp_required_flag(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong-password"})
    assert r.status_code == 401, r.text
    # Неверный пароль на 2FA-включённом аккаунте — тоже обычная ошибка
    # аутентификации, а не 2FA-required сигнал: brute-force пароля не должен
    # получать машиночитаемое подтверждение "код нужен только на верном пароле".
    body = r.json()
    assert not isinstance(body.get("detail"), dict), r.text

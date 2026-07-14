"""S1-06b: OAuth callback должен уважать 2FA (totp_enabled), а не выдавать
полную сессию в обход TOTP-кода.

Юзер с totp_enabled=True, вошедший через OAuth-провайдера, получает
pending-2FA токен (короткий TTL, отдельный scope) вместо полной пары
access/refresh — и должен подтвердить TOTP-код через
POST /auth/oauth/2fa/verify, прежде чем получить сессию.
"""
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DEBUG", "true")

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import Base, User
from database import get_db
from config import settings
import auth_service
import oauth_service


ALLOWED_REDIRECT = "https://app.empirik.io/auth/callback"


@pytest.fixture()
def app_db(monkeypatch):
    monkeypatch.setattr(settings, "OAUTH_ALLOWED_REDIRECT_URIS", [ALLOWED_REDIRECT])

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


def _oauth_user(db, email="oauth@b.com", enabled=False, secret=None):
    u = User(
        email=email,
        name="OAuth User",
        hashed_password=None,
        oauth_provider="google",
        oauth_provider_id="provider-123",
        is_active=1,
        settings={},
        totp_enabled=enabled,
        totp_secret=secret,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


_FAKE_PROVIDER = oauth_service.OAuthProvider(
    name="Google",
    client_id="fake-client-id",
    client_secret="fake-client-secret",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
    scope="openid email profile",
)


def _do_oauth_callback(client, email):
    """Проходит authorize→callback с замоканным провайдером/token-exchange,
    возвращает Response от POST /auth/oauth/{provider}/callback."""
    with patch.object(oauth_service, "get_provider", return_value=_FAKE_PROVIDER):
        authorize_resp = client.get(
            "/auth/oauth/google/authorize",
            params={"redirect_uri": ALLOWED_REDIRECT},
        )
        assert authorize_resp.status_code == 200, authorize_resp.text
        state = authorize_resp.json()["state"]

        with patch.object(
            oauth_service, "exchange_code_for_token", new=AsyncMock(return_value={"access_token": "provider-access-token"})
        ), patch.object(
            oauth_service, "get_user_info", new=AsyncMock(return_value={"email": email, "name": "OAuth User", "id": "provider-123"})
        ):
            return client.post(
                "/auth/oauth/google/callback",
                params={"code": "auth-code-xyz", "state": state, "redirect_uri": ALLOWED_REDIRECT},
            )


# ==================== (а) OAuth callback с 2FA включён — НЕ полная сессия ====================

def test_oauth_callback_with_2fa_does_not_grant_full_session(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _oauth_user(db, email="2fa@b.com", enabled=True, secret=secret)

    r = _do_oauth_callback(client, "2fa@b.com")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("two_factor_required") is True
    assert body.get("pending_token")

    # Нет валидных auth cookies — access_token cookie отсутствует или не
    # принимается get_current_user как полноценная сессия.
    access_cookie = client.cookies.get(auth_service.ACCESS_TOKEN_COOKIE_NAME)
    if access_cookie:
        assert auth_service.decode_access_token(access_cookie) is None

    me = client.get("/auth/me")
    assert me.status_code == 401


# ==================== (б) verify с верным кодом — полная сессия ====================

def test_oauth_2fa_verify_with_valid_code_grants_full_session(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    user = _oauth_user(db, email="2fa-ok@b.com", enabled=True, secret=secret)

    r = _do_oauth_callback(client, "2fa-ok@b.com")
    pending_token = r.json()["pending_token"]

    code = pyotp.TOTP(secret).now()
    verify_resp = client.post(
        "/auth/oauth/2fa/verify",
        json={"pending_token": pending_token, "code": code},
    )

    assert verify_resp.status_code == 200, verify_resp.text
    body = verify_resp.json()
    assert body.get("authenticated") is True

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == user.id


# ==================== (б2) РЕГРЕСС S4-10: replay того же кода отклонён ====================

def test_oauth_2fa_verify_code_replay_rejected(app_db):
    # S4-10 regression: oauth/2fa/verify обязан персистить totp_last_used_step
    # между запросами (db.commit). Один pending_token + тот же код дважды →
    # первый 200, второй 401. RED без db.commit() в /auth/oauth/2fa/verify.
    client, db = app_db
    secret = pyotp.random_base32()
    _oauth_user(db, email="2fa-replay@b.com", enabled=True, secret=secret)

    r = _do_oauth_callback(client, "2fa-replay@b.com")
    pending_token = r.json()["pending_token"]
    code = pyotp.TOTP(secret).now()

    first = client.post(
        "/auth/oauth/2fa/verify",
        json={"pending_token": pending_token, "code": code},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/auth/oauth/2fa/verify",
        json={"pending_token": pending_token, "code": code},
    )
    assert second.status_code == 401, second.text


# ==================== (в) verify с неверным кодом — 401, сессии нет ====================

def test_oauth_2fa_verify_with_invalid_code_rejected(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _oauth_user(db, email="2fa-bad@b.com", enabled=True, secret=secret)

    r = _do_oauth_callback(client, "2fa-bad@b.com")
    pending_token = r.json()["pending_token"]

    verify_resp = client.post(
        "/auth/oauth/2fa/verify",
        json={"pending_token": pending_token, "code": "000000"},
    )

    assert verify_resp.status_code == 401

    me = client.get("/auth/me")
    assert me.status_code == 401


# ==================== (г) pending-токен не работает как обычная сессия ====================

def test_pending_token_rejected_by_get_current_user(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _oauth_user(db, email="2fa-pending@b.com", enabled=True, secret=secret)

    r = _do_oauth_callback(client, "2fa-pending@b.com")
    pending_token = r.json()["pending_token"]

    # Прямая проверка декодера: pending-токен не проходит decode_access_token.
    assert auth_service.decode_access_token(pending_token) is None

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {pending_token}"})
    assert me.status_code == 401


# ==================== (д) РЕГРЕСС: OAuth без 2FA — полная сессия как раньше ====================

def test_oauth_callback_without_2fa_grants_full_session_as_before(app_db):
    client, db = app_db
    _oauth_user(db, email="no2fa@b.com", enabled=False)

    r = _do_oauth_callback(client, "no2fa@b.com")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("authenticated") is True
    assert "two_factor_required" not in body or body.get("two_factor_required") is False

    me = client.get("/auth/me")
    assert me.status_code == 200

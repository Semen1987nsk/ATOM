import jwt as _pyjwt
import auth_service

from tests.integration.test_pr26_endpoints import _make_user, _auth_headers, test_app


def test_tokens_use_pyjwt_not_jose():
    assert hasattr(auth_service.jwt, "ExpiredSignatureError")
    assert auth_service.jwt.__name__ == "jwt"


def test_access_token_roundtrip_hs256():
    tok = auth_service.create_access_token({"sub": "1", "email": "a@b.c"})
    payload = _pyjwt.decode(tok, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
    assert payload["sub"] == "1"
    assert payload["type"] == "access"
    assert payload["jti"]


def test_expired_access_token_returns_none():
    from datetime import timedelta
    tok = auth_service.create_access_token({"sub": "1", "email": "a@b.c"}, expires_delta=timedelta(seconds=-1))
    assert auth_service.decode_access_token(tok) is None


def test_wrong_secret_refresh_returns_none():
    bad = _pyjwt.encode({"sub": "1", "type": "refresh", "jti": "x"}, "WRONG", algorithm="HS256")
    assert auth_service.decode_refresh_token(bad) is None


def test_change_password_rejects_short_new_password(test_app):
    db = test_app["db"]
    user, _ = _make_user(db, "pw@test.com")
    r = test_app["client"].post(
        "/auth/change-password",
        json={"old_password": "pass1234", "new_password": "short11chr"},
        headers=_auth_headers(user),
    )
    assert r.status_code in (400, 422)


def test_password_reset_invalidates_existing_access_token(test_app):
    db = test_app["db"]
    from models import PasswordResetTokenORM
    from utils.datetime_utils import utc_now_naive
    from datetime import timedelta
    user, _ = _make_user(db, "inv@test.com")
    headers = _auth_headers(user)
    assert test_app["client"].get("/auth/me", headers=headers).status_code == 200
    db.add(PasswordResetTokenORM(token="reset-inv-1", user_id=user.id,
        created_at=utc_now_naive(), expires_at=utc_now_naive()+timedelta(hours=1)))
    db.commit()
    r = test_app["client"].post("/auth/password-reset/confirm",
        json={"token": "reset-inv-1", "new_password": "brandnew_password_123"})
    assert r.status_code == 200
    assert test_app["client"].get("/auth/me", headers=headers).status_code == 401


def test_refresh_rotates_and_revokes_old_token(test_app):
    db = test_app["db"]
    user, _ = _make_user(db, "rot@test.com")
    _, refresh = auth_service.create_token_pair(user.id, user.email)
    r1 = test_app["client"].post("/auth/refresh", json={"refresh_token": refresh})
    assert r1.status_code == 200
    new_refresh = r1.json().get("refresh_token")  # см. SEC-08 — если тело без токена, читать из cookie
    # r1 поставил CSRF/auth cookies; чистим их, чтобы replay был чистым body-token
    # запросом (иначе CSRFMiddleware вернёт 403 раньше reuse-detection).
    test_app["client"].cookies.clear()
    r2 = test_app["client"].post("/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401


def test_account_lockout_after_max_failed_attempts(test_app, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 3)
    db = test_app["db"]
    user, _ = _make_user(db, "lock@test.com")
    for _ in range(3):
        test_app["client"].post("/auth/login", json={"email": "lock@test.com", "password": "wrong-pass-12"})
    db.refresh(user)
    assert user.locked_until is not None
    # даже верный пароль теперь отвергается
    r = test_app["client"].post("/auth/login", json={"email": "lock@test.com", "password": "pass1234"})
    assert r.status_code in (401, 423, 429)


def test_login_does_not_return_token_in_body(test_app):
    db = test_app["db"]; _make_user(db, "body@test.com")
    r = test_app["client"].post("/auth/login", json={"email": "body@test.com", "password": "pass1234"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" not in body and "refresh_token" not in body
    assert any("access" in c for c in r.cookies)  # cookie всё ещё ставится


def test_mask_email_redacts_pii():
    from utils.log_redaction import mask_email
    out = mask_email("alice@example.com")
    assert "alice" not in out and "example" not in out and out.endswith(".com")
    assert mask_email("") == "<none>" and mask_email(None) == "<none>"


def test_oauth_authorize_rejects_unlisted_redirect(test_app, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "OAUTH_ALLOWED_REDIRECT_URIS", ["https://app.empirik.io/auth/callback"])
    r = test_app["client"].get("/auth/oauth/google/authorize",
        params={"redirect_uri": "https://evil.example.com/steal"})
    assert r.status_code == 400


def test_reset_confirm_is_post_only(test_app):
    r = test_app["client"].get("/auth/password-reset/confirm?token=x&new_password=yyyyyyyyyyyy")
    assert r.status_code in (404, 405)

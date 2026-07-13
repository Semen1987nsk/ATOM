"""
Integration tests для PR 26 — security endpoints + admin + payments + auth flows.

Покрытие:
- Admin endpoints: multi-tenant, audit, impersonate, reset-broker
- YooKassa webhook: HMAC verify, idempotency, refund
- Password reset: request → confirm с anti-enumeration
- Email verification: register hook → verify token → resend
- 2FA TOTP: enable/verify/disable

Все тесты используют in-memory SQLite через стандартную фикстуру `test_app`.
"""

import hashlib
import hmac
import json
import pytest
import sys
import os
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import (
    Base, User, Account, BrokerConnection, BrokerType,
    AdminAuditLogORM, RevokedTokenORM, PasswordResetTokenORM,
    PaymentAttemptORM, Subscription, SubscriptionPlan,
)
from database import get_db
import auth_service
from utils.datetime_utils import utc_now_naive


@pytest.fixture
def test_app():
    """Fresh DB per test."""
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
    yield {"client": TestClient(app), "db": db_session, "Session": TestingSessionLocal}
    db_session.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _make_user(db, email="user@test.com", is_admin=False):
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


# ==================== ADMIN MULTI-TENANT (Scenario #1) ====================

class TestAdminMultiTenant:
    def test_sync_health_404_for_unknown_account(self, test_app):
        """PR 26 fix: /admin/sync-health/{id} 404, не 500 и не утечка."""
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        r = test_app["client"].get(
            "/admin/sync-health/99999",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 404

    def test_sync_health_writes_audit_log(self, test_app):
        """Просмотр чужого account админом → audit-log entry."""
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        target_user, target_acc = _make_user(db, "u2@test.com")

        r = test_app["client"].get(
            f"/admin/sync-health/{target_acc.id}",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 200

        # Audit log: одна запись о view_sync_health
        entries = db.query(AdminAuditLogORM).filter(
            AdminAuditLogORM.action == "view_sync_health"
        ).all()
        assert len(entries) == 1
        assert entries[0].actor_user_id == admin.id
        assert entries[0].target_account_id == target_acc.id

    def test_non_admin_blocked(self, test_app):
        """Обычный юзер не может звать admin endpoints."""
        db = test_app["db"]
        regular, _ = _make_user(db, "u@test.com", is_admin=False)
        r = test_app["client"].get(
            "/admin/sync-health/1",
            headers=_auth_headers(regular),
        )
        assert r.status_code == 403


# ==================== ADMIN IMPERSONATE + AUDIT ====================

class TestAdminImpersonate:
    def test_impersonate_creates_short_jwt(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        target, _ = _make_user(db, "target@test.com")

        r = test_app["client"].post(
            f"/admin/users/{target.id}/impersonate",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["access_token"]
        assert data["expires_in_minutes"] == 15
        assert data["target_user_id"] == target.id

        # Audit log записан
        entries = db.query(AdminAuditLogORM).filter(
            AdminAuditLogORM.action == "impersonate"
        ).all()
        assert len(entries) == 1

    def test_cannot_impersonate_self(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        r = test_app["client"].post(
            f"/admin/users/{admin.id}/impersonate",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 400

    def test_impersonate_404_unknown_user(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        r = test_app["client"].post(
            "/admin/users/99999/impersonate",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 404


class TestAdminResetBroker:
    def test_reset_broker_requires_confirm(self, test_app):
        """confirm param обязан совпадать с account_id."""
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        target, acc = _make_user(db, "t@test.com")

        r = test_app["client"].post(
            f"/admin/users/{target.id}/reset-broker?account_id={acc.id}&confirm=99",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 400
        assert "confirm" in r.json()["detail"].lower()

    def test_reset_broker_wrong_user(self, test_app):
        """Reset для чужого account → 400."""
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        u1, acc1 = _make_user(db, "u1@test.com")
        u2, _ = _make_user(db, "u2@test.com")

        r = test_app["client"].post(
            f"/admin/users/{u2.id}/reset-broker?account_id={acc1.id}&confirm={acc1.id}",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 400


# ==================== JWT REVOCATION (Scenario #3) ====================

class TestJwtRevocation:
    def test_logout_revokes_jwt(self, test_app):
        """После logout тот же JWT возвращает 401."""
        db = test_app["db"]
        user, _ = _make_user(db, "u@test.com")
        headers = _auth_headers(user)

        # До logout — работает
        r = test_app["client"].get("/auth/me", headers=headers)
        assert r.status_code == 200

        # Logout
        r = test_app["client"].post("/auth/logout", headers=headers)
        assert r.status_code in (200, 204)

        # После logout — должно быть 401 (jti revoked)
        r = test_app["client"].get("/auth/me", headers=headers)
        assert r.status_code == 401

        # В DB есть запись о revoked jti
        assert db.query(RevokedTokenORM).count() >= 1


# ==================== YOOKASSA WEBHOOK (Scenarios #79, #80, #83, #84) ====================

class TestYooKassaWebhook:
    def test_webhook_requires_signature_in_prod(self, test_app, monkeypatch):
        """Без YOOKASSA_WEBHOOK_SECRET в prod — отклоняем."""
        # DEBUG=true по умолчанию в тестах → разрешаем stub format без HMAC
        # Чтобы проверить prod-режим, нужен monkey-patch settings.DEBUG
        from config import settings
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.delenv("YOOKASSA_WEBHOOK_SECRET", raising=False)

        payload = {"event": "payment.succeeded", "object": {"id": "p1", "status": "succeeded"}}
        r = test_app["client"].post(
            "/payments/webhook",
            json=payload,
            headers={"X-YooKassa-Signature": "fake"},
        )
        # Prod без YOOKASSA_WEBHOOK_SECRET → 500 (config error)
        assert r.status_code in (500, 403)

    def test_webhook_rejects_wrong_hmac(self, test_app, monkeypatch):
        monkeypatch.setenv("YOOKASSA_WEBHOOK_SECRET", "secret")

        body = b'{"event":"payment.succeeded","object":{"id":"p1"}}'
        wrong_sig = "wrongsignature"
        r = test_app["client"].post(
            "/payments/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-YooKassa-Signature": wrong_sig,
            },
        )
        assert r.status_code == 403

    def test_webhook_idempotency_via_payment_attempts(self, test_app, monkeypatch):
        """Повторный webhook с тем же payment_id → 200 idempotent."""
        from config import settings
        monkeypatch.setattr(settings, "DEBUG", True)
        # В DEBUG режиме стаб-формат принимается без HMAC

        db = test_app["db"]
        user, _ = _make_user(db, "u@test.com")

        payload = {
            "payment_id": "yk-test-001",
            "user_email": "u@test.com",
            "plan": "pro",
            "status": "succeeded",
            "amount": 399.0,
        }

        # Первый раз — активирует
        r = test_app["client"].post("/payments/webhook", json=payload)
        assert r.status_code == 200

        # Записан в payment_attempts
        attempts = db.query(PaymentAttemptORM).filter(
            PaymentAttemptORM.external_id == "yk-test-001"
        ).all()
        assert len(attempts) == 1

        # Повторный webhook — idempotent
        r = test_app["client"].post("/payments/webhook", json=payload)
        assert r.status_code == 200
        # Кол-во записей не увеличилось
        attempts = db.query(PaymentAttemptORM).filter(
            PaymentAttemptORM.external_id == "yk-test-001"
        ).all()
        assert len(attempts) == 1

    def test_stub_confirm_blocked_in_prod(self, test_app, monkeypatch):
        """Scenario #80: stub-confirm работает ТОЛЬКО в DEBUG."""
        from config import settings
        monkeypatch.setattr(settings, "DEBUG", False)

        r = test_app["client"].get(
            "/payments/stub-confirm?payment_id=p1&user=u@test.com&plan=pro&amount=399"
        )
        assert r.status_code == 404


# ==================== PASSWORD RESET ====================

class TestPasswordReset:
    def test_reset_request_always_202(self, test_app):
        """Anti-enumeration: 202 для существующего и несуществующего email."""
        db = test_app["db"]
        _make_user(db, "exists@test.com")

        # Существующий
        r1 = test_app["client"].post(
            "/auth/password-reset/request",
            json={"email": "exists@test.com"},
        )
        assert r1.status_code == 202

        # Несуществующий
        r2 = test_app["client"].post(
            "/auth/password-reset/request",
            json={"email": "nobody@test.com"},
        )
        assert r2.status_code == 202

        # Ответы идентичны (нет утечки информации)
        assert r1.json() == r2.json()

    def test_reset_confirm_invalid_token(self, test_app):
        # пароль 12+ символов (API-06), чтобы дойти до ветки invalid-token (400),
        # а не отсечься валидатором длины (422)
        r = test_app["client"].post(
            "/auth/password-reset/confirm",
            json={"token": "invalid", "new_password": "newpassword123"},
        )
        assert r.status_code == 400

    def test_reset_confirm_full_flow(self, test_app):
        """Request → use token → login with new pwd."""
        db = test_app["db"]
        user, _ = _make_user(db, "reset@test.com")

        test_app["client"].post(
            "/auth/password-reset/request",
            json={"email": "reset@test.com"},
        )

        # Берём токен прямо из БД (в проде идёт через email)
        token_row = db.query(PasswordResetTokenORM).filter(
            PasswordResetTokenORM.user_id == user.id
        ).first()
        assert token_row is not None

        # Confirm
        r = test_app["client"].post(
            "/auth/password-reset/confirm",
            json={"token": token_row.token, "new_password": "longpassword456"},
        )
        assert r.status_code == 200

        # Login с новым паролем работает
        r = test_app["client"].post(
            "/auth/login",
            json={"email": "reset@test.com", "password": "longpassword456"},
        )
        assert r.status_code == 200

        # Token помечен used (used_at != NULL)
        test_app["db"].refresh(token_row)
        assert token_row.used_at is not None


# ==================== EMAIL VERIFICATION ====================

class TestEmailVerification:
    def test_register_issues_verification_token(self, test_app):
        """После register у юзера должен быть verification_token."""
        r = test_app["client"].post(
            "/auth/register",
            json={
                "email": "newuser@test.com",
                "password": "longpassword123",  # min 12 chars per OWASP
                "name": "New",
                "pd_consent": True,
            },
        )
        assert r.status_code == 200

        db = test_app["db"]
        user = db.query(User).filter(User.email == "newuser@test.com").first()
        assert user is not None
        assert user.email_verification_token is not None
        assert user.email_verified is False

    def test_verify_email_with_valid_token(self, test_app):
        db = test_app["db"]
        # Manually create user with token
        import secrets
        token = secrets.token_urlsafe(32)
        u = User(
            email="verify@test.com",
            hashed_password=auth_service.get_password_hash("p"),
            is_active=1,
            email_verification_token=token,
            email_verification_sent_at=utc_now_naive(),
        )
        db.add(u)
        db.commit()

        r = test_app["client"].get(f"/auth/verify-email?token={token}")
        assert r.status_code == 200

        db.refresh(u)
        assert u.email_verified is True
        assert u.email_verification_token is None

    def test_verify_email_invalid_token(self, test_app):
        r = test_app["client"].get("/auth/verify-email?token=garbage")
        assert r.status_code == 404


# ==================== 2FA TOTP ====================

class TestTotp:
    def test_enable_returns_secret_and_uri(self, test_app):
        db = test_app["db"]
        user, _ = _make_user(db, "totp@test.com")
        r = test_app["client"].post("/auth/2fa/enable", headers=_auth_headers(user))
        assert r.status_code == 200
        data = r.json()
        assert "secret" in data
        assert data["provisioning_uri"].startswith("otpauth://")

    def test_enable_blocked_if_already_active(self, test_app):
        db = test_app["db"]
        user, _ = _make_user(db, "totp2@test.com")
        user.totp_enabled = True
        db.commit()
        r = test_app["client"].post("/auth/2fa/enable", headers=_auth_headers(user))
        assert r.status_code == 400

    def test_verify_with_invalid_code(self, test_app):
        db = test_app["db"]
        user, _ = _make_user(db, "totp3@test.com")
        # Enable first
        test_app["client"].post("/auth/2fa/enable", headers=_auth_headers(user))
        r = test_app["client"].post(
            "/auth/2fa/verify",
            json={"code": "000000"},
            headers=_auth_headers(user),
        )
        assert r.status_code == 400

    def test_code_replay_rejected_and_step_persisted(self, test_app):
        """S4-10: один и тот же TOTP-код принимается один раз, повтор → 400.

        Проверяет полный replay-вектор через эндпоинт (не только unit): шаг
        сохраняется в БД (db.refresh), поэтому второй запрос видит guard.
        """
        import pyotp

        db = test_app["db"]
        user, _ = _make_user(db, "replay@test.com")
        # Сеем секрет напрямую через ORM — так знаем код для генерации.
        secret = pyotp.random_base32()
        user.totp_secret = secret
        user.totp_last_used_step = None
        db.commit()

        code = pyotp.TOTP(secret).now()

        # Первый ввод — принят, 2FA активирована.
        r1 = test_app["client"].post(
            "/auth/2fa/verify",
            json={"code": code},
            headers=_auth_headers(user),
        )
        assert r1.status_code == 200

        # totp_last_used_step персистнут в БД.
        db.refresh(user)
        assert user.totp_last_used_step is not None

        # Повтор того же кода — replay, отклонён.
        r2 = test_app["client"].post(
            "/auth/2fa/verify",
            json={"code": code},
            headers=_auth_headers(user),
        )
        assert r2.status_code == 400


# ==================== SECURITY HEADERS ====================

class TestSecurityHeaders:
    def test_security_headers_present(self, test_app):
        """PR 26: каждый response имеет X-Frame-Options + X-Content-Type-Options + CSP."""
        r = test_app["client"].get("/")
        assert r.status_code == 200
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert r.headers.get("Content-Security-Policy")


# ==================== DOCS GATING ====================

class TestDocsGating:
    def test_docs_blocked_when_not_debug(self, test_app, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "DEBUG", False)
        r = test_app["client"].get("/docs")
        assert r.status_code == 404


# ==================== ADMIN PHASE 1 ENDPOINTS ====================

class TestAdminPhase1:
    def test_user_snapshot(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        target, _ = _make_user(db, "target@test.com")
        r = test_app["client"].get(
            f"/admin/users/{target.id}/snapshot",
            headers=_auth_headers(admin),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["id"] == target.id
        assert "accounts" in data

    def test_sync_queue(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        r = test_app["client"].get("/admin/sync-queue", headers=_auth_headers(admin))
        assert r.status_code == 200
        data = r.json()
        assert "circuit_open" in data
        assert "stale_24h" in data
        assert "healthy" in data

    def test_db_stats(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        r = test_app["client"].get("/admin/db-stats", headers=_auth_headers(admin))
        assert r.status_code == 200
        data = r.json()
        assert "row_counts" in data
        assert "users" in data["row_counts"]

    def test_audit_log_endpoint(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        target, _ = _make_user(db, "target@test.com")

        # Совершаем audit-action
        test_app["client"].post(
            f"/admin/users/{target.id}/toggle-active",
            headers=_auth_headers(admin),
        )

        # Audit log endpoint возвращает запись
        r = test_app["client"].get("/admin/audit-log", headers=_auth_headers(admin))
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert any(e["action"] == "toggle_active" for e in entries)

    def test_slo_endpoint(self, test_app):
        db = test_app["db"]
        admin, _ = _make_user(db, "admin@test.com", is_admin=True)
        r = test_app["client"].get("/admin/slo", headers=_auth_headers(admin))
        assert r.status_code == 200
        data = r.json()
        assert "window_7d" in data
        assert "tinkoff_latency_24h_ms" in data

"""
PR 26 (Phase 2) — TOTP 2FA для admin аккаунтов.

Использует `pyotp` (стандартный TOTP RFC 6238 / Google Authenticator).
Если `pyotp` не установлен, fallback на noop с warning'ом —
2FA не критична для launch, но рекомендуется для admin аккаунтов.

Workflow:
1. Admin → `POST /auth/2fa/enable` → возвращает QR data + secret
2. Admin сканирует QR в Google Authenticator / Authy / любой TOTP app
3. Admin → `POST /auth/2fa/verify {code: '123456'}` → активирует
4. На каждом login (для админов) запрашивается 6-digit код

Secret хранится в БД (User.totp_secret) — это OK по RFC, не secret-key-level.
"""

from __future__ import annotations

import base64
import secrets
from typing import Optional

from logger import get_logger

log = get_logger("totp")

try:
    import pyotp  # type: ignore
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    log.warning("pyotp not installed — 2FA disabled. pip install pyotp")


def generate_secret() -> str:
    """Возвращает новый TOTP secret (base32). 32-byte = 160 bits entropy."""
    if PYOTP_AVAILABLE:
        return pyotp.random_base32()
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def provisioning_uri(secret: str, email: str, issuer: str = "Eqio") -> str:
    """URI для QR-кода: otpauth://totp/Eqio:email?secret=...&issuer=Eqio."""
    if not PYOTP_AVAILABLE:
        return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}"
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_code(secret: Optional[str], code: str) -> bool:
    """Проверить 6-digit TOTP код. Допускается ±1 window (90 секунд)."""
    if not secret or not code:
        return False
    if not PYOTP_AVAILABLE:
        log.error("verify_code called but pyotp not installed")
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    except Exception:
        log.exception("TOTP verify failed")
        return False

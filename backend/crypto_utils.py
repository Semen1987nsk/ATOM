"""
Шифрование / дешифрование секретов (broker-токены и др.)

Используется Fernet (AES-128-CBC + HMAC-SHA256).
Ключ берётся из переменной окружения BROKER_TOKEN_KEY.
В dev-режиме генерируется автоматически (с предупреждением).

Использование:
    from crypto_utils import encrypt_token, decrypt_token

    cipher = encrypt_token("t.xxx...")   # -> base64 строка
    plain  = decrypt_token(cipher)       # -> "t.xxx..."
"""

import os
import warnings
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from logger import get_logger

log = get_logger("crypto")

_FERNET: Fernet | None = None


def _get_fernet() -> Fernet:
    """Ленивая инициализация Fernet-экземпляра (singleton)."""
    global _FERNET
    if _FERNET is not None:
        return _FERNET

    raw_key = os.getenv("BROKER_TOKEN_KEY", "")

    if not raw_key:
        is_debug = os.getenv("DEBUG", "false").lower() == "true"
        if not is_debug:
            raise RuntimeError(
                "\n🚨 FATAL: BROKER_TOKEN_KEY is not set!\n"
                "   Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'\n"
                "   Then set: export BROKER_TOKEN_KEY='your-key'"
            )
        # Dev-режим — детерминированный ключ из SECRET_KEY для стабильности между рестартами
        from config import settings
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        raw_key = base64.urlsafe_b64encode(digest[:32]).decode()
        warnings.warn(
            "\n⚠️  BROKER_TOKEN_KEY not set — deriving from SECRET_KEY (dev only).\n"
            "   Set BROKER_TOKEN_KEY env var for production.",
            UserWarning,
            stacklevel=3,
        )

    # Если ключ не в формате Fernet (44 символа url-safe base64), преобразуем
    try:
        _FERNET = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
    except (ValueError, Exception):
        # Произвольная строка — получаем 32 байта через SHA-256
        digest = hashlib.sha256(raw_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(digest[:32])
        _FERNET = Fernet(fernet_key)

    return _FERNET


def encrypt_token(plaintext: str) -> str:
    """Шифрует строку и возвращает base64-представление."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    """
    Дешифрует строку.  Если ciphertext НЕ является валидным шифротекстом
    (например, при миграции со старых plain-text токенов), возвращает как есть.
    """
    if not ciphertext:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        # Токен хранится в plaintext (до миграции) — возвращаем как есть
        log.warning("decrypt_token: ciphertext is not valid Fernet — returning as-is (legacy plaintext?)")
        return ciphertext

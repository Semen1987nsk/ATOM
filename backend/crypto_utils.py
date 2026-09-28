"""
Шифрование / дешифрование секретов (broker-токены и др.)

Используется Fernet (AES-128-CBC + HMAC-SHA256).

PR 26 — key versioning через prefix `v1:`, `v2:` и т.д.:
- Активный ключ берётся из `BROKER_TOKEN_KEY` (legacy, без префикса) ИЛИ
  `BROKER_TOKEN_KEY_V2` (новый формат).
- Старые ключи остаются в `BROKER_TOKEN_KEY_V1`, `BROKER_TOKEN_KEY_V0` и т.д. —
  они НЕ шифруют новое, но дешифруют старое.
- При расшифровке смотрим на префикс ciphertext'а: `v2:xxxxx` → V2 ключ,
  `v1:xxxxx` → V1, без префикса → legacy `BROKER_TOKEN_KEY`.
- При шифровании ставим префикс активного ключа.

Это решает классическую проблему ротации: если просто заменить ключ,
все stored токены становятся unreadable. С версионированием мы можем
ротировать ключ → постепенно перешифровать токены (background job) →
удалить старый ключ.

Использование:
    cipher = encrypt_token("t.xxx...")   # -> "v2:gAAAAA..."
    plain  = decrypt_token(cipher)       # -> "t.xxx..."
"""

import os
import warnings
import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from logger import get_logger

log = get_logger("crypto")

# Сейчас активная версия. При ротации меняем на v3 и т.д.
_ACTIVE_VERSION = "v2"

# Map version -> Fernet instance. Заполняется лениво в _ensure_keys_loaded.
_FERNETS: dict[str, Fernet] = {}
_LEGACY_FERNET: Optional[Fernet] = None  # для ciphertext без префикса


def _normalize_to_fernet_key(raw_key: str) -> bytes:
    """Произвольная строка → 32-byte Fernet key."""
    try:
        # Если уже валидный 44-символьный Fernet key.
        Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
        return raw_key.encode() if isinstance(raw_key, str) else raw_key
    except (ValueError, Exception):
        digest = hashlib.sha256(raw_key.encode()).digest()
        return base64.urlsafe_b64encode(digest[:32])


def _ensure_keys_loaded() -> None:
    """Загружаем все доступные ключи (активный + старые версии) один раз."""
    global _LEGACY_FERNET

    if _FERNETS:
        return  # уже загружены

    # 1. Сканируем env: BROKER_TOKEN_KEY_V0, BROKER_TOKEN_KEY_V1, V2, ...
    for v_num in range(0, 10):
        env_name = f"BROKER_TOKEN_KEY_V{v_num}"
        raw = os.getenv(env_name, "")
        if raw:
            key_bytes = _normalize_to_fernet_key(raw)
            _FERNETS[f"v{v_num}"] = Fernet(key_bytes)
            log.info("loaded key version v%d from %s", v_num, env_name)

    # 2. Legacy: BROKER_TOKEN_KEY без префикса — для ciphertext без `vN:`.
    legacy_raw = os.getenv("BROKER_TOKEN_KEY", "")
    if legacy_raw:
        key_bytes = _normalize_to_fernet_key(legacy_raw)
        _LEGACY_FERNET = Fernet(key_bytes)
        # И заодно добавляем как _ACTIVE_VERSION если активный явно не задан.
        if _ACTIVE_VERSION not in _FERNETS:
            _FERNETS[_ACTIVE_VERSION] = _LEGACY_FERNET

    # 3. Dev fallback — генерим из SECRET_KEY если ничего не задано.
    if not _FERNETS and not _LEGACY_FERNET:
        is_debug = os.getenv("DEBUG", "false").lower() == "true"
        if not is_debug:
            raise RuntimeError(
                "\n🚨 FATAL: BROKER_TOKEN_KEY (or BROKER_TOKEN_KEY_V2) is not set!\n"
                "   Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'\n"
                "   Then set: export BROKER_TOKEN_KEY_V2='your-key'"
            )
        from config import settings
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        derived = base64.urlsafe_b64encode(digest[:32])
        _FERNETS[_ACTIVE_VERSION] = Fernet(derived)
        _LEGACY_FERNET = _FERNETS[_ACTIVE_VERSION]
        warnings.warn(
            "\n⚠️  BROKER_TOKEN_KEY not set — deriving from SECRET_KEY (dev only).\n"
            "   Set BROKER_TOKEN_KEY_V2 env var for production.",
            UserWarning,
            stacklevel=3,
        )


def _get_active_fernet() -> Fernet:
    _ensure_keys_loaded()
    if _ACTIVE_VERSION in _FERNETS:
        return _FERNETS[_ACTIVE_VERSION]
    # Иначе используем самый высокий по номеру.
    if _FERNETS:
        latest = sorted(_FERNETS.keys())[-1]
        return _FERNETS[latest]
    if _LEGACY_FERNET is not None:
        return _LEGACY_FERNET
    raise RuntimeError("no encryption keys configured")


def encrypt_token(plaintext: str) -> str:
    """Шифрует строку и возвращает `vN:base64` строку."""
    if not plaintext:
        return ""
    f = _get_active_fernet()
    ciphertext = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_ACTIVE_VERSION}:{ciphertext}"


class TokenDecryptionError(Exception):
    """Raised when a stored broker token cannot be decrypted."""


def decrypt_token(ciphertext: str) -> str:
    """
    Дешифрует токен с учётом версии ключа.

    Формат:
    - `v2:base64...` → используем V2 ключ
    - `v1:base64...` → используем V1 ключ (legacy decryption)
    - `base64...` (без префикса) → legacy `BROKER_TOKEN_KEY`

    Поднимает TokenDecryptionError если ни один из ключей не подошёл.
    """
    if not ciphertext:
        return ""
    _ensure_keys_loaded()

    # Парсим префикс версии.
    version = None
    payload = ciphertext
    if ":" in ciphertext:
        prefix, _, rest = ciphertext.partition(":")
        if prefix.startswith("v") and prefix[1:].isdigit():
            version = prefix
            payload = rest

    candidates: list[Fernet] = []
    if version and version in _FERNETS:
        candidates.append(_FERNETS[version])
    elif version is None:
        if _LEGACY_FERNET is not None:
            candidates.append(_LEGACY_FERNET)
        # Также попробуем все известные ключи — на случай если legacy токен
        # был зашифрован одним из них (миграция).
        candidates.extend(_FERNETS.values())
    else:
        # Версия в префиксе, но ключа нет → пробуем все, ошибка иначе.
        candidates.extend(_FERNETS.values())

    last_exc: Optional[Exception] = None
    for f in candidates:
        try:
            return f.decrypt(payload.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            continue

    log.error(
        "decrypt_token: failed across %d candidate key(s); version_prefix=%s",
        len(candidates),
        version,
    )
    raise TokenDecryptionError("broker token unreadable") from last_exc

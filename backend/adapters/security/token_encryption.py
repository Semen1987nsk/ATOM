"""
Шифрование брокерских токенов AES-256-GCM с поддержкой ротации мастер-ключа.

Почему AESGCM, не Fernet:

* AESGCM — стандартный AEAD, тот же что в TLS 1.3, лучше анализирован.
* Fernet (cryptography.fernet) использует AES-128-CBC + HMAC-SHA256 — это
  старый формат, нет AEAD, ключ 128 бит. Для финансового SaaS в 2026 —
  слишком слабо.
* Прозрачный формат: `key_id (1B) || nonce (12B) || ciphertext_with_tag`,
  в base64 → 24..30 символов overhead на любой длине токена.

Формат шифротекста:

```
base64(
    key_id   (1 byte)   ← какой мастер-ключ использовали
  | nonce    (12 bytes) ← AES-GCM nonce, random per-message
  | cipher   (varies)   ← зашифрованный токен
  | tag      (16 bytes) ← GCM auth tag (встроен в cipher через AESGCM)
)
```

Ротация мастер-ключа (production-сценарий):

1. Деплой: добавляем новый ключ как `MASTER_KEY_2_B64`, оставляем
   `MASTER_KEY_B64` (он же key_id=1) на месте.
2. `MASTER_KEY_ID=2` — все новые шифровки используют ключ 2.
3. Старые записи (key_id=1 в начале шифротекста) расшифровываются по
   ключу 1, потому что `active_keys[1]` всё ещё в памяти.
4. Через retention period (типично 90 дней) — миграция: расшифровать
   все записи с key_id=1, перешифровать с key_id=2. Тогда ключ 1
   можно удалить из env.

Источник: https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM
"""

from __future__ import annotations

import base64
import os
import secrets
import warnings
from dataclasses import dataclass
from typing import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings
from logger import get_logger

log = get_logger("token_encryption")


# AES-256 требует 32-байтовый ключ.
_KEY_LENGTH_BYTES = 32
# AES-GCM рекомендует nonce 96 бит (12 байт) — оптимум для перфоманса +
# безопасности (см. NIST SP 800-38D §8.2.1).
_NONCE_LENGTH_BYTES = 12
# `key_id` хранится первым байтом → max 255 ключей одновременно.
# Этого с запасом хватит на годы (один key_id на год = 255 лет).
_MAX_KEY_ID = 255


class TokenEncryptionError(Exception):
    """Любая проблема с шифрованием/расшифровкой токенов."""


class _MasterKeyMissing(TokenEncryptionError):
    """В env нет `MASTER_KEY_B64` (или ни одного MASTER_KEY_<N>_B64)."""


@dataclass(frozen=True)
class _LoadedKey:
    key_id: int
    raw: bytes


class TokenEncryptionService:
    """
    Сервис шифрования с памятью о всех активных мастер-ключах.

    В обычной работе достаточно одного `MASTER_KEY_B64` (key_id=1). Если
    в env заданы `MASTER_KEY_2_B64`, `MASTER_KEY_3_B64`, ... — они тоже
    загружаются и могут использоваться для расшифровки старых записей.

    Текущий ключ для шифрования — `MASTER_KEY_ID` (целое число, default 1).
    """

    def __init__(
        self,
        *,
        active_keys: Mapping[int, bytes] | None = None,
        current_key_id: int | None = None,
    ) -> None:
        if active_keys is not None:
            keys = {int(k): v for k, v in active_keys.items()}
        else:
            keys = self._load_keys_from_env()

        if not keys:
            self._fail_no_keys()

        self._validate_keys(keys)
        self._keys: dict[int, bytes] = keys
        self._current_key_id = self._resolve_current_id(current_key_id)
        # AESGCM-объекты иммутабельны и thread-safe — переиспользуем.
        self._aesgcm: dict[int, AESGCM] = {kid: AESGCM(k) for kid, k in keys.items()}

    # ── public API ─────────────────────────────────────────────────────

    @property
    def current_key_id(self) -> int:
        return self._current_key_id

    @property
    def active_key_ids(self) -> list[int]:
        return sorted(self._keys.keys())

    def encrypt(self, plaintext: str) -> str:
        """
        Возвращает шифротекст в base64. Использует текущий мастер-ключ.

        Пустая строка не шифруется — поднимаем ошибку, чтобы случайный
        пустой токен (баг в коде вызова) не превратился в валидный
        шифр-текст с пустым plaintext.
        """
        if not plaintext:
            raise TokenEncryptionError("cannot encrypt empty string")

        key_id = self._current_key_id
        aesgcm = self._aesgcm[key_id]
        nonce = secrets.token_bytes(_NONCE_LENGTH_BYTES)
        cipher_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # key_id занимает 1 байт. Проверяем что влезает.
        if not (1 <= key_id <= _MAX_KEY_ID):
            raise TokenEncryptionError(f"invalid key_id {key_id}")
        envelope = bytes([key_id]) + nonce + cipher_with_tag
        return base64.urlsafe_b64encode(envelope).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Расшифровывает токен. Подбирает ключ по `key_id` из envelope."""
        if not ciphertext_b64:
            raise TokenEncryptionError("cannot decrypt empty string")

        try:
            envelope = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
        except Exception as exc:
            raise TokenEncryptionError(f"malformed base64: {exc}") from exc

        if len(envelope) < 1 + _NONCE_LENGTH_BYTES + 16:
            # 1 (key_id) + 12 (nonce) + 16 (GCM tag) = 29 — минимальная длина.
            raise TokenEncryptionError("envelope too short")

        key_id = envelope[0]
        nonce = envelope[1 : 1 + _NONCE_LENGTH_BYTES]
        cipher_with_tag = envelope[1 + _NONCE_LENGTH_BYTES :]

        aesgcm = self._aesgcm.get(key_id)
        if aesgcm is None:
            raise TokenEncryptionError(
                f"unknown key_id={key_id}; active keys: {self.active_key_ids}"
            )
        try:
            plaintext = aesgcm.decrypt(nonce, cipher_with_tag, None)
        except Exception as exc:
            # InvalidTag, etc. — гасим до domain-уровня.
            raise TokenEncryptionError("decryption failed (tag mismatch or corrupted)") from exc

        return plaintext.decode("utf-8")

    def key_id_of(self, ciphertext_b64: str) -> int:
        """Достать key_id из envelope без расшифровки. Удобно для миграции."""
        envelope = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
        return envelope[0]

    # ── env loading & validation ───────────────────────────────────────

    @staticmethod
    def _load_keys_from_env() -> dict[int, bytes]:
        """
        Загружает мастер-ключи из переменных окружения / config.settings:

        * `MASTER_KEY_B64` → key_id=1 (по умолчанию).
        * `MASTER_KEY_<N>_B64` → key_id=N (для ротации).
        """
        keys: dict[int, bytes] = {}

        primary_b64 = (settings.MASTER_KEY_B64 or "").strip()
        if primary_b64:
            keys[1] = TokenEncryptionService._decode_b64_key(primary_b64, key_id=1)

        # Ищем дополнительные MASTER_KEY_<N>_B64 в env.
        for env_name, env_value in os.environ.items():
            if not env_name.startswith("MASTER_KEY_") or not env_name.endswith("_B64"):
                continue
            if env_name == "MASTER_KEY_B64":
                continue  # уже обработан выше
            mid = env_name[len("MASTER_KEY_") : -len("_B64")]
            if not mid.isdigit():
                continue
            kid = int(mid)
            if kid <= 0 or kid > _MAX_KEY_ID:
                warnings.warn(
                    f"Ignoring {env_name}: key_id={kid} вне диапазона [1, {_MAX_KEY_ID}]",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            if not env_value.strip():
                continue
            keys[kid] = TokenEncryptionService._decode_b64_key(env_value, key_id=kid)
        return keys

    @staticmethod
    def _decode_b64_key(value: str, *, key_id: int) -> bytes:
        try:
            raw = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise TokenEncryptionError(
                f"MASTER_KEY (key_id={key_id}) is not valid base64: {exc}"
            ) from exc
        if len(raw) != _KEY_LENGTH_BYTES:
            raise TokenEncryptionError(
                f"MASTER_KEY (key_id={key_id}) must decode to exactly "
                f"{_KEY_LENGTH_BYTES} bytes (got {len(raw)})"
            )
        return raw

    @staticmethod
    def _validate_keys(keys: dict[int, bytes]) -> None:
        for kid, raw in keys.items():
            if not (1 <= kid <= _MAX_KEY_ID):
                raise TokenEncryptionError(f"invalid key_id {kid}")
            if len(raw) != _KEY_LENGTH_BYTES:
                raise TokenEncryptionError(
                    f"key {kid}: {_KEY_LENGTH_BYTES} bytes required"
                )

    def _resolve_current_id(self, explicit: int | None) -> int:
        candidate = explicit if explicit is not None else settings.MASTER_KEY_ID
        if candidate not in self._keys:
            raise TokenEncryptionError(
                f"current key_id={candidate} not in active_keys "
                f"({sorted(self._keys)}). Set MASTER_KEY_<N>_B64 or "
                f"MASTER_KEY_ID."
            )
        return candidate

    @staticmethod
    def _fail_no_keys() -> None:
        is_debug = os.getenv("DEBUG", "false").lower() == "true"
        if not is_debug:
            raise _MasterKeyMissing(
                "MASTER_KEY_B64 не задан. Сгенерируй ключ:\n"
                "  python -c \"import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\"\n"
                "Затем добавь в env как MASTER_KEY_B64=<...>."
            )
        # В DEBUG-режиме разрешаем работу с генерируемым ephemeral-ключом,
        # но громко предупреждаем. Этот ключ живёт только в одном процессе:
        # перезапуск процесса → невозможно расшифровать ранее сохранённые
        # токены. Это лучше чем падать в локальном dev.
        raise _MasterKeyMissing(
            "MASTER_KEY_B64 не задан. Для dev-режима можно сгенерировать "
            "временный ключ через `TokenEncryptionService.with_ephemeral_dev_key()`."
        )

    # ── factory для dev ────────────────────────────────────────────────

    @classmethod
    def with_ephemeral_dev_key(cls) -> "TokenEncryptionService":
        """
        Создать сервис с одноразовым случайным ключом для тестов / dev.

        НИКОГДА не использовать в production: ключ генерируется при каждом
        создании, после перезапуска процесса нельзя расшифровать ранее
        сохранённые токены.
        """
        random_key = secrets.token_bytes(_KEY_LENGTH_BYTES)
        warnings.warn(
            "TokenEncryptionService.with_ephemeral_dev_key() — DEV ONLY. "
            "Ключ живёт только в одном процессе.",
            UserWarning,
            stacklevel=2,
        )
        return cls(active_keys={1: random_key}, current_key_id=1)

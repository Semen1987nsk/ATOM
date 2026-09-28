"""
Unit-тесты `adapters.security.token_encryption`. Проверяем:

* AES-256-GCM round-trip (encrypt → decrypt → совпадает),
* Уникальность nonce (два encrypt одной строки дают разные ciphertext),
* Key rotation: записи, зашифрованные старым key_id, расшифровываются
  если ключ всё ещё в active_keys,
* Невалидный ciphertext / tag mismatch → TokenEncryptionError,
* Пустые входы отвергаются.
"""

from __future__ import annotations

import base64
import secrets

import pytest

from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)


def _random_key() -> bytes:
    return secrets.token_bytes(32)


def _b64key() -> str:
    return base64.b64encode(_random_key()).decode("ascii")


class TestEncryptDecryptRoundtrip:
    def test_short_token(self) -> None:
        svc = TokenEncryptionService(
            active_keys={1: _random_key()}, current_key_id=1
        )
        ct = svc.encrypt("t.short")
        assert ct != "t.short"
        assert svc.decrypt(ct) == "t.short"

    def test_realistic_tinkoff_token(self) -> None:
        """Длина настоящего Tinkoff токена ~88 символов."""
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        token = "t." + "A" * 86
        assert svc.decrypt(svc.encrypt(token)) == token

    def test_unicode_safe(self) -> None:
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        plaintext = "т.токен_с_русскими_символами"
        assert svc.decrypt(svc.encrypt(plaintext)) == plaintext

    def test_two_encryptions_differ(self) -> None:
        """Random nonce → одинаковый plaintext даёт разный ciphertext."""
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        c1 = svc.encrypt("t.same")
        c2 = svc.encrypt("t.same")
        assert c1 != c2
        assert svc.decrypt(c1) == svc.decrypt(c2) == "t.same"


class TestKeyRotation:
    def test_decrypt_with_old_key_after_rotation(self) -> None:
        """Сценарий ротации: shifrovшifrовали при key_id=1, потом current=2."""
        key1 = _random_key()
        key2 = _random_key()

        # Шифруем с key_id=1.
        svc_v1 = TokenEncryptionService(active_keys={1: key1}, current_key_id=1)
        ciphertext_v1 = svc_v1.encrypt("t.old_token")

        # Через месяц: новый ключ key_id=2, старый всё ещё в active_keys.
        svc_v2 = TokenEncryptionService(
            active_keys={1: key1, 2: key2}, current_key_id=2
        )
        # Новые записи идут под key_id=2.
        ciphertext_v2 = svc_v2.encrypt("t.new_token")
        assert svc_v2.key_id_of(ciphertext_v2) == 2

        # Старая запись всё ещё расшифровывается.
        assert svc_v2.decrypt(ciphertext_v1) == "t.old_token"
        assert svc_v2.decrypt(ciphertext_v2) == "t.new_token"

    def test_decrypt_fails_if_old_key_removed(self) -> None:
        key1 = _random_key()
        key2 = _random_key()
        svc_v1 = TokenEncryptionService(active_keys={1: key1}, current_key_id=1)
        ciphertext = svc_v1.encrypt("t.lost")

        # Старый ключ удалён, остался только новый.
        svc_v2 = TokenEncryptionService(active_keys={2: key2}, current_key_id=2)
        with pytest.raises(TokenEncryptionError, match="unknown key_id"):
            svc_v2.decrypt(ciphertext)

    def test_current_key_must_be_in_active(self) -> None:
        with pytest.raises(TokenEncryptionError, match="not in active_keys"):
            TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=99)

    def test_key_must_be_32_bytes(self) -> None:
        with pytest.raises(TokenEncryptionError, match="bytes required"):
            TokenEncryptionService(active_keys={1: b"too_short"}, current_key_id=1)


class TestTamperResistance:
    def test_corrupted_ciphertext_rejected(self) -> None:
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        ct = svc.encrypt("t.original")
        # Подделываем последний символ (часть GCM tag).
        tampered = ct[:-2] + ("A" if ct[-2] != "A" else "B") + ct[-1]
        with pytest.raises(TokenEncryptionError):
            svc.decrypt(tampered)

    def test_malformed_base64_rejected(self) -> None:
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        with pytest.raises(TokenEncryptionError, match="malformed base64"):
            svc.decrypt("not!!base64!!")

    def test_too_short_envelope_rejected(self) -> None:
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        with pytest.raises(TokenEncryptionError, match="envelope too short"):
            svc.decrypt(base64.urlsafe_b64encode(b"\x01\x02\x03").decode("ascii"))

    def test_empty_plaintext_rejected(self) -> None:
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        with pytest.raises(TokenEncryptionError, match="empty"):
            svc.encrypt("")

    def test_empty_ciphertext_rejected(self) -> None:
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        with pytest.raises(TokenEncryptionError, match="empty"):
            svc.decrypt("")


class TestEphemeralDevKey:
    def test_with_ephemeral_dev_key_works(self) -> None:
        with pytest.warns(UserWarning, match="DEV ONLY"):
            svc = TokenEncryptionService.with_ephemeral_dev_key()
        assert svc.decrypt(svc.encrypt("t.dev")) == "t.dev"

    def test_two_ephemeral_keys_isolate(self) -> None:
        """Каждый with_ephemeral_dev_key создаёт новый ключ — записи не пересекаются."""
        with pytest.warns(UserWarning):
            svc1 = TokenEncryptionService.with_ephemeral_dev_key()
        with pytest.warns(UserWarning):
            svc2 = TokenEncryptionService.with_ephemeral_dev_key()
        ct = svc1.encrypt("t.from_svc1")
        with pytest.raises(TokenEncryptionError):
            svc2.decrypt(ct)


class TestEnvelopeMetadata:
    def test_key_id_recoverable_without_decryption(self) -> None:
        """`key_id_of()` нужен для миграции токенов между ключами."""
        svc = TokenEncryptionService(active_keys={1: _random_key()}, current_key_id=1)
        ct = svc.encrypt("t.something")
        assert svc.key_id_of(ct) == 1

    def test_active_key_ids_sorted(self) -> None:
        svc = TokenEncryptionService(
            active_keys={3: _random_key(), 1: _random_key(), 2: _random_key()},
            current_key_id=3,
        )
        assert svc.active_key_ids == [1, 2, 3]

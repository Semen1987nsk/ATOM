"""MASTER_KEY_B64 (AES-256-GCM мастер-ключ брокерских токенов):
в проде (DEBUG=false) ОБЯЗАТЕЛЕН, иначе токены лягут нешифрованными."""
from __future__ import annotations

import pytest


def test_raises_in_prod_when_missing(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("MASTER_KEY_B64", raising=False)
    from config import _resolve_master_key_b64
    with pytest.raises(RuntimeError):
        _resolve_master_key_b64()


def test_empty_ok_in_debug(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("MASTER_KEY_B64", raising=False)
    from config import _resolve_master_key_b64
    assert _resolve_master_key_b64() == ""


def test_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("MASTER_KEY_B64", "c29tZS1iYXNlNjQta2V5")
    from config import _resolve_master_key_b64
    assert _resolve_master_key_b64() == "c29tZS1iYXNlNjQta2V5"

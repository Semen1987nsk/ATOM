"""
Unit-тесты PR 16 observability:

* `_before_send` маскирует Tinkoff-токены в exception messages, breadcrumbs.
* `bind_sync_context` / `clear_sync_context` корректно работают с asyncio.
* `SyncContextFilter` проставляет поля в LogRecord.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from adapters.observability.sync_context import (
    SyncContextFilter,
    bind_sync_context,
    clear_sync_context,
    current_sync_context,
)
from observability import _before_send


# ── Sentry before_send / token masking ──────────────────────────────


def test_before_send_redacts_password_in_request_data() -> None:
    event = {
        "request": {
            "data": {"password": "secret123", "username": "alice"},
        }
    }
    out = _before_send(event, hint={})
    assert out["request"]["data"]["password"] == "***"
    assert out["request"]["data"]["username"] == "alice"


def test_before_send_redacts_authorization_header() -> None:
    event = {
        "request": {
            "headers": {"Authorization": "Bearer t.realtoken", "X-Other": "fine"},
        }
    }
    out = _before_send(event, hint={})
    assert out["request"]["headers"]["Authorization"] == "***"
    assert out["request"]["headers"]["X-Other"] == "fine"


def test_before_send_masks_token_in_exception_value() -> None:
    """Tinkoff token (t.XXXX...) в exception message → t.****MASKED****."""
    event = {
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "Failed with token t.FeABCDEFGHIJKLMNOPQRSTUV1234vZBA on call",
                }
            ]
        }
    }
    out = _before_send(event, hint={})
    val = out["exception"]["values"][0]["value"]
    assert "t.FeABCDEFGHIJKLMNOPQRSTUV1234vZBA" not in val
    assert "t.****MASKED****" in val


def test_before_send_masks_token_in_breadcrumbs() -> None:
    event = {
        "breadcrumbs": {
            "values": [
                {"message": "using t.ABCDEFGHIJKLMNOPQRSTUVWXYZ123 now"},
                {"data": {"some_key": "called with t.SECRETTOKEN1234567890ABCDE"}},
            ]
        }
    }
    out = _before_send(event, hint={})
    bcs = out["breadcrumbs"]["values"]
    assert "t.ABCDEFGHIJKLMNOPQRSTUVWXYZ123" not in bcs[0]["message"]
    assert "t.****MASKED****" in bcs[0]["message"]
    assert "t.SECRETTOKEN1234567890ABCDE" not in bcs[1]["data"]["some_key"]


def test_before_send_does_not_mask_short_t_dot_strings() -> None:
    """`t.is_active` — НЕ должен заменяться (это field name, не токен)."""
    event = {"exception": {"values": [{"value": "AttributeError: t.is_active"}]}}
    out = _before_send(event, hint={})
    assert "t.is_active" in out["exception"]["values"][0]["value"]


def test_before_send_redacts_master_key() -> None:
    event = {"request": {"data": {"MASTER_KEY_B64": "AABBCC=="}}}
    out = _before_send(event, hint={})
    assert out["request"]["data"]["MASTER_KEY_B64"] == "***"


# ── sync_context ─────────────────────────────────────────────────────


def test_bind_and_clear_sync_context() -> None:
    """Базовый round-trip bind/clear."""
    tokens = bind_sync_context(
        sync_id="sync-abc",
        account_id=42,
        broker_account_id="2135909232",
    )
    ctx = current_sync_context()
    assert ctx["sync_id"] == "sync-abc"
    assert ctx["broker_account_id"] == "2135909232"
    # account_id хешируется → 12 hex символов.
    assert len(ctx["account_hash"]) == 12
    assert ctx["account_hash"] != "42"

    clear_sync_context(tokens)
    ctx_after = current_sync_context()
    assert ctx_after == {
        "sync_id": None,
        "account_hash": None,
        "broker_account_id": None,
    }


def test_sync_context_isolated_per_task() -> None:
    """Два параллельных async-таска не пересекаются по contextvars."""

    async def task_a() -> dict:
        tokens = bind_sync_context(
            sync_id="A", account_id=1, broker_account_id="acc-a"
        )
        try:
            await asyncio.sleep(0.01)
            return current_sync_context()
        finally:
            clear_sync_context(tokens)

    async def task_b() -> dict:
        tokens = bind_sync_context(
            sync_id="B", account_id=2, broker_account_id="acc-b"
        )
        try:
            await asyncio.sleep(0.01)
            return current_sync_context()
        finally:
            clear_sync_context(tokens)

    async def run() -> tuple[dict, dict]:
        a, b = await asyncio.gather(task_a(), task_b())
        return a, b

    a, b = asyncio.run(run())
    assert a["sync_id"] == "A"
    assert b["sync_id"] == "B"
    assert a["broker_account_id"] == "acc-a"
    assert b["broker_account_id"] == "acc-b"


def test_account_id_is_hashed_not_plain() -> None:
    """user_id / account_id не должен утечь в логи как есть."""
    tokens = bind_sync_context(
        sync_id="s",
        account_id=12345,
        broker_account_id="brk",
    )
    try:
        ctx = current_sync_context()
        # Hash 12 hex chars; raw "12345" не должен совпасть.
        assert ctx["account_hash"] != "12345"
        # SHA-256 detected: только [0-9a-f].
        assert all(c in "0123456789abcdef" for c in ctx["account_hash"])
    finally:
        clear_sync_context(tokens)


def test_sync_context_filter_adds_fields_to_log_record() -> None:
    """SyncContextFilter добавляет поля в LogRecord."""
    flt = SyncContextFilter()

    tokens = bind_sync_context(
        sync_id="ctx-1", account_id=99, broker_account_id="brk-1"
    )
    try:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hi", args=(), exc_info=None,
        )
        flt.filter(record)
        assert getattr(record, "sync_id") == "ctx-1"
        assert getattr(record, "broker_account_id") == "brk-1"
        assert getattr(record, "account_hash") != "-"
    finally:
        clear_sync_context(tokens)

    # После clear — поля становятся "-".
    record2 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hi", args=(), exc_info=None,
    )
    flt.filter(record2)
    assert getattr(record2, "sync_id") == "-"
    assert getattr(record2, "broker_account_id") == "-"

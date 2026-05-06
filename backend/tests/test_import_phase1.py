"""
Тесты под фиксы Phase 1 в import_service:
- TZ-aware парсинг дат (МСК → UTC; date(utc) колонка → UTC напрямую).
- currency берётся из CSV-колонки если есть, иначе НЕ подменяется «RUB» вслепую.
"""
from __future__ import annotations

import io
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import import_service  # noqa: E402


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ──────────────────────────────────────────────
#  TZ-aware datetimes
# ──────────────────────────────────────────────


def test_normalize_msk_to_utc():
    """Naive datetime интерпретируется как МСК и переводится в UTC."""
    dt = datetime(2026, 5, 4, 12, 30, 0)  # 12:30 МСК
    result = import_service._normalize_to_utc_naive(dt)
    assert result == datetime(2026, 5, 4, 9, 30, 0)  # 09:30 UTC
    assert result.tzinfo is None  # храним naive UTC для совместимости с БД


def test_normalize_explicit_utc_when_column_named_utc():
    """Колонка date(utc) → не сдвигаем на МСК, считаем UTC."""
    dt = datetime(2026, 5, 4, 12, 30, 0)
    result = import_service._normalize_to_utc_naive(dt, assume_tz=timezone.utc)
    assert result == datetime(2026, 5, 4, 12, 30, 0)


def test_normalize_aware_datetime_converted_to_utc():
    tz_plus_5 = timezone.utc.utcoffset(None)
    dt = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone(__import__("datetime").timedelta(hours=5)))
    result = import_service._normalize_to_utc_naive(dt)
    # 14:00 в +5 = 09:00 UTC
    assert result == datetime(2026, 5, 4, 9, 0, 0)


def test_normalize_invalid_returns_none():
    assert import_service._normalize_to_utc_naive(None) is None
    assert import_service._normalize_to_utc_naive("nonsense not a date 13/13/2026") is None


def test_csv_import_msk_dates_converted_to_utc():
    """Полный путь: CSV с naive датами → UTC-naive в выходе."""
    df = pd.DataFrame({
        "date": ["2026-05-04 12:30:00", "2026-05-04 13:00:00"],
        "symbol": ["SBER", "GAZP"],
        "side": ["buy", "buy"],
        "price": [300.5, 150.0],
        "quantity": [10, 20],
    })
    trades = import_service.parse_trade_file(_csv_bytes(df), "report.csv")
    assert len(trades) == 2
    # 12:30 МСК → 09:30 UTC
    entry_at = trades[0]["entry_at"]
    assert entry_at.hour == 9 and entry_at.minute == 30
    assert entry_at.tzinfo is None  # UTC-naive


def test_csv_import_utc_column_not_shifted():
    """Колонка date(utc) → дата уже в UTC, сдвигать на 3 часа нельзя."""
    df = pd.DataFrame({
        "date(utc)": ["2026-05-04 12:30:00"],
        "symbol": ["BTCUSDT"],
        "side": ["buy"],
        "price": [50000],
        "quantity": [0.1],
    })
    trades = import_service.parse_trade_file(_csv_bytes(df), "binance.csv")
    assert len(trades) == 1
    entry_at = trades[0]["entry_at"]
    # Должно остаться 12:30, а не 09:30
    assert entry_at.hour == 12 and entry_at.minute == 30


# ──────────────────────────────────────────────
#  currency без молчаливого RUB
# ──────────────────────────────────────────────


def test_csv_import_currency_from_column():
    """CSV с колонкой currency → значение должно попасть в trade['currency']."""
    df = pd.DataFrame({
        "date": ["2026-05-04 12:30:00"],
        "symbol": ["AAPL"],
        "side": ["buy"],
        "price": [200],
        "quantity": [10],
        "currency": ["USD"],
    })
    trades = import_service.parse_trade_file(_csv_bytes(df), "report.csv")
    assert trades[0]["currency"] == "USD"


def test_csv_import_no_currency_column_no_silent_rub():
    """Без колонки currency — поле либо отсутствует, либо None.
    КЛЮЧЕВОЕ: НЕ подменяется автоматически на 'RUB' (источник багов с USD-сделками).
    """
    df = pd.DataFrame({
        "date": ["2026-05-04 12:30:00"],
        "symbol": ["AAPL"],
        "side": ["buy"],
        "price": [200],
        "quantity": [10],
    })
    trades = import_service.parse_trade_file(_csv_bytes(df), "report.csv")
    cur = trades[0].get("currency")
    assert cur is None or cur == "", (
        f"currency не должен молча подменяться 'RUB', а у нас: {cur!r}"
    )

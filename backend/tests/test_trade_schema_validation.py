"""S3-17: TradeBase/TradeUpdate отвергают неположительные price/quantity."""
from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schemas  # noqa: E402


def _valid_payload(**over):
    p = {
        "symbol": "SBER",
        "direction": "long",
        "entry_price": 300.0,
        "quantity": 10.0,
        "entry_at": "2026-01-01T10:00:00",
    }
    p.update(over)
    return p


def test_negative_price_rejected():
    with pytest.raises(ValidationError):
        schemas.TradeBase(**_valid_payload(entry_price=-100.0))


def test_zero_quantity_rejected():
    with pytest.raises(ValidationError):
        schemas.TradeBase(**_valid_payload(quantity=0.0))


def test_valid_payload_accepted():
    t = schemas.TradeBase(**_valid_payload())
    assert t.entry_price == 300.0


def test_update_negative_price_rejected():
    with pytest.raises(ValidationError):
        schemas.TradeUpdate(entry_price=-5.0)

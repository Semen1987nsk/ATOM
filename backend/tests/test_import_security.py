"""SEC-07: Excel magic-byte validation + row-cap (zip-bomb / DoS guard)."""
import io

import pandas as pd
import pytest

import config
import import_service


def test_rejects_non_xlsx_magic():
    fake = b"<html>not xlsx</html>" + b"\x00" * 100
    with pytest.raises(ValueError):
        import_service.parse_trade_file(fake, "evil.xlsx")


def test_rejects_non_xls_magic():
    fake = b"definitely not an OLE2 file" + b"\x00" * 100
    with pytest.raises(ValueError):
        import_service.parse_trade_file(fake, "evil.xls")


def test_valid_xlsx_passes_magic(monkeypatch):
    df = pd.DataFrame({
        "date": ["2025-01-01 10:00:00"],
        "symbol": ["SBER"],
        "side": ["buy"],
        "price": [100.0],
        "quantity": [1.0],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    trades = import_service.parse_trade_file(buf.read(), "good.xlsx")
    assert isinstance(trades, list)


def test_row_cap_enforced(monkeypatch):
    monkeypatch.setattr(config.settings, "MAX_IMPORT_ROWS", 5)
    df = pd.DataFrame({
        "symbol": ["X"] * 50,
        "side": ["buy"] * 50,
        "price": [1] * 50,
        "quantity": [1] * 50,
        "date": ["2025-01-01"] * 50,
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    with pytest.raises(ValueError):
        import_service.parse_trade_file(buf.read(), "big.xlsx")

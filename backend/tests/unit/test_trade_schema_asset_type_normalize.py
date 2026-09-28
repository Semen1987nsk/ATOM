"""
BUG-005 regression: Trade response должен заполнять asset_type из
instrument_type_v2, если поле NULL в БД (брокерский импорт).

Без нормализации EditTradeModal на фронте показывает 'Stock' для фьючерса
(fallback в buildInitialFormData), и при save без касания select PATCH
перепишет real type в БД.
"""

from __future__ import annotations

from datetime import datetime

import schemas


def _make_trade(**overrides):
    base = dict(
        id=1,
        account_id=1,
        symbol="TEST",
        direction="long",
        entry_price=100.0,
        quantity=10.0,
        entry_at=datetime(2026, 1, 1, 10, 0),
        currency="rub",
    )
    base.update(overrides)
    return schemas.Trade(**base)


class TestAssetTypeNormalization:
    """asset_type fallback на instrument_type_v2 при NULL."""

    def test_futures_null_asset_type_resolves_from_v2(self) -> None:
        t = _make_trade(asset_type=None, instrument_type_v2="futures")
        assert t.asset_type == "Futures"

    def test_share_null_asset_type_resolves_to_stock(self) -> None:
        t = _make_trade(asset_type=None, instrument_type_v2="share")
        assert t.asset_type == "Stock"

    def test_bond_null_asset_type_resolves_to_bond(self) -> None:
        t = _make_trade(asset_type=None, instrument_type_v2="bond")
        assert t.asset_type == "Bond"

    def test_etf_null_asset_type_resolves_to_etf(self) -> None:
        t = _make_trade(asset_type=None, instrument_type_v2="etf")
        assert t.asset_type == "ETF"

    def test_currency_null_asset_type_resolves_to_currency(self) -> None:
        t = _make_trade(asset_type=None, instrument_type_v2="currency")
        assert t.asset_type == "Currency"

    def test_option_null_asset_type_resolves_to_option(self) -> None:
        t = _make_trade(asset_type=None, instrument_type_v2="option")
        assert t.asset_type == "Option"

    def test_existing_non_tapi_asset_type_not_overwritten(self) -> None:
        """Manual trade имеет custom asset_type — нормализация не должна перезаписать."""
        t = _make_trade(asset_type="Crypto", instrument_type_v2="share")
        assert t.asset_type == "Crypto"

    def test_lowercase_tapi_asset_type_normalized_to_capitalized(self) -> None:
        """В БД broker trades хранятся как 'futures'/'share' — нормализуем для UI."""
        t = _make_trade(asset_type="futures", instrument_type_v2="futures")
        assert t.asset_type == "Futures"

    def test_lowercase_share_normalized_to_stock(self) -> None:
        t = _make_trade(asset_type="share", instrument_type_v2="share")
        assert t.asset_type == "Stock"

    def test_both_null_remains_null(self) -> None:
        """Manual trade без подсказок — оставляем None, frontend сам ставит fallback."""
        t = _make_trade(asset_type=None, instrument_type_v2=None)
        assert t.asset_type is None

    def test_unknown_v2_capitalizes(self) -> None:
        """Неизвестный T-API enum (не из mapping) — capitalize."""
        t = _make_trade(asset_type=None, instrument_type_v2="someweirdtype")
        assert t.asset_type == "Someweirdtype"

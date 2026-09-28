"""MATH-08: profit_left для фьючерсов в mae_mfe.py должен брать pv из
сохранённого Trade.point_value (snapshot на момент закрытия, source =
empirical_payment), а НЕ из cached `pnl_service.get_point_value(symbol)`.

Для индексных фьючерсов (DAX/Brent/foreign) cached pv от Tinkoff metadata
неправильное → ×1000-bias в «потерянная прибыль». Snapshot point_value
сохранён правильно (с empirical fallback'ом). См. models.py:406-412.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from analytics.mae_mfe import analyze_mae_mfe

UTC = timezone.utc


def _trade(
    *,
    point_value=None,
    symbol="FUT-FAKE",
    entry_price=Decimal("100"),
    exit_price=Decimal("105"),
    mfe_price=Decimal("110"),
    mae_price=Decimal("99"),
    qty=Decimal("10"),
    direction_value="long",
    net_pnl=Decimal("50"),
):
    """Минимальный Trade-mock с нужным point_value (или без)."""
    return SimpleNamespace(
        symbol=symbol,
        entry_price=entry_price,
        exit_price=exit_price,
        mfe_price=mfe_price,
        mae_price=mae_price,
        quantity=qty,
        direction=SimpleNamespace(value=direction_value),
        operations=None,
        net_pnl=net_pnl,
        pnl=net_pnl,
        entry_at=datetime(2026, 5, 1, tzinfo=UTC),
        exit_at=datetime(2026, 5, 10, tzinfo=UTC),
        point_value=point_value,
    )


def test_profit_left_uses_stored_point_value_when_present(monkeypatch):
    """MATH-08: при наличии Trade.point_value формула должна брать его, а
    НЕ ходить в pnl_service.get_point_value (cached, может врать)."""
    # Cached pv «врёт» ×1000 (типичный bias для индексных фьючерсов).
    cached_get_pv_calls = []

    def fake_get_pv(symbol):
        cached_get_pv_calls.append(symbol)
        return Decimal("1000")

    monkeypatch.setattr("pnl_service.get_point_value", fake_get_pv)

    # Trade с правильным snapshot pv = 1 (empirical, real для контракта).
    trades = [_trade(point_value=Decimal("1"))]
    result = analyze_mae_mfe(trades)

    # profit_left = (price_diff_max - price_diff_actual) × qty × pv
    # entry=100, mfe=110, exit=105, qty=10, pv=1 (stored)
    # mfe_pct = 10%, actual_pct = 5%
    # price_diff_max = 100 × 0.10 = 10
    # price_diff_actual = 100 × 0.05 = 5
    # max_pnl = 10 × 10 × 1 = 100, actual_pnl = 5 × 10 × 1 = 50
    # left = 50
    profit_left_avg = result.get("avg_profit_left_on_table")
    assert profit_left_avg is not None
    # С stored pv=1 ожидаем ~50. С cached pv=1000 было бы ~50000 (×1000).
    assert profit_left_avg == pytest.approx(50, rel=0.01), (
        f"Expected ~50 (stored pv=1), got {profit_left_avg}. "
        f"Это значит код всё ещё использует cached pv=1000."
    )


def test_profit_left_falls_back_to_cached_when_no_stored_pv(monkeypatch):
    """MATH-08: для legacy трейдов без stored point_value (старые сделки,
    backfill не дошёл) должны использовать cached как fallback."""

    def fake_get_pv(symbol):
        return Decimal("2")

    monkeypatch.setattr("pnl_service.get_point_value", fake_get_pv)

    # Trade БЕЗ stored point_value.
    trades = [_trade(point_value=None)]
    result = analyze_mae_mfe(trades)

    # Cached pv=2 → max_pnl = 10 × 10 × 2 = 200, actual = 5 × 10 × 2 = 100,
    # left = 100.
    profit_left_avg = result.get("avg_profit_left_on_table")
    assert profit_left_avg == pytest.approx(100, rel=0.01), (
        f"Expected ~100 (cached pv=2 fallback), got {profit_left_avg}"
    )


def test_profit_left_falls_back_when_stored_pv_is_zero(monkeypatch):
    """Edge: stored pv = 0 (некорректные данные) — fallback на cached."""

    def fake_get_pv(symbol):
        return Decimal("3")

    monkeypatch.setattr("pnl_service.get_point_value", fake_get_pv)

    trades = [_trade(point_value=Decimal("0"))]
    result = analyze_mae_mfe(trades)
    profit_left_avg = result.get("avg_profit_left_on_table")
    # Cached pv=3 → max_pnl=300, actual=150, left=150
    assert profit_left_avg == pytest.approx(150, rel=0.01)


def test_profit_left_shares_pv_one_remains_consistent(monkeypatch):
    """Для акций stored pv обычно = 1 (или None) — поведение неизменно."""

    def fake_get_pv(symbol):
        return Decimal("1")

    monkeypatch.setattr("pnl_service.get_point_value", fake_get_pv)

    trades = [_trade(point_value=Decimal("1"))]
    result = analyze_mae_mfe(trades)
    profit_left_avg = result.get("avg_profit_left_on_table")
    # pv=1 → left = 50
    assert profit_left_avg == pytest.approx(50, rel=0.01)

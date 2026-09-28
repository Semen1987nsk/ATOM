"""
Регрессионные тесты на Trade.pnl_pct (PR 18).

Гарантия от возврата бага «+678% по фьючерсу»: для фьючерсов цена в пунктах,
а pnl в рублях. Делать pct как pnl / (price × qty) — категорически неверно.
Правильный знаменатель — entry_value (cost-basis в рублях).
"""

from __future__ import annotations

from datetime import datetime

import pytest

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
        exit_price=110.0,
        exit_at=datetime(2026, 1, 2, 10, 0),
        pnl=100.0,
        currency="rub",
    )
    base.update(overrides)
    return schemas.Trade(**base)


class TestPnlPctWithEntryValue:
    """Когда entry_value есть — pnl_pct = pnl / entry_value × 100."""

    def test_shares_uses_entry_value_when_present(self) -> None:
        t = _make_trade(entry_value=1000.0, exit_value=1100.0, pnl=100.0)
        assert t.pnl_pct == pytest.approx(10.0, abs=0.001)

    def test_short_negative_pnl_negative_pct(self) -> None:
        t = _make_trade(
            direction="short",
            entry_value=1000.0,
            exit_value=1050.0,
            pnl=-50.0,
        )
        assert t.pnl_pct == pytest.approx(-5.0, abs=0.001)

    def test_futures_uses_entry_value_not_price_x_qty(self) -> None:
        """
        Главный регрессионный тест: для фьючерса pnl_pct должен
        вычисляться от entry_value (рубли), а не от entry_price (пункты).

        Сценарий из реальных данных по ETH6:
        - quantity = 348 (контракты)
        - entry_price = 16.39 (пункты — НЕ рубли!)
        - pnl = +38687 ₽ (рубли, payment-based)
        - entry_value = 438709 ₽ (cost-basis в рублях)

        Неправильно: pnl / (price × qty) = 38687 / (16.39 × 348) = +678%
        Правильно:   pnl / entry_value   = 38687 / 438709       = +8.82%
        """
        t = _make_trade(
            symbol="ETH6",
            entry_price=16.39,
            quantity=348.0,
            entry_value=438709.64,
            exit_value=477397.0,
            pnl=38687.36,
        )
        assert t.pnl_pct == pytest.approx(8.82, abs=0.05), (
            f"Регрессия! Ожидался +8.82% (от cost-basis в рублях), получили {t.pnl_pct}%. "
            "Скорее всего pnl_pct снова считается через entry_price × qty (баг до PR 18)."
        )
        # Sanity: не превышает 100% — для нормальной фьючерсной сделки.
        assert abs(t.pnl_pct) < 100, "Аномально большой процент → проверь формулу"

    def test_negative_futures_pnl_negative_pct(self) -> None:
        """Из тех же реальных данных: CCJ6 LONG проиграл 9.76%, не 97.55%."""
        t = _make_trade(
            symbol="CCJ6",
            entry_price=281.9,
            quantity=45.0,
            entry_value=126855.0,
            exit_value=114480.0,
            pnl=-12375.0,
        )
        assert t.pnl_pct == pytest.approx(-9.76, abs=0.05)


class TestPnlPctFallback:
    """Когда entry_value=None (legacy/manual сделки) — старая формула."""

    def test_legacy_no_entry_value_uses_price_qty(self) -> None:
        t = _make_trade(
            entry_value=None,
            exit_value=None,
            entry_price=100.0,
            quantity=10.0,
            pnl=100.0,
        )
        # Fallback: 100 / (100 × 10) × 100 = 10%.
        assert t.pnl_pct == pytest.approx(10.0, abs=0.001)

    def test_no_pnl_returns_none(self) -> None:
        t = _make_trade(pnl=None, entry_value=None, exit_value=None)
        assert t.pnl_pct is None

    def test_zero_entry_value_falls_back_to_price_formula(self) -> None:
        t = _make_trade(
            entry_value=0.0,  # edge case, не должно делить на ноль.
            entry_price=100.0,
            quantity=10.0,
            pnl=100.0,
        )
        # Должно сработать fallback: 100 / 1000 × 100 = 10%.
        assert t.pnl_pct == pytest.approx(10.0, abs=0.001)

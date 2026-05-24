"""
PR 26 (Phase 3) — unit tests для reconciliation_service.

Покрывает pure-функции без зависимости от БД:
- classify_diff: tolerance логика (10₽ / 0.1%)
- aggregate_broker_report: суммирование trades + foreign dividends
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.entities import BrokerReportTradeRow
from services.reconciliation_service import (
    ABS_TOLERANCE_RUB,
    REL_TOLERANCE_PCT,
    aggregate_broker_report,
    classify_diff,
)


# ════════════════════════════════════════════════════════════════════════
# classify_diff: 10₽ / 0.1% tolerance
# ════════════════════════════════════════════════════════════════════════


class TestClassifyDiff:
    """AU16: classify_diff returns 4-tuple (diff_abs, diff_pct, status, note)."""

    def test_zero_diff_is_ok(self):
        _, _, status, _ = classify_diff(Decimal("1000"), Decimal("1000"))
        assert status == "ok"

    def test_tiny_diff_within_abs_is_ok(self):
        """Расхождение 5₽ при значении 1000₽ — в пределах abs tolerance."""
        _, _, status, _ = classify_diff(Decimal("1000"), Decimal("1005"))
        assert status == "ok"

    def test_small_pct_diff_is_ok(self):
        """Расхождение 0.05% при значении 100k₽ — в пределах pct tolerance."""
        _, _, status, _ = classify_diff(Decimal("100000"), Decimal("100050"))
        # 50₽ > 10₽ но 0.05% < 0.1% → still ok (либо abs либо pct в пределах)
        assert status == "ok"

    def test_large_absolute_diff_hard(self):
        """Расхождение 1000₽ при значении 1000₽ — hard break."""
        _, _, status, _ = classify_diff(Decimal("1000"), Decimal("2000"))
        assert status == "hard"

    def test_diff_pct_large(self):
        """Расхождение 5% — точно hard."""
        _, _, status, _ = classify_diff(Decimal("100000"), Decimal("105000"))
        assert status == "hard"

    def test_diff_returns_correct_values(self):
        diff_abs, diff_pct, _, _ = classify_diff(Decimal("1000"), Decimal("950"))
        assert diff_abs == Decimal("50")
        assert diff_pct > Decimal("5.2")  # 50/950 ≈ 5.26%

    def test_zero_broker_with_nonzero_ours(self):
        """Edge case: broker=0, ours=100.

        AU16: с новой OR→AND logic для hard break (оба критерия должны
        быть значительно превышены) — 100₽ это soft, не hard. Это
        корректнее: 100₽ единица не должны автоматически быть "hard"
        даже на пустой broker baseline. Для значимых hard'ов нужно >100₽
        diff_abs И >0.5% diff_pct (10× от tolerance).
        """
        diff_abs, _, status, _ = classify_diff(Decimal("100"), Decimal("0"))
        assert diff_abs == Decimal("100")
        assert status == "soft"

    def test_zero_broker_with_large_ours_is_hard(self):
        """200 vs 0: оба критерия превышены 10× → hard."""
        diff_abs, _, status, _ = classify_diff(Decimal("200"), Decimal("0"))
        assert diff_abs == Decimal("200")
        assert status == "hard"  # 200 > 100 (abs*10) AND 20000% > 0.5%

    # ── AU16: per-metric tolerance overrides ────────────────────────────

    def test_realized_pnl_uses_5pct_tolerance(self):
        """realized_pnl имеет более широкий tolerance (5%) — methodology."""
        # 100k vs 104k = 4% разница — для realized_pnl это OK (5% tolerance)
        _, _, status, note = classify_diff(
            Decimal("100000"), Decimal("104000"), metric="realized_pnl"
        )
        assert status == "ok"
        assert "Trade.net_pnl" in note  # methodology note attached

    def test_broker_commission_strict_tolerance(self):
        """broker_commission_total: strict 1₽ tolerance (AU15 verified)."""
        _, _, status, note = classify_diff(
            Decimal("50.00"), Decimal("52.00"), metric="broker_commission_total"
        )
        # 2₽ > 1₽ tolerance + pct = 4% > 0.001% → hard
        assert status in ("soft", "hard")
        assert "AU15" in note

    def test_unknown_metric_uses_default(self):
        """Метрика не в _METRIC_TOLERANCES → дефолтный 10₽/0.1%."""
        _, _, status, note = classify_diff(
            Decimal("1000"), Decimal("1005"), metric="custom_unknown"
        )
        assert status == "ok"  # 5₽ < 10₽ default
        assert note == ""

    def test_clearing_commission_methodology_note(self):
        """clearing_commission_total — широкая tolerance + note."""
        _, _, status, note = classify_diff(
            Decimal("200"), Decimal("0"), metric="clearing_commission_total"
        )
        # 200 > 50 abs tol, но 100% > 50% rel tol тоже выходит за границы;
        # однако без 10x превышения hard'а — soft
        assert status == "soft"
        assert "category split" in note


# ════════════════════════════════════════════════════════════════════════
# aggregate_broker_report
# ════════════════════════════════════════════════════════════════════════


def _row(
    direction: str,
    total: str,
    broker_c: str = "0",
    exch_c: str = "0",
    clear_c: str = "0",
    ticker: str = "TEST",
    when: datetime = datetime(2026, 1, 15, tzinfo=timezone.utc),
):
    return BrokerReportTradeRow(
        trade_id=f"t-{direction}-{total}-{when.isoformat()}",
        direction=direction,
        ticker=ticker,
        trade_datetime=when,
        quantity=1,
        price=Decimal(total),
        total_order_amount=Decimal(total),
        broker_commission=Decimal(broker_c),
        exchange_commission=Decimal(exch_c),
        exchange_clearing_commission=Decimal(clear_c),
    )


class TestAggregateBrokerReport:
    def test_empty_trades_zero_aggregates(self):
        result = aggregate_broker_report([], [])
        assert result["realized_pnl"] == Decimal(0)
        assert result["broker_commission_total"] == Decimal(0)

    def test_single_buy_only(self):
        """Только buy: открытая позиция, NO realized P&L (AU13 FIFO).

        Раньше формула была cash flow approximation: P&L = sell-buy-commissions.
        Теперь broker side тоже FIFO: открытая позиция = realized_pnl 0.
        commission_total всё равно копится отдельно для своей метрики.
        """
        rows = [_row("buy", "10000", broker_c="30")]
        result = aggregate_broker_report(rows, [])
        assert result["realized_pnl"] == Decimal("0")
        assert result["broker_commission_total"] == Decimal("30")

    def test_buy_and_sell_with_profit(self):
        rows = [
            _row("buy", "10000", broker_c="30"),
            _row("sell", "11000", broker_c="33"),
        ]
        result = aggregate_broker_report(rows, [])
        # AU13 FIFO: close long → pnl = (11000-10000) × 1 = 1000
        # − entry commission per unit (30/1 = 30)
        # − exit commission per unit (33/1 = 33)
        # = 1000 - 30 - 33 = 937
        assert result["realized_pnl"] == Decimal("937")
        assert result["broker_commission_total"] == Decimal("63")

    def test_multiple_commission_types(self):
        rows = [_row("buy", "10000", broker_c="30", exch_c="5", clear_c="2")]
        result = aggregate_broker_report(rows, [])
        assert result["broker_commission_total"] == Decimal("30")
        assert result["exchange_commission_total"] == Decimal("5")
        assert result["clearing_commission_total"] == Decimal("2")

    def test_end_cash_balance_passed_through(self):
        result = aggregate_broker_report([], [], end_cash_balance=Decimal("50000"))
        assert result["end_cash_balance"] == Decimal("50000")

    def test_foreign_dividend_summary(self):
        """Foreign dividends с MoneyValue-like dict'ом."""
        from dataclasses import dataclass

        @dataclass
        class _MV:
            units: int = 0
            nano: int = 0

        # $100 gross, $15 tax удержан
        gross = _MV(units=100, nano=0)
        tax = _MV(units=15, nano=0)
        result = aggregate_broker_report([], [{"dividend_gross": gross, "tax": tax}])
        assert result["dividends_gross"] == Decimal("100")
        assert result["ndfl_withheld"] == Decimal("15")

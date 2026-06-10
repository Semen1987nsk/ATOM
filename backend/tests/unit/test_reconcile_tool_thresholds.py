"""MATH-09: пороги reconcile_journal_vs_cash должны совпадать с pnl_health_service (5/25%)."""
from decimal import Decimal


def test_reconcile_thresholds_match_pnl_health_service():
    from tools.reconcile_journal_vs_cash import THRESHOLD_OK_PCT, THRESHOLD_WARN_PCT
    from services.pnl_health_service import THRESHOLD_OK_PCT as HEALTH_OK
    from services.pnl_health_service import THRESHOLD_WARNING_PCT as HEALTH_WARN
    assert THRESHOLD_OK_PCT == HEALTH_OK == Decimal("5.0")
    assert THRESHOLD_WARN_PCT == HEALTH_WARN == Decimal("25.0")

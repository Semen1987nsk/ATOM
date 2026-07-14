import pytest
from sqlalchemy.exc import IntegrityError

from routers import trades as trades_router


def test_non_dedup_integrity_reraised():
    # Хелпер-классификатор: только uq_trades_dedup_v2 → 409, остальное re-raise.
    class _Orig(Exception):
        def __str__(self):
            return 'NOT NULL constraint failed: trades.account_id'
    exc = IntegrityError("stmt", {}, _Orig())
    assert trades_router._is_duplicate_trade_error(exc) is False


def test_dedup_integrity_is_duplicate():
    class _Orig(Exception):
        def __str__(self):
            return 'UNIQUE constraint failed: uq_trades_dedup_v2'
    exc = IntegrityError("stmt", {}, _Orig())
    assert trades_router._is_duplicate_trade_error(exc) is True

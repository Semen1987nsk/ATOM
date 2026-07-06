"""S3-14: get_net_deposits_baseline_from_db возвращает знаковую сумму."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics._common_baseline import get_net_deposits_baseline_from_db  # noqa: E402


def _db_with_sum(units, nano):
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.one.return_value = (units, nano)
    return db


def test_net_negative_stays_negative():
    # Выведено 100k, внесено 20k → Σ = -80000 (не +80000).
    db = _db_with_sum(-80_000, 0)
    result = get_net_deposits_baseline_from_db(db, account_id=1)
    assert result == Decimal("-80000")


def test_net_positive_unchanged():
    db = _db_with_sum(150_000, 0)
    assert get_net_deposits_baseline_from_db(db, account_id=1) == Decimal("150000")

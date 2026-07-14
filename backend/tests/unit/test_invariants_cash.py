from datetime import datetime

import models
from services import invariants_service


def test_cash_invariant_uses_real_snapshot_columns(db_session):
    user = models.User(email="inv@x.com", hashed_password="x", is_active=1)
    db_session.add(user)
    db_session.flush()
    acc = models.Account(user_id=user.id, name="acc")
    db_session.add(acc)
    db_session.flush()
    db_session.add(models.BalanceSnapshot(account_id=acc.id, date=datetime(2025, 1, 1), balance=100000))
    db_session.add(models.BalanceSnapshot(account_id=acc.id, date=datetime(2025, 12, 31), balance=150000))
    # output-операция должна попасть в withdrawals
    db_session.add(models.OperationORM(
        account_id=acc.id, broker_account_id="brk1", operation_id="op1",
        operation_type="output", executed_at=datetime(2025, 6, 1), state="executed",
        payment_units=-50000, payment_nano=0,
    ))
    db_session.commit()

    # Не должно кидать AttributeError на snapshot_date/total_value.
    check = invariants_service._cash_invariant(
        db_session, acc.id, datetime(2025, 1, 1), datetime(2025, 12, 31)
    )
    assert check.name == "cash"

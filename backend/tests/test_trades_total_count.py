"""API-02: GET /trades/ отдаёт X-Total-Count, чтобы фронт видел усечение списка."""
from datetime import datetime

from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers

import models


def _seed_trades(db, account_id: int, n: int) -> None:
    for i in range(n):
        db.add(models.Trade(
            account_id=account_id,
            symbol="SBER",
            direction=models.TradeDirection.LONG,
            entry_price=100 + i,
            quantity=1,
            entry_at=datetime(2025, 1, 1, 10, i),
        ))
    db.commit()


def test_total_count_header_with_truncated_page(test_app):
    db = test_app["db"]
    u, acc = _make_user(db, "count@test.com")
    _seed_trades(db, acc.id, 3)

    r = test_app["client"].get("/trades/?limit=2", headers=_auth_headers(u))

    assert r.status_code == 200
    assert r.headers.get("X-Total-Count") == "3"
    assert len(r.json()) == 2


def test_total_count_header_when_all_fit(test_app):
    db = test_app["db"]
    u, acc = _make_user(db, "count2@test.com")
    _seed_trades(db, acc.id, 3)

    r = test_app["client"].get("/trades/", headers=_auth_headers(u))

    assert r.status_code == 200
    assert r.headers.get("X-Total-Count") == "3"
    assert len(r.json()) == 3

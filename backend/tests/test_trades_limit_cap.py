"""API-04: cap on ?limit for /trades/ and /trades/positions."""
from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers


def test_trades_limit_capped(test_app):
    db = test_app["db"]
    u, _ = _make_user(db, "lim@test.com")
    r = test_app["client"].get("/trades/?limit=10000000", headers=_auth_headers(u))
    assert r.status_code == 422


def test_positions_limit_capped(test_app):
    db = test_app["db"]
    u, _ = _make_user(db, "lim2@test.com")
    r = test_app["client"].get("/trades/positions?limit=10000000", headers=_auth_headers(u))
    assert r.status_code == 422

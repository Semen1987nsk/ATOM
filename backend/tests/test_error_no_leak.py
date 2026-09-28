"""API-13: internal exception strings must not leak into response bodies."""
from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers


def test_onboarding_error_no_internal_detail(test_app, monkeypatch):
    db = test_app["db"]
    u, _ = _make_user(db, "leak@test.com")

    # Account is required so the loop reaches reconcile_account (not 404).
    import models
    acc = models.Account(user_id=u.id, name="Leak Acc")
    db.add(acc)
    db.commit()

    import services.reconciliation_service as rs

    async def boom(*a, **k):
        raise RuntimeError("secret dsn leaked")

    monkeypatch.setattr(rs, "reconcile_account", boom)

    r = test_app["client"].post("/onboarding/reconcile", headers=_auth_headers(u))
    assert "secret dsn leaked" not in r.text

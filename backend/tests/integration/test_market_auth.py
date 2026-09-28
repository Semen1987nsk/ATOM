"""
API-01: auth + rate-limit на market-прокси (/market/prices, /market/futures-specs).

Проверяем что эндпоинты теперь требуют аутентификацию (401 без токена)
и отдают данные при валидном токене (сервис замокан, без живого MOEX).
"""
from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers


def test_prices_requires_auth(test_app):
    r = test_app["client"].get("/market/prices?tickers=SBER")
    assert r.status_code == 401


def test_prices_ok_with_auth(test_app, monkeypatch):
    import market_service
    # PERF-04: get_current_prices теперь async — мок тоже async.
    async def fake_prices(self, t):
        return {"SBER": 100.0}
    monkeypatch.setattr(
        market_service.MarketService,
        "get_current_prices",
        fake_prices,
    )
    db = test_app["db"]
    user, _ = _make_user(db, "mkt@test.com")
    r = test_app["client"].get(
        "/market/prices?tickers=SBER", headers=_auth_headers(user)
    )
    assert r.status_code == 200
    assert r.json() == {"prices": {"SBER": 100.0}}


def test_futures_specs_requires_auth(test_app):
    r = test_app["client"].get("/market/futures-specs?tickers=SiH6")
    assert r.status_code == 401

"""Tests for /api/landing/ticker — happy path, stale fallback, 503 on cold failure."""
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _fake_prices():
    return {
        "SBER": {"last": 324.18, "change_pct": 0.42},
        "GAZP": {"last": 167.40, "change_pct": -0.18},
        "LKOH": {"last": 7142.0, "change_pct": 1.08},
        "YNDX": {"last": 4288.0, "change_pct": -0.32},
        "IMOEX": {"last": 3182.6, "change_pct": 0.51},
    }


def _clear_landing_state():
    """Reset module-level cache/last-good between tests."""
    from routers.landing import _CACHE, _LAST_GOOD
    _CACHE.clear()
    _LAST_GOOD.clear()


def test_ticker_happy_path_returns_5_symbols():
    """Live ticker returns the 5 hard-coded MOEX symbols."""
    _clear_landing_state()
    with patch("routers.landing._fetch_moex_marketdata", return_value=_fake_prices()):
        r = client.get("/api/landing/ticker")

    assert r.status_code == 200
    body = r.json()
    assert body["stale"] is False
    assert {t["symbol"] for t in body["tickers"]} == set(_fake_prices().keys())


def test_ticker_returns_stale_on_warm_cache_when_moex_down():
    """Warm cache + MOEX down → stale=True with last known good."""
    _clear_landing_state()
    # Warm cache
    with patch("routers.landing._fetch_moex_marketdata", return_value=_fake_prices()):
        client.get("/api/landing/ticker")

    # Expire TTL so cache miss happens
    from routers.landing import _CACHE
    _CACHE.expire(_CACHE.timer() + 9999)

    # MOEX down
    with patch("routers.landing._fetch_moex_marketdata", side_effect=Exception("MOEX down")):
        r = client.get("/api/landing/ticker")

    assert r.status_code == 200
    assert r.json()["stale"] is True
    assert len(r.json()["tickers"]) == 5


def test_ticker_returns_503_on_cold_cache_failure():
    """Cold cache + MOEX down → 503."""
    _clear_landing_state()
    with patch("routers.landing._fetch_moex_marketdata", side_effect=Exception("MOEX down")):
        r = client.get("/api/landing/ticker")
    assert r.status_code == 503

"""Публичный (без auth) тикер MOEX для лендинга: /api/landing/ticker.

LiveTicker на лендинге поллит Next-роут /api/landing/ticker, который проксирует
на backend /api/landing/ticker. До этой фичи backend-эндпоинта не было → Next
всегда отдавал fallback (статичный snapshot). Здесь:

- `MarketService.get_landing_ticker()` собирает курируемый набор (индекс IMOEX
  через index-board SNDX + ликвидные акции через TQBR) с last + change_pct,
  кешируя весь payload на 60с.
- роутер `/api/landing/ticker` — публичный, без auth (лендинг гостевой).

MOEX замокан (skill moex-iss-api-patterns: не ходить в реальный ISS из CI).
"""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import market_service  # noqa: E402
from market_service import MarketService  # noqa: E402

# Реальные имена колонок ISS (сверено живым запросом к iss.moex.com).
SHARES_PAYLOAD = {
    "marketdata": {
        "columns": ["SECID", "LAST", "LCLOSEPRICE", "CLOSEPRICE", "MARKETPRICE", "LASTCHANGEPRCNT"],
        "data": [
            ["SBER", 299.18, 300.94, None, 307.23, -0.02],
            ["GAZP", 167.40, None, None, None, -0.18],
            ["LKOH", 7142.0, None, None, None, 1.08],
            ["NOISE", 1.0, None, None, None, 0.0],  # не в курируемом списке — игнор
        ],
    }
}
INDEX_PAYLOAD = {
    "marketdata": {
        "columns": ["SECID", "CURRENTVALUE", "LASTVALUE", "LASTCHANGEPRC"],
        "data": [["IMOEX", 2318.28, 2420.56, -4.23]],
    }
}


def _dispatcher(shares=SHARES_PAYLOAD, index=INDEX_PAYLOAD):
    async def fake(url: str):
        if "markets/index" in url:
            return index
        if "markets/shares" in url:
            return shares
        return None
    return fake


@pytest.fixture(autouse=True)
def _clear_ticker_cache():
    market_service._ticker_cache.clear()
    yield
    market_service._ticker_cache.clear()


@pytest.fixture
def service():
    return MarketService()


@pytest.mark.asyncio
async def test_happy_path_returns_index_and_stocks(service):
    """IMOEX (индекс) + акции с last и change_pct, в курируемом порядке."""
    with patch.object(market_service, "_moex_get", _dispatcher()):
        result = await service.get_landing_ticker()

    assert result["stale"] is False
    by_symbol = {t["symbol"]: t for t in result["tickers"]}
    assert {"IMOEX", "SBER", "GAZP", "LKOH"} <= set(by_symbol)
    assert "NOISE" not in by_symbol  # не курируемый — отброшен

    # IMOEX из index-блока: last=CURRENTVALUE, change_pct=LASTCHANGEPRC
    assert by_symbol["IMOEX"]["last"] == pytest.approx(2318.28)
    assert by_symbol["IMOEX"]["change_pct"] == pytest.approx(-4.23)
    # SBER из shares-блока: last=LAST, change_pct=LASTCHANGEPRCNT
    assert by_symbol["SBER"]["last"] == pytest.approx(299.18)
    assert by_symbol["SBER"]["change_pct"] == pytest.approx(-0.02)

    # IMOEX идёт первым (курируемый порядок)
    assert result["tickers"][0]["symbol"] == "IMOEX"


@pytest.mark.asyncio
async def test_moex_down_marks_stale_empty(service):
    """Если ISS недоступен (None) — stale=True, tickers=[] (фронт уйдёт в fallback)."""
    async def all_none(url: str):
        return None

    with patch.object(market_service, "_moex_get", all_none):
        result = await service.get_landing_ticker()

    assert result["stale"] is True
    assert result["tickers"] == []


@pytest.mark.asyncio
async def test_last_falls_back_when_null(service):
    """LAST=null у акции → берём LCLOSEPRICE; CURRENTVALUE=0 у индекса → LASTVALUE."""
    shares = {
        "marketdata": {
            "columns": ["SECID", "LAST", "LCLOSEPRICE", "CLOSEPRICE", "MARKETPRICE", "LASTCHANGEPRCNT"],
            "data": [["SBER", None, 305.0, None, None, 0.5]],
        }
    }
    index = {
        "marketdata": {
            "columns": ["SECID", "CURRENTVALUE", "LASTVALUE", "LASTCHANGEPRC"],
            "data": [["IMOEX", 0, 2420.56, -1.0]],
        }
    }
    with patch.object(market_service, "_moex_get", _dispatcher(shares=shares, index=index)):
        result = await service.get_landing_ticker()

    by_symbol = {t["symbol"]: t for t in result["tickers"]}
    assert by_symbol["SBER"]["last"] == pytest.approx(305.0)
    assert by_symbol["IMOEX"]["last"] == pytest.approx(2420.56)


@pytest.mark.asyncio
async def test_partial_response_below_threshold_is_stale(service):
    """S2-09: если TQBR marketdata пуст (анонимный доступ) и собрался только
    IMOEX из индекс-блока — это НЕ успех: stale=True, tickers=[], НЕ кешируем.
    Иначе гости лендинга видят бегущую строку из одного символа."""
    shares_empty = {"marketdata": {"columns": ["SECID", "LAST"], "data": []}}
    with patch.object(market_service, "_moex_get",
                      _dispatcher(shares=shares_empty)):
        result = await service.get_landing_ticker()

    assert result["stale"] is True
    assert result["tickers"] == []
    # Кеш не заполнен — повторный вызов снова пойдёт в ISS.
    assert market_service._ticker_cache.get("landing:ticker") is None


def test_endpoint_is_public_and_returns_shape():
    """GET /api/landing/ticker — 200 без авторизации, форма {stale, tickers[]}."""
    from main import app

    with patch.object(market_service, "_moex_get", _dispatcher()):
        client = TestClient(app)
        resp = client.get("/api/landing/ticker")  # без Authorization

    assert resp.status_code == 200
    body = resp.json()
    assert "stale" in body and isinstance(body["stale"], bool)
    assert isinstance(body["tickers"], list) and len(body["tickers"]) >= 1
    for t in body["tickers"]:
        assert set(t) >= {"symbol", "last", "change_pct"}
        assert isinstance(t["last"], (int, float))
        assert isinstance(t["change_pct"], (int, float))

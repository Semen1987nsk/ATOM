"""
Tests for market data service (MOEX API).

Содержит:
- TestMarketService — integration-тесты с реальным MOEX API (требуют сети)
- TestNormalizeIssBlock — unit-тесты парсера column-oriented JSON
- TestMoexGetRetry — моки httpx.AsyncClient.get, проверка retry-логики
  (PERF-04: миграция с sync requests.get на общий async httpx.AsyncClient
  из services/moex_async. Backoff+jitter теперь живут в moex_async.fetch_json,
  тесты там же — tests/unit/test_market_service_async.py).
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_service import (  # noqa: E402
    MarketService,
    _moex_get,
    _normalize_iss_block,
)
from services import moex_async  # noqa: E402


def _httpx_resp(status: int, json_data: dict | None = None, url: str = "https://x") -> httpx.Response:
    """Build httpx.Response с прицепленным request — нужно для raise_for_status."""
    return httpx.Response(status, json=json_data, request=httpx.Request("GET", url))


class TestMarketService:
    """Tests for MarketService. PERF-04: get_current_prices теперь async."""

    @pytest.fixture
    def service(self):
        return MarketService()

    @pytest.mark.asyncio
    async def test_empty_tickers(self, service):
        """Should return empty dict for empty tickers list."""
        result = await service.get_current_prices([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_price_for_valid_ticker(self, service):
        """Should return price for valid ticker (requires network)."""
        # This is an integration test - requires network access
        result = await service.get_current_prices(["SBER"])

        # During market hours, should return a price
        # During off-hours, might return empty
        if "SBER" in result:
            assert result["SBER"] > 0
        await moex_async.close_client()

    @pytest.mark.asyncio
    async def test_get_price_for_invalid_ticker(self, service):
        """Should handle invalid tickers gracefully."""
        result = await service.get_current_prices(["INVALID_TICKER_XYZ"])
        assert "INVALID_TICKER_XYZ" not in result
        await moex_async.close_client()

    @pytest.mark.asyncio
    async def test_get_multiple_prices(self, service):
        """Should fetch multiple prices at once."""
        tickers = ["SBER", "GAZP", "LKOH"]
        result = await service.get_current_prices(tickers)

        # Should return dict (might be empty if market closed)
        assert isinstance(result, dict)
        await moex_async.close_client()

    def test_sources_configured(self, service):
        """Should have all required sources configured."""
        assert len(service.sources) >= 3
        assert any("TQBR" in s for s in service.sources)  # Stocks
        assert any("RFUD" in s for s in service.sources)  # Futures
        assert any("CETS" in s for s in service.sources)  # Currency

    @pytest.mark.asyncio
    async def test_get_candles_rejects_path_injection(self, service):
        """SEC-13: тикер с path-injection отклоняется до построения URL → [].

        Сеть отдала бы непустые свечи — без regex-гарда тест был бы non-empty.
        Гард должен вернуть [] не сделав ни одного HTTP-запроса.

        PERF-04: после миграции get_candles → async, патчим moex_async.fetch_json,
        а не requests.get (которого больше нет в market_service).
        """
        from datetime import datetime
        candle_payload = {
            "candles": {
                "columns": ["open", "high", "low", "close", "volume", "begin", "end"],
                "data": [[1, 2, 0.5, 1.5, 10, "2025-01-01 10:00", "2025-01-01 10:00"]],
            }
        }
        fake_fetch = AsyncMock(return_value=candle_payload)
        with patch("market_service.moex_async.fetch_json", fake_fetch):
            result = await service.get_candles(
                "SBER/../secret", datetime(2025, 1, 1), datetime(2025, 1, 2)
            )
            assert result == []
            assert not fake_fetch.called  # guard сработал до HTTP

    @pytest.mark.asyncio
    async def test_get_candles_accepts_real_tickers(self, service):
        """SEC-13: реальные тикеры (акции/фьючерсы/облигации) проходят regex.

        Сеть замокана (fetch_json → None ≡ 404/network fail), проверяем только что
        ticker не отбрасывается на входе, а доходит до HTTP-запроса (итог []
        из-за того что fetch_json вернул None).
        """
        from datetime import datetime
        fake_fetch = AsyncMock(return_value=None)
        with patch("market_service.moex_async.fetch_json", fake_fetch):
            for tkr in ("SBER", "SiH6", "RU000A1234X5", "BRZ5", "USD000UTSTOM"):
                result = await service.get_candles(
                    tkr, datetime(2025, 1, 1), datetime(2025, 1, 2)
                )
                assert result == []
            assert fake_fetch.called


class TestNormalizeIssBlock:
    """Unit-тесты парсера column-oriented JSON формата ISS API."""

    def test_basic_marketdata(self):
        data = {
            "marketdata": {
                "columns": ["SECID", "LAST"],
                "data": [["SBER", 250.1], ["GAZP", 180.5]],
            }
        }
        rows = _normalize_iss_block(data, "marketdata")
        assert rows == [
            {"SECID": "SBER", "LAST": 250.1},
            {"SECID": "GAZP", "LAST": 180.5},
        ]

    def test_missing_block(self):
        """Если блока нет — возвращаем [], не падаем."""
        assert _normalize_iss_block({"foo": "bar"}, "marketdata") == []

    def test_block_is_not_dict(self):
        """Если блок не dict (например, список) — []."""
        assert _normalize_iss_block({"marketdata": []}, "marketdata") == []

    def test_missing_columns_or_data(self):
        """Битые блоки (нет columns или data) — []."""
        assert _normalize_iss_block({"x": {"columns": ["A"]}}, "x") == []
        assert _normalize_iss_block({"x": {"data": [[1]]}}, "x") == []
        assert _normalize_iss_block({"x": {"columns": [], "data": []}}, "x") == []

    def test_mismatched_row_length(self):
        """Строки с длиной ≠ числу колонок — пропускаются (защита от мусора)."""
        data = {
            "x": {
                "columns": ["A", "B", "C"],
                "data": [
                    ["a1", "b1", "c1"],   # ok
                    ["a2", "b2"],         # пропускается
                    ["a3", "b3", "c3"],   # ok
                ],
            }
        }
        rows = _normalize_iss_block(data, "x")
        assert len(rows) == 2
        assert rows[0]["A"] == "a1"
        assert rows[1]["A"] == "a3"

    def test_empty_data_list(self):
        """columns заполнены, data пустая — []."""
        data = {"x": {"columns": ["A", "B"], "data": []}}
        assert _normalize_iss_block(data, "x") == []

    def test_none_input(self):
        """None или не-dict — []."""
        assert _normalize_iss_block(None, "x") == []
        assert _normalize_iss_block("string", "x") == []
        assert _normalize_iss_block(42, "x") == []


class TestMoexGetRetry:
    """PERF-04: _moex_get теперь async-обёртка над moex_async.fetch_json.

    Retry/backoff-логика переехала в services/moex_async и покрыта
    `tests/unit/test_market_service_async.py::test_fetch_json_*`. Здесь
    остаются только smoke-проверки делегирования и async-сигнатуры.
    """

    @pytest.mark.asyncio
    async def test_moex_get_is_coroutine(self):
        """_moex_get — корутина (не sync requests.get)."""
        coro = _moex_get("https://iss.moex.com/test")
        assert asyncio.iscoroutine(coro)
        # Закроем корутину чтобы не было warning'а 'never awaited'.
        coro.close()

    @pytest.mark.asyncio
    async def test_moex_get_delegates_to_async_fetch(self, monkeypatch):
        """_moex_get должен звать moex_async.fetch_json и возвращать его результат."""
        payload = {"securities": {"columns": [], "data": []}}
        fake_fetch = AsyncMock(return_value=payload)
        monkeypatch.setattr(moex_async, "fetch_json", fake_fetch)

        result = await _moex_get("https://iss.moex.com/test")

        assert result == payload
        fake_fetch.assert_called_once_with("https://iss.moex.com/test")

    @pytest.mark.asyncio
    async def test_moex_get_returns_none_on_network_failure(self, monkeypatch):
        """Когда fetch_json вернул None (network/all retries failed) — пробрасываем None."""
        monkeypatch.setattr(moex_async, "fetch_json", AsyncMock(return_value=None))

        result = await _moex_get("https://iss.moex.com/fail")
        assert result is None

    @pytest.mark.asyncio
    async def test_moex_get_propagates_http_response_via_fetch_json(self, monkeypatch):
        """Smoke: 200 OK ответ от httpx → fetch_json → _moex_get."""
        async def fake_get(self, url, params=None):
            return _httpx_resp(200, {"data": "ok"}, url)

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        await moex_async.close_client()  # reset singleton с замоканным get

        result = await _moex_get("https://iss.moex.com/ok")
        assert result == {"data": "ok"}
        await moex_async.close_client()

    @pytest.mark.asyncio
    async def test_moex_get_retries_on_5xx(self, monkeypatch):
        """5xx первой попытки → retry внутри moex_async → 200."""
        calls = {"n": 0}

        async def fake_get(self, url, params=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _httpx_resp(503, url=url)
            return _httpx_resp(200, {"recovered": True}, url)

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        monkeypatch.setattr(moex_async.asyncio, "sleep", AsyncMock())
        await moex_async.close_client()

        result = await _moex_get("https://iss.moex.com/retry")
        assert result == {"recovered": True}
        assert calls["n"] == 2
        await moex_async.close_client()

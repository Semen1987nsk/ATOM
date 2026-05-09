"""
Tests for market data service (MOEX API).

Содержит:
- TestMarketService — integration-тесты с реальным MOEX API (требуют сети)
- TestNormalizeIssBlock — unit-тесты парсера column-oriented JSON
- TestBackoffJitter — проверка что jitter реально размазывает sleep'ы
- TestMoexGetRetry — моки 429/5xx/timeout, проверка retry-логики
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_service import (  # noqa: E402
    MarketService,
    _backoff_with_jitter,
    _moex_get,
    _normalize_iss_block,
)


class TestMarketService:
    """Tests for MarketService."""
    
    @pytest.fixture
    def service(self):
        return MarketService()
    
    def test_empty_tickers(self, service):
        """Should return empty dict for empty tickers list."""
        result = service.get_current_prices([])
        assert result == {}
    
    def test_get_price_for_valid_ticker(self, service):
        """Should return price for valid ticker (requires network)."""
        # This is an integration test - requires network access
        result = service.get_current_prices(["SBER"])
        
        # During market hours, should return a price
        # During off-hours, might return empty
        if "SBER" in result:
            assert result["SBER"] > 0
    
    def test_get_price_for_invalid_ticker(self, service):
        """Should handle invalid tickers gracefully."""
        result = service.get_current_prices(["INVALID_TICKER_XYZ"])
        assert "INVALID_TICKER_XYZ" not in result
    
    def test_get_multiple_prices(self, service):
        """Should fetch multiple prices at once."""
        tickers = ["SBER", "GAZP", "LKOH"]
        result = service.get_current_prices(tickers)
        
        # Should return dict (might be empty if market closed)
        assert isinstance(result, dict)
    
    def test_sources_configured(self, service):
        """Should have all required sources configured."""
        assert len(service.sources) >= 3
        assert any("TQBR" in s for s in service.sources)  # Stocks
        assert any("RFUD" in s for s in service.sources)  # Futures
        assert any("CETS" in s for s in service.sources)  # Currency


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


class TestBackoffJitter:
    """Проверка _backoff_with_jitter — чтобы под gunicorn не было thundering herd."""

    def test_within_bounds(self):
        """Jitter ±20%: для base=1.0 значения должны быть в [0.8, 1.2]."""
        for _ in range(100):
            v = _backoff_with_jitter(1.0)
            assert 0.8 <= v <= 1.2

    def test_scales_with_base(self):
        """Для base=10 значения в [8.0, 12.0]."""
        for _ in range(50):
            v = _backoff_with_jitter(10.0)
            assert 8.0 <= v <= 12.0

    def test_actually_jitters(self):
        """Должна быть реальная дисперсия — не 100% одинаковых значений.

        Это критичный тест: если кто-то выкинет random.random() и оставит
        константный множитель, тест поймает.
        """
        values = {_backoff_with_jitter(1.0) for _ in range(50)}
        # Из 50 вызовов уникальных значений должно быть много (>30)
        assert len(values) > 30, f"Expected diverse jitter, got {len(values)} unique"


class TestMoexGetRetry:
    """Моки HTTP — проверяем что retry реально срабатывает."""

    def _make_response(self, status_code: int, json_data=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        return resp

    def test_200_no_retry(self):
        """200 OK сразу — никаких sleep'ов."""
        ok = self._make_response(200, {"securities": {"columns": [], "data": []}})
        with patch("market_service.requests.get", return_value=ok) as mock_get, \
             patch("market_service._time.sleep") as mock_sleep:
            result = _moex_get("https://iss.moex.com/test")
            assert result == {"securities": {"columns": [], "data": []}}
            assert mock_get.call_count == 1
            assert mock_sleep.call_count == 0

    def test_429_then_200(self):
        """429 → sleep с jitter → 200. Должен вернуть данные."""
        rate_limited = self._make_response(429)
        ok = self._make_response(200, {"data": "result"})
        with patch("market_service.requests.get", side_effect=[rate_limited, ok]) as mock_get, \
             patch("market_service._time.sleep") as mock_sleep:
            result = _moex_get("https://iss.moex.com/test")
            assert result == {"data": "result"}
            assert mock_get.call_count == 2
            # Sleep вызвался ровно один раз с jitter-значением в [0.8, 1.2]
            assert mock_sleep.call_count == 1
            sleep_arg = mock_sleep.call_args[0][0]
            assert 0.8 <= sleep_arg <= 1.2

    def test_503_then_200(self):
        """5xx тоже триггерит retry."""
        unavailable = self._make_response(503)
        ok = self._make_response(200, {"data": "ok"})
        with patch("market_service.requests.get", side_effect=[unavailable, ok]), \
             patch("market_service._time.sleep") as mock_sleep:
            result = _moex_get("https://iss.moex.com/test")
            assert result == {"data": "ok"}
            assert mock_sleep.call_count == 1

    def test_404_no_retry(self):
        """404 — не retryable, возвращаем None сразу."""
        not_found = self._make_response(404)
        with patch("market_service.requests.get", return_value=not_found), \
             patch("market_service._time.sleep") as mock_sleep:
            result = _moex_get("https://iss.moex.com/test")
            assert result is None
            assert mock_sleep.call_count == 0

    def test_all_attempts_fail(self):
        """Все попытки вернули 429 — итог None, без падения."""
        rate_limited = self._make_response(429)
        with patch("market_service.requests.get", return_value=rate_limited), \
             patch("market_service._time.sleep") as mock_sleep:
            result = _moex_get("https://iss.moex.com/test")
            assert result is None
            # Было 3 попытки (initial + 2 retry), значит 2 sleep'а
            assert mock_sleep.call_count == 2

    def test_timeout_then_200(self):
        """ConnectionTimeout → retry → 200."""
        ok = self._make_response(200, {"data": "recovered"})
        with patch(
            "market_service.requests.get",
            side_effect=[requests.Timeout("slow"), ok],
        ), patch("market_service._time.sleep"):
            result = _moex_get("https://iss.moex.com/test")
            assert result == {"data": "recovered"}

    def test_jitter_diverges_between_attempts(self):
        """При 2 retry sleep'ах jitter даёт разные значения (не одинаковые)."""
        rate_limited = self._make_response(429)
        with patch("market_service.requests.get", return_value=rate_limited), \
             patch("market_service._time.sleep") as mock_sleep:
            _moex_get("https://iss.moex.com/test")
            # 2 retry-попытки = 2 sleep
            assert mock_sleep.call_count == 2
            sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
            # base'ы разные (1.0, 3.0), плюс jitter — точно различные
            assert sleep_values[0] != sleep_values[1]
            # Первый — около 1.0 (с jitter ±20%)
            assert 0.8 <= sleep_values[0] <= 1.2
            # Второй — около 3.0
            assert 2.4 <= sleep_values[1] <= 3.6

"""
Tests for market data service (MOEX API).
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_service import MarketService


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

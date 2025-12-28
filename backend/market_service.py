import requests
from typing import List, Dict, Optional
from logger import get_logger

log = get_logger("market")

class MarketService:
    def __init__(self):
        self.sources = [
            # Stocks (Main Board)
            "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json",
            # Futures (Main Board)
            "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities.json",
            # Currencies (ETS) - Optional, but good to have
            "https://iss.moex.com/iss/engines/currency/markets/selt/boards/CETS/securities.json" 
        ]

    def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetches current prices from MOEX ISS (Stocks, Futures, Currencies).
        Returns a dictionary {ticker: price}.
        """
        prices = {}
        
        # Optimization: If no tickers requested, don't fetch
        if not tickers:
            return {}

        log.debug(f"Fetching prices for {len(tickers)} tickers: {tickers}")

        for url in self.sources:
            try:
                response = requests.get(url, timeout=5)
                data = response.json()
                
                if 'marketdata' not in data:
                    continue

                columns = data['marketdata']['columns']
                rows = data['marketdata']['data']
                
                # Find indices for SECID and LAST
                try:
                    secid_idx = columns.index('SECID')
                    last_idx = columns.index('LAST')
                except ValueError:
                    continue

                # Create a map of all available prices in this source
                for row in rows:
                    ticker = row[secid_idx]
                    price = row[last_idx]
                    
                    # Some instruments might have None as price (not traded yet today)
                    if price is not None:
                        # Only add if it's one of the requested tickers (optimization)
                        # OR if we want to cache everything (but here we filter)
                        if ticker in tickers:
                            prices[ticker] = float(price)
            
            except Exception as e:
                log.warning(f"Error fetching MOEX data from {url}: {e}")
                continue
        
        log.debug(f"Retrieved {len(prices)} prices")
        return prices

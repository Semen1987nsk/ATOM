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

    def get_futures_specs(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Fetches futures specifications (MINSTEP, STEPPRICE) from MOEX.
        Returns a dictionary {ticker: {minstep: float, stepprice: float}}.
        """
        specs = {}
        
        if not tickers:
            return {}
        
        # Futures securities endpoint
        url = "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities.json"
        
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if 'securities' not in data:
                return {}
            
            columns = data['securities']['columns']
            rows = data['securities']['data']
            
            # Find indices
            try:
                secid_idx = columns.index('SECID')
                minstep_idx = columns.index('MINSTEP')
                stepprice_idx = columns.index('STEPPRICE')
            except ValueError:
                log.warning("Missing required columns in MOEX futures response")
                return {}
            
            for row in rows:
                ticker = row[secid_idx]
                if ticker in tickers:
                    minstep = row[minstep_idx]
                    stepprice = row[stepprice_idx]
                    if minstep is not None and stepprice is not None:
                        specs[ticker] = {
                            'minstep': float(minstep),
                            'stepprice': float(stepprice)
                        }
        
        except Exception as e:
            log.warning(f"Error fetching MOEX futures specs: {e}")
        
        log.debug(f"Retrieved specs for {len(specs)} futures")
        return specs

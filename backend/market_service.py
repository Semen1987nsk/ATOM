import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
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
    def get_candles(
        self, 
        ticker: str, 
        start_date: datetime, 
        end_date: datetime,
        interval: int = 60  # 1 = 1min, 10 = 10min, 60 = 1hour, 24 = 1day
    ) -> List[Dict]:
        """
        Получает исторические свечи с MOEX ISS API.
        
        Args:
            ticker: Тикер инструмента (например, SBER, SiH6)
            start_date: Начало периода
            end_date: Конец периода
            interval: Интервал свечей (1, 10, 60, 24)
        
        Returns:
            Список словарей с данными свечей: {open, high, low, close, volume, begin, end}
        """
        candles = []
        
        # Определяем тип инструмента и соответствующий endpoint
        # Формат: /iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/candles.json
        
        endpoints = [
            # Акции (Main Board)
            f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json",
            # Фьючерсы
            f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities/{ticker}/candles.json",
            # Валюты
            f"https://iss.moex.com/iss/engines/currency/markets/selt/boards/CETS/securities/{ticker}/candles.json",
        ]
        
        # Форматируем даты для API
        from_date = start_date.strftime("%Y-%m-%d")
        to_date = end_date.strftime("%Y-%m-%d")
        
        for url in endpoints:
            try:
                # MOEX API поддерживает пагинацию, собираем все данные
                start = 0
                while True:
                    params = {
                        "from": from_date,
                        "till": to_date,
                        "interval": interval,
                        "start": start
                    }
                    
                    response = requests.get(url, params=params, timeout=10)
                    if response.status_code != 200:
                        break
                        
                    data = response.json()
                    
                    if 'candles' not in data or 'data' not in data['candles']:
                        break
                    
                    columns = data['candles']['columns']
                    rows = data['candles']['data']
                    
                    if not rows:
                        break
                    
                    # Парсим данные
                    try:
                        open_idx = columns.index('open')
                        high_idx = columns.index('high')
                        low_idx = columns.index('low')
                        close_idx = columns.index('close')
                        volume_idx = columns.index('volume')
                        begin_idx = columns.index('begin')
                        end_idx = columns.index('end')
                    except ValueError:
                        break
                    
                    for row in rows:
                        candle = {
                            'open': float(row[open_idx]) if row[open_idx] else None,
                            'high': float(row[high_idx]) if row[high_idx] else None,
                            'low': float(row[low_idx]) if row[low_idx] else None,
                            'close': float(row[close_idx]) if row[close_idx] else None,
                            'volume': float(row[volume_idx]) if row[volume_idx] else 0,
                            'begin': row[begin_idx],
                            'end': row[end_idx]
                        }
                        candles.append(candle)
                    
                    # Проверяем нужна ли следующая страница
                    if len(rows) < 500:  # MOEX возвращает макс 500 записей
                        break
                    start += 500
                
                # Если нашли свечи, выходим из цикла
                if candles:
                    log.debug(f"Retrieved {len(candles)} candles for {ticker} from {url}")
                    break
                    
            except Exception as e:
                log.warning(f"Error fetching candles for {ticker} from {url}: {e}")
                continue
        
        return candles

    def calculate_mae_mfe(
        self,
        ticker: str,
        direction: str,  # "LONG" or "SHORT"
        entry_price: float,
        entry_time: datetime,
        exit_time: datetime
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Рассчитывает MAE и MFE для сделки на основе исторических данных.
        
        MAE (Maximum Adverse Excursion) - худшая цена против позиции
        MFE (Maximum Favorable Excursion) - лучшая цена в пользу позиции
        
        Args:
            ticker: Тикер инструмента
            direction: Направление сделки ("LONG" или "SHORT")
            entry_price: Цена входа
            entry_time: Время входа
            exit_time: Время выхода
        
        Returns:
            Tuple (mae_price, mfe_price) или (None, None) если данные недоступны
        """
        # Расширяем период на 1 день для надёжности
        start_date = entry_time - timedelta(hours=1)
        end_date = exit_time + timedelta(hours=1)
        
        # Определяем интервал на основе длительности сделки
        duration_hours = (exit_time - entry_time).total_seconds() / 3600
        
        if duration_hours <= 2:
            interval = 1  # 1-минутные свечи для коротких сделок
        elif duration_hours <= 24:
            interval = 10  # 10-минутные для внутридневных
        elif duration_hours <= 24 * 7:
            interval = 60  # Часовые для недельных
        else:
            interval = 24  # Дневные для длинных
        
        # Получаем свечи
        candles = self.get_candles(ticker, start_date, end_date, interval)
        
        if not candles:
            log.warning(f"No candles found for {ticker} from {start_date} to {end_date}")
            return None, None
        
        # Фильтруем свечи только в период сделки
        relevant_candles = []
        entry_str = entry_time.strftime("%Y-%m-%d %H:%M")
        exit_str = exit_time.strftime("%Y-%m-%d %H:%M")
        
        for candle in candles:
            candle_begin = candle.get('begin', '')
            # Проверяем что свеча в пределах сделки
            if candle_begin and entry_str <= candle_begin <= exit_str:
                relevant_candles.append(candle)
        
        if not relevant_candles:
            # Если нет точного совпадения, используем все загруженные свечи
            log.debug(f"No candles in exact range, using all {len(candles)} candles")
            relevant_candles = candles
        
        if not relevant_candles:
            return None, None
        
        # Собираем все high и low
        all_highs = [c['high'] for c in relevant_candles if c['high'] is not None]
        all_lows = [c['low'] for c in relevant_candles if c['low'] is not None]
        
        if not all_highs or not all_lows:
            return None, None
        
        max_price = max(all_highs)
        min_price = min(all_lows)
        
        # Определяем MAE и MFE в зависимости от направления
        if direction.upper() == "LONG":
            # Для лонга: MAE = минимальная цена, MFE = максимальная цена
            mae_price = min_price
            mfe_price = max_price
        else:
            # Для шорта: MAE = максимальная цена, MFE = минимальная цена
            mae_price = max_price
            mfe_price = min_price
        
        log.info(f"Calculated MAE/MFE for {ticker} {direction}: MAE={mae_price}, MFE={mfe_price}, candles={len(relevant_candles)}")
        
        return mae_price, mfe_price
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
        exit_time: datetime,
        operations: list = None  # Список операций для усреднённых позиций
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Рассчитывает MAE и MFE для сделки на основе исторических данных.
        
        MAE (Maximum Adverse Excursion) - худшая цена против позиции
        MFE (Maximum Favorable Excursion) - лучшая цена в пользу позиции
        
        Для усреднённых позиций:
        - entry_price должна быть средневзвешенной ценой
        - MAE/MFE считаются от этой средней цены
        - Период берётся от первого входа до выхода
        
        Args:
            ticker: Тикер инструмента
            direction: Направление сделки ("LONG" или "SHORT")
            entry_price: Средневзвешенная цена входа (для усреднённых позиций)
            entry_time: Время первого входа
            exit_time: Время выхода
            operations: Опционально - список операций [{type, time, date, price, qty}, ...]
        
        Returns:
            Tuple (mae_price, mfe_price) или (None, None) если данные недоступны
        """
        # Определяем реальное время первого входа из операций если есть
        actual_entry_time = entry_time
        if operations:
            entry_ops = [op for op in operations if op.get('type') == 'entry']
            if entry_ops:
                # Находим самый ранний вход
                try:
                    first_entry = min(entry_ops, key=lambda x: self._parse_operation_datetime(x))
                    parsed_time = self._parse_operation_datetime(first_entry)
                    if parsed_time:
                        actual_entry_time = parsed_time
                        log.debug(f"Using first entry time from operations: {actual_entry_time}")
                except Exception as e:
                    log.warning(f"Failed to parse operation times: {e}")
        
        # Расширяем период на 1 час для надёжности
        start_date = actual_entry_time - timedelta(hours=1)
        end_date = exit_time + timedelta(hours=1)
        
        # Определяем интервал на основе длительности сделки
        duration_hours = (exit_time - actual_entry_time).total_seconds() / 3600
        
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
        entry_str = actual_entry_time.strftime("%Y-%m-%d %H:%M")
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
        
        # Логируем с информацией об усреднении
        avg_info = ""
        if operations and len([op for op in operations if op.get('type') == 'entry']) > 1:
            avg_info = f" (averaged, {len(operations)} ops)"
        
        log.info(f"Calculated MAE/MFE for {ticker} {direction}{avg_info}: "
                 f"avg_entry={entry_price:.2f}, MAE={mae_price}, MFE={mfe_price}, "
                 f"candles={len(relevant_candles)}")
        
        return mae_price, mfe_price
    
    def _parse_operation_datetime(self, op: dict) -> Optional[datetime]:
        """Парсит дату/время из операции"""
        try:
            date_str = op.get('date', '')
            time_str = op.get('time', '00:00:00')
            
            # Формат: "dd.mm.yyyy" или "yyyy-mm-dd"
            if '.' in date_str:
                dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            else:
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            return dt
        except Exception:
            return None

    def calculate_post_exit_analysis(
        self,
        ticker: str,
        direction: str,
        exit_price: float,
        exit_time: datetime,
        timeframe: str = None,
        periods_hours: list = None
    ) -> Dict:
        """
        Анализирует движение цены ПОСЛЕ закрытия сделки.
        
        Показывает:
        - Продолжила ли цена движение в вашу сторону (закрылись рано)
        - Развернулась ли цена (закрытие было правильным)
        
        Args:
            ticker: Тикер инструмента
            direction: Направление сделки ("LONG" или "SHORT")
            exit_price: Цена выхода
            exit_time: Время выхода
            timeframe: Таймфрейм торговли (1m, 5m, 15m, 1H, 4H, 1D, 1W)
            periods_hours: Периоды анализа в часах (если не указано — выбирается по таймфрейму)
        
        Returns:
            Dict с анализом по каждому периоду
        """
        # Выбираем периоды в зависимости от таймфрейма торговли
        if periods_hours is None:
            periods_hours = self._get_post_exit_periods(timeframe)
        
        result = {
            "exit_price": exit_price,
            "exit_time": exit_time.isoformat() if exit_time else None,
            "direction": direction,
            "timeframe": timeframe,
            "periods": {}
        }
        
        for hours in periods_hours:
            period_end = exit_time + timedelta(hours=hours)
            
            # Определяем интервал свечей
            if hours <= 4:
                interval = 10  # 10-минутные
            elif hours <= 24:
                interval = 60  # Часовые
            else:
                interval = 24  # Дневные
            
            candles = self.get_candles(ticker, exit_time, period_end, interval)
            
            if not candles:
                result["periods"][f"{hours}h"] = {
                    "available": False,
                    "message": "Нет данных"
                }
                continue
            
            # Фильтруем только свечи после выхода
            exit_str = exit_time.strftime("%Y-%m-%d %H:%M")
            post_exit_candles = [c for c in candles if c.get('begin', '') > exit_str]
            
            if not post_exit_candles:
                post_exit_candles = candles
            
            all_highs = [c['high'] for c in post_exit_candles if c['high'] is not None]
            all_lows = [c['low'] for c in post_exit_candles if c['low'] is not None]
            all_closes = [c['close'] for c in post_exit_candles if c['close'] is not None]
            
            if not all_highs or not all_lows or not all_closes:
                result["periods"][f"{hours}h"] = {
                    "available": False,
                    "message": "Нет данных"
                }
                continue
            
            max_price = max(all_highs)
            min_price = min(all_lows)
            final_price = all_closes[-1]  # Последняя цена закрытия
            
            # Анализ для LONG
            if direction.upper() == "LONG":
                # Для лонга: если цена выросла после выхода — закрылись рано
                continuation_price = max_price  # Максимальная цена после выхода
                continuation_move = (max_price - exit_price) / exit_price * 100
                final_move = (final_price - exit_price) / exit_price * 100
                
                if continuation_move > 1:  # Цена выросла больше чем на 1%
                    exit_quality = "early"  # Закрылись рано
                    quality_score = max(0, 100 - continuation_move * 10)  # Чем больше рост, тем хуже
                elif final_move < -1:  # Цена упала больше чем на 1%
                    exit_quality = "good"  # Правильное закрытие
                    quality_score = min(100, 70 + abs(final_move) * 5)
                else:
                    exit_quality = "neutral"
                    quality_score = 70
            else:
                # Для шорта: если цена упала после выхода — закрылись рано
                continuation_price = min_price
                continuation_move = (exit_price - min_price) / exit_price * 100
                final_move = (exit_price - final_price) / exit_price * 100
                
                if continuation_move > 1:
                    exit_quality = "early"
                    quality_score = max(0, 100 - continuation_move * 10)
                elif final_move < -1:
                    exit_quality = "good"
                    quality_score = min(100, 70 + abs(final_move) * 5)
                else:
                    exit_quality = "neutral"
                    quality_score = 70
            
            period_label = self._format_period_label(hours)
            
            result["periods"][f"{hours}h"] = {
                "available": True,
                "label": period_label,
                "max_price": max_price,
                "min_price": min_price,
                "final_price": final_price,
                "continuation_price": continuation_price,
                "continuation_move_pct": round(continuation_move, 2),
                "final_move_pct": round(final_move, 2),
                "exit_quality": exit_quality,
                "quality_score": round(quality_score, 0),
                "candles_count": len(post_exit_candles),
                "message": self._get_exit_quality_message(exit_quality, continuation_move, direction)
            }
        
        # Общая оценка качества выхода
        available_periods = [p for p in result["periods"].values() if p.get("available")]
        if available_periods:
            avg_score = sum(p["quality_score"] for p in available_periods) / len(available_periods)
            early_count = sum(1 for p in available_periods if p["exit_quality"] == "early")
            
            result["summary"] = {
                "avg_quality_score": round(avg_score, 0),
                "early_exits_count": early_count,
                "total_periods": len(available_periods),
                "overall_rating": self._get_overall_exit_rating(avg_score, early_count)
            }
        
        return result
    
    def _format_period_label(self, hours: float) -> str:
        """Форматирует метку периода"""
        if hours < 1:
            minutes = int(hours * 60)
            return f"{minutes} мин"
        elif hours < 24:
            return f"{int(hours)} ч"
        elif hours < 168:
            days = hours / 24
            if days == int(days):
                return f"{int(days)} дн"
            return f"{days:.1f} дн"
        elif hours < 720:
            weeks = hours / 168
            if weeks == int(weeks):
                return f"{int(weeks)} нед"
            return f"{weeks:.1f} нед"
        elif hours < 8760:
            months = hours / 720
            if months == int(months):
                return f"{int(months)} мес"
            return f"{months:.1f} мес"
        else:
            years = hours / 8760
            return f"{years:.1f} г"
    
    def _get_exit_quality_message(self, quality: str, move_pct: float, direction: str) -> str:
        """Генерирует сообщение о качестве выхода"""
        dir_text = "выросла" if direction.upper() == "LONG" else "упала"
        
        if quality == "early":
            return f"Цена {dir_text} на {abs(move_pct):.1f}% — закрылись рано"
        elif quality == "good":
            return f"Цена развернулась — закрытие было правильным"
        else:
            return f"Цена осталась примерно на месте"
    
    def _get_overall_exit_rating(self, avg_score: float, early_count: int) -> str:
        """Общая оценка качества выходов"""
        if avg_score >= 80 and early_count == 0:
            return "Отличное время выхода"
        elif avg_score >= 60:
            return "Хорошее время выхода"
        elif early_count >= 2:
            return "Тенденция к раннему закрытию"
        else:
            return "Требует внимания"
    
    def _get_post_exit_periods(self, timeframe: str = None) -> list:
        """
        Определяет периоды post-exit анализа в зависимости от таймфрейма торговли.
        
        Логика:
        - Скальпинг (1m-5m): смотрим 15мин, 1ч, 4ч
        - Интрадей (15m): смотрим 1ч, 4ч, 1д
        - Свинг (1H): смотрим 4ч, 1д, 1н
        - Позиционный (4H): смотрим 1д, 1н, 1м
        - Дневной (1D): смотрим 1н, 1м, 3м
        - Недельный (1W): смотрим 1м, 3м, 6м
        
        Args:
            timeframe: Таймфрейм в формате 1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W
        
        Returns:
            Список периодов в часах
        """
        if not timeframe:
            # По умолчанию — универсальные периоды
            return [1, 4, 24, 168]  # 1ч, 4ч, 1д, 1н
        
        tf = timeframe.upper().strip()
        
        # Скальпинг: 1-5 минутные графики
        if tf in ['1M', '1MIN', '2M', '3M', '5M', '5MIN']:
            return [0.25, 1, 4]  # 15мин, 1ч, 4ч
        
        # Интрадей: 15-30 минутные графики
        elif tf in ['15M', '15MIN', '30M', '30MIN']:
            return [1, 4, 24]  # 1ч, 4ч, 1д
        
        # Свинг: часовые графики
        elif tf in ['1H', '60M', '60MIN', 'H1']:
            return [4, 24, 168]  # 4ч, 1д, 1н
        
        # Позиционный: 4-часовые графики
        elif tf in ['4H', '240M', 'H4']:
            return [24, 168, 720]  # 1д, 1н, 1м (30 дней)
        
        # Дневной: дневные графики
        elif tf in ['1D', 'D1', 'D', 'DAILY']:
            return [168, 720, 2160]  # 1н, 1м, 3м (90 дней)
        
        # Недельный: недельные графики
        elif tf in ['1W', 'W1', 'W', 'WEEKLY']:
            return [720, 2160, 4320]  # 1м, 3м, 6м (180 дней)
        
        # Месячный
        elif tf in ['1MN', 'MN', 'MONTHLY']:
            return [2160, 4320, 8760]  # 3м, 6м, 1г (365 дней)
        
        else:
            # Неизвестный таймфрейм — универсальные периоды
            log.debug(f"Unknown timeframe '{timeframe}', using default periods")
            return [1, 4, 24, 168]
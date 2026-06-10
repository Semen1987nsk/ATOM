import re
import threading
import time as _time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, time
from logger import get_logger
from services import moex_async
import pytz

log = get_logger("market")

# Московская временная зона
MSK_TZ = pytz.timezone('Europe/Moscow')

# SEC-13: allowlist тикера перед подстановкой в MOEX URL.
# Допустимы буквы/цифры/.-_, длина ≤20 — покрывает акции (SBER), фьючерсы
# (SiH6, BRZ5), облигации (RU000A...), валюты (USD000UTSTOM). Отсекает path-injection.
_TICKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")


# ═══════════════════════════════════════════════════
#  Простой TTL-кэш (thread-safe)
# ═══════════════════════════════════════════════════

class _TTLCache:
    """Примитивный кэш с временем жизни записей (thread-safe)."""

    def __init__(self, default_ttl: float = 30.0):
        self._store: Dict[str, Tuple[float, object]] = {}  # key -> (expires_at, value)
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str):
        """Возвращает значение или None, если устарело / отсутствует."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if _time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value, ttl: float | None = None):
        with self._lock:
            self._store[key] = (_time.monotonic() + (ttl or self._default_ttl), value)

    def clear(self):
        with self._lock:
            self._store.clear()


# Глобальный кэш цен — TTL 30 секунд
_price_cache = _TTLCache(default_ttl=30.0)
# Глобальный кэш спецификаций фьючерсов — TTL 300 секунд (меняются редко)
_specs_cache = _TTLCache(default_ttl=300.0)

# ═══════════════════════════════════════════════════
#  MOEX HTTP — делегируется services/moex_async (PERF-04)
# ═══════════════════════════════════════════════════

# Прежде здесь жил sync requests.get + _backoff_with_jitter + _MOEX_MAX_RETRIES.
# После PERF-04 retry/backoff/jitter сосредоточены в services/moex_async.fetch_json
# (exponential + jitter), а старая sync-обвязка удалена.


async def _moex_get(url: str, timeout: float = 5) -> Optional[dict]:
    """GET MOEX ISS через общий httpx.AsyncClient (PERF-04).

    Прежде здесь была sync requests.get с собственным retry+jitter. Теперь
    делегируем общему async-singleton services/moex_async.fetch_json, который
    несёт shared connection pool и async retry — это разблокирует event-loop
    под /market/* эндпойнтами.

    `timeout` параметр оставлен для обратной совместимости сигнатуры (старые
    вызовы передавали 5/10), но игнорируется: timeout задаётся глобально на
    AsyncClient в moex_async._DEFAULT_TIMEOUT.
    """
    return await moex_async.fetch_json(url)


# ═══════════════════════════════════════════════════
#  ISS column-oriented JSON parser (центральная точка)
# ═══════════════════════════════════════════════════

def _normalize_iss_block(data: dict, block: str) -> List[Dict]:
    """
    ISS возвращает блоки в column-oriented формате:
        {"securities": {"columns": ["SECID", "LAST"], "data": [["SBER", 250.1], ...]}}

    Эта функция превращает их в row-oriented [{"SECID": "SBER", "LAST": 250.1}, ...].

    Возвращает [] если блок отсутствует, columns/data битые или data пустой —
    вызывающий не должен делать дополнительных проверок.

    Используется для marketdata, securities, candles. Один источник истины
    вместо 4 копий парсера в этом файле.
    """
    if not data or not isinstance(data, dict):
        return []
    section = data.get(block)
    if not isinstance(section, dict):
        return []

    columns = section.get("columns")
    rows = section.get("data")
    if not columns or not isinstance(columns, list) or not isinstance(rows, list):
        return []

    return [dict(zip(columns, row)) for row in rows if isinstance(row, list) and len(row) == len(columns)]


# Праздники MOEX 2025-2026 (торги не проводятся)
MOEX_HOLIDAYS = {
    # 2025
    datetime(2025, 1, 1).date(),
    datetime(2025, 1, 2).date(),
    datetime(2025, 1, 3).date(),
    datetime(2025, 1, 6).date(),
    datetime(2025, 1, 7).date(),
    datetime(2025, 1, 8).date(),
    datetime(2025, 2, 24).date(),  # День защитника отечества (перенос)
    datetime(2025, 3, 10).date(),  # 8 марта (перенос)
    datetime(2025, 5, 1).date(),
    datetime(2025, 5, 2).date(),
    datetime(2025, 5, 9).date(),
    datetime(2025, 6, 12).date(),
    datetime(2025, 6, 13).date(),
    datetime(2025, 11, 3).date(),  # День народного единства (перенос)
    datetime(2025, 12, 31).date(),
    # 2026
    datetime(2026, 1, 1).date(),
    datetime(2026, 1, 2).date(),
    datetime(2026, 1, 5).date(),
    datetime(2026, 1, 6).date(),
    datetime(2026, 1, 7).date(),
    datetime(2026, 1, 8).date(),
    datetime(2026, 2, 23).date(),
    datetime(2026, 3, 9).date(),
    datetime(2026, 5, 1).date(),
    datetime(2026, 5, 11).date(),
    datetime(2026, 6, 12).date(),
    datetime(2026, 11, 4).date(),
}

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

    def _to_msk(self, dt: datetime) -> datetime:
        """
        Нормализует datetime к часовому поясу биржи (MSK).

        MAE-01: naive datetime трактуем как UTC — это конвенция хранения
        в БД (trade_repo/import_service пишут UTC-naive). Прежняя трактовка
        naive=МСК сдвигала окно фильтра свечей на −3 часа для всех путей,
        читающих сделку из БД (bulk-пересчёт, import-hook, nightly backfill),
        и расходилась с calculate_post_exit_analysis, который всегда
        конвертировал naive как UTC.
        """
        if dt.tzinfo is None:
            return pytz.utc.localize(dt).astimezone(MSK_TZ)
        return dt.astimezone(MSK_TZ)

    async def get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetches current prices from MOEX ISS (Stocks, Futures, Currencies).
        Returns a dictionary {ticker: price}.
        Uses a 30-second TTL cache to avoid hammering MOEX on every request.

        PERF-04: метод async; sync TTL-кэш сохраняется как был (thread-safe
        Lock — он не тормозит event-loop, операции O(1)).
        """
        if not tickers:
            return {}

        prices: Dict[str, float] = {}
        missing: List[str] = []

        # Check cache first
        for t in tickers:
            cached = _price_cache.get(f"price:{t}")
            if cached is not None:
                prices[t] = cached
            else:
                missing.append(t)

        if not missing:
            return prices

        log.debug(f"Fetching prices for {len(missing)} tickers (cache miss): {missing}")

        for url in self.sources:
            try:
                data = await _moex_get(url)
                for entry in _normalize_iss_block(data, "marketdata"):
                    ticker = entry.get("SECID")
                    price = entry.get("LAST")
                    if price is not None and ticker in missing:
                        price_f = float(price)
                        prices[ticker] = price_f
                        _price_cache.set(f"price:{ticker}", price_f)

            except Exception as e:
                log.warning(f"Error fetching MOEX data from {url}: {e}")
                continue

        log.debug(f"Retrieved {len(prices)} prices")
        return prices

    async def get_futures_specs(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Fetches futures specifications (MINSTEP, STEPPRICE) from MOEX.
        Returns a dictionary {ticker: {minstep: float, stepprice: float}}.
        Uses a 5-minute TTL cache (specs change rarely).

        PERF-04: метод async — вызывается из async /market/futures-specs.
        """
        if not tickers:
            return {}

        specs: Dict[str, Dict] = {}
        missing: List[str] = []

        for t in tickers:
            cached = _specs_cache.get(f"spec:{t}")
            if cached is not None:
                specs[t] = cached
            else:
                missing.append(t)

        if not missing:
            return specs

        url = "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities.json"

        try:
            data = await _moex_get(url)
            for entry in _normalize_iss_block(data, "securities"):
                ticker = entry.get("SECID")
                if ticker not in missing:
                    continue
                minstep = entry.get("MINSTEP")
                stepprice = entry.get("STEPPRICE")
                if minstep is not None and stepprice is not None:
                    spec = {
                        'minstep': float(minstep),
                        'stepprice': float(stepprice),
                    }
                    specs[ticker] = spec
                    _specs_cache.set(f"spec:{ticker}", spec)

        except Exception as e:
            log.warning(f"Error fetching MOEX futures specs: {e}")

        log.debug(f"Retrieved specs for {len(specs)} futures")
        return specs
    
    def is_trading_day(self, date: datetime) -> bool:
        """Проверяет, является ли дата торговым днём MOEX"""
        # Конвертируем в MSK для корректной проверки даты
        if isinstance(date, datetime):
            date_msk = self._to_msk(date)
            d = date_msk.date()
        else:
            d = date
        # Выходные
        if d.weekday() >= 5:  # Суббота=5, Воскресенье=6
            return False
        # Праздники
        if d in MOEX_HOLIDAYS:
            return False
        return True
    
    def is_trading_hours(self, dt: datetime, is_futures: bool = False) -> bool:
        """
        Проверяет, попадает ли время в торговую сессию MOEX.
        
        Основная сессия (акции): 10:00 - 18:45 MSK
        Вечерняя сессия (только фьючерсы): 19:05 - 23:50 MSK
        """
        if not self.is_trading_day(dt):
            return False
        
        dt_msk = self._to_msk(dt)
        
        t = dt_msk.time()
        
        # Основная сессия: 10:00 - 18:45
        main_session = time(10, 0) <= t <= time(18, 45)
        
        if is_futures:
            # Вечерняя сессия: 19:05 - 23:50
            evening_session = time(19, 5) <= t <= time(23, 50)
            return main_session or evening_session
        
        return main_session
    
    def get_next_trading_time(self, dt: datetime) -> datetime:
        """Возвращает ближайшее торговое время после указанного момента"""
        current = dt
        
        # Максимум 14 дней вперёд (на случай новогодних праздников)
        for _ in range(14 * 24):  # 14 дней в часах
            if self.is_trading_day(current):
                current_msk = self._to_msk(current)
                
                t = current_msk.time()
                
                # Если до начала торгов - ждём 10:00
                if t < time(10, 0):
                    return current_msk.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # Если в торговые часы - возвращаем как есть
                if time(10, 0) <= t <= time(18, 45):
                    return current_msk
                
                # Если после торгов - переходим на следующий день
                current = current + timedelta(days=1)
                current = current.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                current = current + timedelta(days=1)
                current = current.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return dt  # Fallback

    def count_trading_hours(self, start_dt: datetime, end_dt: datetime) -> float:
        """Считает количество торговых часов между двумя датами"""
        if start_dt >= end_dt:
            return 0
        
        trading_hours = 0
        current = start_dt
        
        while current < end_dt:
            if self.is_trading_hours(current):
                trading_hours += 1
            current = current + timedelta(hours=1)
        
        return trading_hours
    
    async def get_candles(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        interval: int = 60  # 1 = 1min, 10 = 10min, 60 = 1hour, 24 = 1day
    ) -> List[Dict]:
        """
        Получает исторические свечи с MOEX ISS API.

        PERF-04: async — вызывается из async-роутов /trades/* через
        calculate_mae_mfe / calculate_post_exit_analysis. Под массовыми bulk
        пересчётами (50-500 сделок) sync requests.get блокировал event-loop
        под FastAPI worker'ом; теперь все HTTP идут через общий
        services/moex_async.fetch_json (httpx.AsyncClient + exponential
        retry/backoff с jitter).

        Args:
            ticker: Тикер инструмента (например, SBER, SiH6)
            start_date: Начало периода
            end_date: Конец периода
            interval: Интервал свечей (1, 10, 60, 24)

        Returns:
            Список словарей с данными свечей: {open, high, low, close, volume, begin, end}
        """
        if not _TICKER_RE.match(ticker or ""):
            log.warning("get_candles: invalid ticker rejected")
            return []

        candles = []

        # Определяем тип инструмента и соответствующий endpoint.
        # Формат: /iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/candles.json
        #
        # Порядок важен: первый endpoint, вернувший непустые свечи — победил
        # (см. цикл ниже с break). Поэтому акции на TQBR проверяем раньше,
        # чем ОФЗ — частотный случай должен быть первым.
        endpoints = [
            # Акции — Main Board (T+: расчёты)
            f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json",
            # ОФЗ (государственные облигации)
            f"https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQOB/securities/{ticker}/candles.json",
            # Корпоративные облигации
            f"https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/securities/{ticker}/candles.json",
            # ETF (биржевые фонды)
            f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQTF/securities/{ticker}/candles.json",
            # Фьючерсы FORTS
            f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities/{ticker}/candles.json",
            # Валюты selt CETS
            f"https://iss.moex.com/iss/engines/currency/markets/selt/boards/CETS/securities/{ticker}/candles.json",
        ]

        # Форматируем даты для API
        from_date = start_date.strftime("%Y-%m-%d")
        to_date = end_date.strftime("%Y-%m-%d")

        for url in endpoints:
            try:
                # MOEX API поддерживает пагинацию, собираем все данные.
                # Ретраи/таймауты/backoff — внутри moex_async.fetch_json.
                start = 0
                while True:
                    params = {
                        "from": from_date,
                        "till": to_date,
                        "interval": interval,
                        "start": start,
                    }

                    data = await moex_async.fetch_json(url, params=params)
                    if data is None:
                        # Сеть/HTTP-ошибка после retry'ев — пробуем следующий endpoint
                        break

                    rows = _normalize_iss_block(data, "candles")
                    if not rows:
                        break

                    for row in rows:
                        candle = {
                            'open': float(row['open']) if row.get('open') is not None else None,
                            'high': float(row['high']) if row.get('high') is not None else None,
                            'low': float(row['low']) if row.get('low') is not None else None,
                            'close': float(row['close']) if row.get('close') is not None else None,
                            'volume': float(row['volume']) if row.get('volume') is not None else 0,
                            'begin': row.get('begin'),
                            'end': row.get('end'),
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

    async def calculate_mae_mfe(
        self,
        ticker: str,
        direction: str,  # "LONG" or "SHORT"
        entry_price: float,
        entry_time: datetime,
        exit_time: datetime,
        operations: list = None,  # Список операций для усреднённых позиций
        exit_price: float = None  # Цена выхода для гарантии корректности MAE/MFE
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
        
        # Приводим время сделки к часовому поясу биржи.
        # Для naive datetime считаем, что время уже задано в локальном времени MOEX.
        entry_msk = self._to_msk(actual_entry_time)
        exit_msk = self._to_msk(exit_time)
        
        # Расширяем период на 1 час для надёжности (уже в MSK)
        start_date = entry_msk - timedelta(hours=1)
        end_date = exit_msk + timedelta(hours=1)
        
        log.debug(f"MAE/MFE period: entry={actual_entry_time} -> MSK={entry_msk}")
        log.debug(f"MAE/MFE period: exit={exit_time} -> MSK={exit_msk}")
        log.debug(f"Fetching candles from {start_date} to {end_date}")
        
        # Определяем интервал на основе длительности сделки
        duration_hours = (exit_msk - entry_msk).total_seconds() / 3600
        
        if duration_hours <= 2:
            interval = 1  # 1-минутные свечи для коротких сделок
        elif duration_hours <= 24:
            interval = 10  # 10-минутные для внутридневных
        elif duration_hours <= 24 * 7:
            interval = 60  # Часовые для недельных
        else:
            interval = 24  # Дневные для длинных
        
        # Получаем свечи (даты уже в MSK)
        candles = await self.get_candles(ticker, start_date, end_date, interval)
        
        if not candles:
            log.warning(f"No candles found for {ticker} from {start_date} to {end_date}")
            return None, None
        
        # Фильтруем свечи только в период сделки (entry_msk и exit_msk уже сконвертированы выше)
        relevant_candles = []
        
        # Используем формат с секундами для точного сравнения
        entry_str = entry_msk.strftime("%Y-%m-%d %H:%M:%S")
        exit_str = exit_msk.strftime("%Y-%m-%d %H:%M:%S")
        
        log.debug(f"Filtering candles in range: {entry_str} to {exit_str}")
        
        for candle in candles:
            candle_begin = candle.get('begin', '')
            candle_end = candle.get('end', '')
            
            # ВАЖНО: Свеча включается ТОЛЬКО если она ПОЛНОСТЬЮ внутри периода сделки
            # begin >= entry AND end <= exit
            # Это предотвращает включение свечей, чьи HIGH/LOW могли быть достигнуты
            # после выхода из сделки
            if candle_begin and candle_end:
                # Нормализуем форматы (добавляем :00 если нет секунд)
                if len(candle_begin) == 16:  # "YYYY-MM-DD HH:MM"
                    candle_begin += ":00"
                if len(candle_end) == 16:
                    candle_end += ":59"
                    
                if entry_str <= candle_begin and candle_end <= exit_str:
                    relevant_candles.append(candle)
        
        if not relevant_candles and interval > 1:
            # Если нет свечей в точном диапазоне, пробуем с 1-минутными для точности
            log.debug(f"No candles in exact range with interval={interval}, trying 1-minute candles")
            candles_1m = await self.get_candles(ticker, start_date, end_date, interval=1)
            
            for candle in candles_1m:
                candle_begin = candle.get('begin', '')
                candle_end = candle.get('end', '')
                
                if candle_begin and candle_end:
                    if len(candle_begin) == 16:
                        candle_begin += ":00"
                    if len(candle_end) == 16:
                        candle_end += ":59"
                        
                    if entry_str <= candle_begin and candle_end <= exit_str:
                        relevant_candles.append(candle)
            
            log.debug(f"Found {len(relevant_candles)} 1-minute candles in range")
        
        if not relevant_candles:
            log.warning(f"No candles found for {ticker} in trade period {entry_str} to {exit_str}")
            return None, None
        
        # Собираем все high и low
        all_highs = [c['high'] for c in relevant_candles if c['high'] is not None]
        all_lows = [c['low'] for c in relevant_candles if c['low'] is not None]
        
        if not all_highs or not all_lows:
            return None, None
        
        max_price = max(all_highs)
        min_price = min(all_lows)
        
        # ВАЖНО: Учитываем цену выхода!
        # Цена выхода гарантированно была достигнута, поэтому MAE/MFE должны её учитывать
        if exit_price is not None:
            if exit_price > max_price:
                max_price = exit_price
                log.debug(f"Adjusted max_price to exit_price: {exit_price}")
            if exit_price < min_price:
                min_price = exit_price
                log.debug(f"Adjusted min_price to exit_price: {exit_price}")
        
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
            # Приоритет 1: ISO формат в поле 'time' (например "2026-01-19T08:14:29.518Z")
            time_field = op.get('time', '')
            if time_field and 'T' in time_field:
                # ISO формат: "2026-01-19T08:14:29.518Z" или "2026-01-19T08:14:29"
                time_field = time_field.replace('Z', '+00:00')
                if '.' in time_field:
                    # С миллисекундами
                    dt = datetime.fromisoformat(time_field.replace('+00:00', ''))
                else:
                    dt = datetime.fromisoformat(time_field.replace('+00:00', ''))
                return dt
            
            # Приоритет 2: Отдельные поля date и time
            date_str = op.get('date', '')
            time_str = op.get('time', '00:00:00')
            
            if not date_str:
                return None
            
            # Формат: "dd.mm.yyyy" или "yyyy-mm-dd"
            if '.' in date_str:
                dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            else:
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            return dt
        except Exception as e:
            log.debug(f"Failed to parse operation datetime: {op}, error: {e}")
            return None

    async def calculate_post_exit_analysis(
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
        # ===== ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ =====
        if not exit_price or exit_price <= 0:
            log.warning(f"Invalid exit_price for {ticker}: {exit_price}")
            return {"error": "Invalid exit_price", "periods": {}}
        
        if not exit_time:
            log.warning(f"Missing exit_time for {ticker}")
            return {"error": "Missing exit_time", "periods": {}}
        
        if not direction or direction.upper() not in ("LONG", "SHORT"):
            log.warning(f"Invalid direction for {ticker}: {direction}")
            return {"error": "Invalid direction", "periods": {}}
        
        # Нормализуем direction
        direction = direction.upper()
        
        # Выбираем периоды в зависимости от таймфрейма торговли
        if periods_hours is None:
            periods_hours = self._get_post_exit_periods(timeframe)
        
        result = {
            "exit_price": exit_price,
            "exit_time": exit_time.isoformat() if exit_time else None,
            "direction": direction,
            "timeframe": timeframe,
            "periods": {},
            "warnings": []
        }
        
        # ===== ПРОВЕРКА ТОРГОВЫХ СЕССИЙ =====
        if not self.is_trading_day(exit_time):
            result["warnings"].append("Выход в нерабочий день - данные могут быть неточными")
        
        # Конвертируем exit_time в MSK для корректного сравнения со свечами
        # ВАЖНО: Время сделок в UTC, свечи MOEX в MSK
        if exit_time.tzinfo is None:
            exit_utc = pytz.utc.localize(exit_time)
        else:
            exit_utc = exit_time.astimezone(pytz.utc)
        exit_msk = exit_utc.astimezone(MSK_TZ)
        
        for hours in periods_hours:
            # Рассчитываем реальное торговое время с учётом выходных/праздников
            period_end = exit_time + timedelta(hours=hours)
            period_end_msk = exit_msk + timedelta(hours=hours)
            
            # Проверяем, сколько торговых часов в периоде
            trading_hours = self.count_trading_hours(exit_time, period_end)
            if trading_hours < hours * 0.3:  # Менее 30% торгового времени
                result["periods"][f"{hours}h"] = {
                    "available": False,
                    "message": f"Период попадает на нерабочие дни ({trading_hours:.0f}ч торгов из {hours}ч)",
                    "trading_hours": trading_hours,
                    "requested_hours": hours
                }
                continue
            
            # Определяем интервал свечей
            if hours <= 4:
                interval = 10  # 10-минутные
            elif hours <= 24:
                interval = 60  # Часовые
            else:
                interval = 24  # Дневные
            
            # Используем MSK время для запроса и фильтрации свечей
            candles = await self.get_candles(ticker, exit_msk, period_end_msk, interval)
            
            if not candles:
                result["periods"][f"{hours}h"] = {
                    "available": False,
                    "message": "Нет данных"
                }
                continue
            
            # Фильтруем только свечи после выхода (используем MSK)
            exit_str = exit_msk.strftime("%Y-%m-%d %H:%M")
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
            
            # ===== АДАПТИВНЫЙ ПОРОГ на основе волатильности =====
            # Рассчитываем среднюю волатильность в периоде
            if len(post_exit_candles) >= 2:
                price_changes = []
                for c in post_exit_candles:
                    if c.get('high') and c.get('low') and c.get('close'):
                        range_pct = (c['high'] - c['low']) / c['close'] * 100
                        price_changes.append(range_pct)
                avg_volatility = sum(price_changes) / len(price_changes) if price_changes else 1.0
                # Порог = 0.5 * средняя волатильность, но не менее 0.5% и не более 3%
                significance_threshold = max(0.5, min(3.0, avg_volatility * 0.5))
            else:
                significance_threshold = 1.0  # По умолчанию 1%
            
            # Анализ для LONG
            if direction == "LONG":
                # Для лонга: если цена выросла после выхода — закрылись рано
                continuation_price = max_price  # Максимальная цена после выхода
                continuation_move = (max_price - exit_price) / exit_price * 100
                final_move = (final_price - exit_price) / exit_price * 100
                
                if continuation_move > significance_threshold:  # Цена выросла значительно
                    exit_quality = "early"  # Закрылись рано
                    quality_score = max(0, 100 - continuation_move * 10)  # Чем больше рост, тем хуже
                elif final_move < -significance_threshold:  # Цена упала значительно
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
                
                if continuation_move > significance_threshold:
                    exit_quality = "early"
                    quality_score = max(0, 100 - continuation_move * 10)
                elif final_move < -significance_threshold:
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
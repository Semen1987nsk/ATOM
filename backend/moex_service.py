"""
MOEX ISS API Service
Получение спецификаций инструментов с Московской биржи

Бесплатный API без авторизации!
Документация: https://iss.moex.com/iss/reference/
"""

import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from functools import lru_cache

logger = logging.getLogger(__name__)

MOEX_ISS_BASE = "https://iss.moex.com/iss"

# Fallback спецификации для известных фьючерсов (ключи в ВЕРХНЕМ регистре!)
# Используются когда инструмент уже не торгуется на бирже
KNOWN_FUTURES_SPECS = {
    # Валютные
    "SI": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # USD/RUB
    "EU": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # EUR/RUB
    "CNY": {"minstep": Decimal("0.001"), "stepprice": Decimal(1), "point_value": Decimal(1000)},  # CNY/RUB
    
    # Индексные
    "MX": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # MOEX Index
    "RI": {"minstep": Decimal(10), "stepprice": Decimal("15"), "point_value": Decimal("1.5")},  # RTS Index (примерно)
    "RTS": {"minstep": Decimal(5), "stepprice": Decimal("7.5"), "point_value": Decimal("1.5")},  # Mini-RTS
    
    # Товарные
    "BR": {"minstep": Decimal("0.01"), "stepprice": Decimal(10), "point_value": Decimal(1000)},  # Brent Oil
    "GD": {"minstep": Decimal("0.1"), "stepprice": Decimal(10), "point_value": Decimal(100)},  # Gold
    "NG": {"minstep": Decimal("0.001"), "stepprice": Decimal(10), "point_value": Decimal(10000)},  # Natural Gas
    
    # Акционные фьючерсы
    "SR": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # Sberbank
    "GZ": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # Gazprom
    "LK": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # Lukoil
    "VB": {"minstep": Decimal("0.000001"), "stepprice": Decimal(1), "point_value": Decimal(1000000)},  # VTB
    "GM": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},  # Norilsk Nickel
    
    # Иностранные акции
    "BB": {"minstep": Decimal("0.01"), "stepprice": Decimal(10), "point_value": Decimal(1000)},  # Alibaba
    "AL": {"minstep": Decimal("0.01"), "stepprice": Decimal(10), "point_value": Decimal(1000)},  # Alcoa
    
    # ADR на российские акции
    "SB": {"minstep": Decimal("0.01"), "stepprice": Decimal(10), "point_value": Decimal(1000)},  # Sberbank ADR
    "DX": {"minstep": Decimal("0.01"), "stepprice": Decimal(10), "point_value": Decimal(1000)},  # Dollar Index
    "XI": {"minstep": Decimal("0.01"), "stepprice": Decimal(10), "point_value": Decimal(1000)},  # Xi (unknown base)
}


class MoexService:
    """Сервис для работы с MOEX ISS API"""
    
    def __init__(self):
        self._specs_cache: Dict[str, Dict] = {}
    
    def get_futures_spec(self, ticker: str) -> Optional[Dict]:
        """
        Получение спецификации фьючерса с MOEX ISS API.
        
        Args:
            ticker: Тикер фьючерса (например, SiH5, BBZ4, RIM5)
            
        Returns:
            Dict с полями:
            - ticker: str
            - minstep: Decimal (минимальный шаг цены)
            - stepprice: Decimal (стоимость шага в рублях)
            - point_value: Decimal (= stepprice / minstep)
            - lotsize: int
            - assetcode: str (базовый актив)
            - lasttradedate: str
        """
        # Проверяем кэш
        if ticker in self._specs_cache:
            return self._specs_cache[ticker]
        
        try:
            url = f"{MOEX_ISS_BASE}/engines/futures/markets/forts/securities/{ticker}.json"
            params = {
                "iss.meta": "off",
                "iss.only": "securities"
            }
            
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.warning(f"MOEX API error for {ticker}: {response.status_code}")
                    return None
                
                data = response.json()
            
            securities = data.get("securities", {})
            columns = securities.get("columns", [])
            rows = securities.get("data", [])
            
            if not rows:
                logger.warning(f"No data for futures {ticker}")
                return None
            
            # Преобразуем в словарь
            spec_raw = dict(zip(columns, rows[0]))
            
            minstep = Decimal(str(spec_raw.get("MINSTEP", 1) or 1))
            stepprice = Decimal(str(spec_raw.get("STEPPRICE", 1) or 1))
            
            # Рассчитываем point_value
            point_value = stepprice / minstep if minstep > 0 else Decimal(1)
            
            spec = {
                "ticker": spec_raw.get("SECID", ticker),
                "minstep": minstep,
                "stepprice": stepprice,
                "point_value": point_value,
                "lotsize": int(spec_raw.get("LOTSIZE", 1) or 1),
                "assetcode": spec_raw.get("ASSETCODE", ""),
                "lasttradedate": spec_raw.get("LASTTRADEDATE", ""),
                "shortname": spec_raw.get("SHORTNAME", ""),
            }
            
            # Кэшируем
            self._specs_cache[ticker] = spec
            
            logger.debug(f"Fetched MOEX spec for {ticker}: point_value={point_value}")
            
            return spec
            
        except Exception as e:
            logger.error(f"Error fetching MOEX spec for {ticker}: {e}")
            return None
    
    def get_point_value(self, ticker: str) -> Decimal:
        """
        Получить point_value для фьючерса.
        
        Сначала пробует MOEX ISS API, затем fallback на известные спецификации.
        
        Returns:
            point_value или Decimal(1) если не удалось получить
        """
        # Пробуем получить актуальные данные с биржи
        spec = self.get_futures_spec(ticker)
        if spec:
            return spec["point_value"]
        
        # Fallback на известные спецификации
        # Формат тикера: {BaseCode}{MonthCode}{YearDigit}
        # Примеры: SiH5 (base=Si), CNYH5 (base=CNY), RIM5 (base=RI)
        if len(ticker) >= 3:
            # Отбрасываем последние 2 символа (месяц + год)
            base_code = ticker[:-2].upper()
            
            # Пробуем точное совпадение
            if base_code in KNOWN_FUTURES_SPECS:
                logger.debug(f"Using fallback spec for {ticker} (base: {base_code})")
                return KNOWN_FUTURES_SPECS[base_code]["point_value"]
            
            # Пробуем первые 2 символа (Si, RI, BR, GZ, etc.)
            base_code_2 = ticker[:2].upper()
            if base_code_2 in KNOWN_FUTURES_SPECS:
                logger.debug(f"Using fallback spec for {ticker} (base: {base_code_2})")
                return KNOWN_FUTURES_SPECS[base_code_2]["point_value"]
        
        logger.warning(f"No point_value found for {ticker}, using 1")
        return Decimal(1)
    
    # ────────────────────────────────────────────────
    #  Candles (для Trade Replay)
    # ────────────────────────────────────────────────

    # Нормализация interval-строк фронта в коды MOEX ISS.
    # MOEX поддерживает: 1=1m, 10=10m, 60=1h, 24=1d, 7=1w, 31=1mo, 4=1q.
    _INTERVAL_MAP = {
        "1m": 1,
        "10m": 10,
        "1h": 60,
        "1d": 24,
        "1w": 7,
        "1mo": 31,
    }

    @staticmethod
    def normalize_interval(interval: str) -> int:
        """Принимает '1m'/'10m'/'1h'/'1d'/'1w'/'1mo' или сразу int-код. Кидает ValueError."""
        if isinstance(interval, int):
            return interval
        s = str(interval).strip().lower()
        if s in MoexService._INTERVAL_MAP:
            return MoexService._INTERVAL_MAP[s]
        if s.isdigit():
            return int(s)
        raise ValueError(f"Unknown candle interval: {interval}")

    @staticmethod
    def auto_interval(span: timedelta) -> str:
        """
        Авто-подбор разрешения свечей под длину окна,
        чтобы график не превращался в кашу/пустыню.
        """
        seconds = span.total_seconds()
        if seconds <= 6 * 3600:           # ≤ 6h  → 1-min
            return "1m"
        if seconds <= 3 * 86400:          # ≤ 3d  → 10-min
            return "10m"
        if seconds <= 30 * 86400:         # ≤ 30d → 1h
            return "1h"
        if seconds <= 365 * 86400:        # ≤ 1y  → 1d
            return "1d"
        return "1w"

    def get_candles(
        self,
        ticker: str,
        interval: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Свечи с MOEX ISS. Пробует stock/shares, затем futures/forts.

        Returns: list of {t (ISO), o, h, l, c, v}.
        Возвращает [] если данных нет (тикер не найден / нерабочие дни / выходной).
        """
        interval_code = self.normalize_interval(interval)

        # MOEX ISS принимает диапазон в формате YYYY-MM-DD HH:MM:SS.
        # Если start/end не заданы — последние 30 дней.
        if end is None:
            end = datetime.utcnow()
        if start is None:
            start = end - timedelta(days=30)
        params = {
            "iss.meta": "off",
            "iss.only": "candles",
            "interval": interval_code,
            "from": start.strftime("%Y-%m-%d %H:%M:%S"),
            "till": end.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Порядок попыток зависит от вида тикера — экономим один RTT.
        if self.is_futures_ticker(ticker):
            urls = [
                f"{MOEX_ISS_BASE}/engines/futures/markets/forts/securities/{ticker}/candles.json",
                f"{MOEX_ISS_BASE}/engines/stock/markets/shares/securities/{ticker}/candles.json",
            ]
        else:
            urls = [
                f"{MOEX_ISS_BASE}/engines/stock/markets/shares/securities/{ticker}/candles.json",
                f"{MOEX_ISS_BASE}/engines/futures/markets/forts/securities/{ticker}/candles.json",
            ]

        try:
            with httpx.Client(timeout=15.0) as client:
                for url in urls:
                    try:
                        resp = client.get(url, params=params)
                        if resp.status_code != 200:
                            continue
                        data = resp.json().get("candles", {})
                        cols = data.get("columns", [])
                        rows = data.get("data", [])
                        if not rows:
                            continue
                        # MOEX columns: ['open','close','high','low','value','volume','begin','end']
                        idx = {name: cols.index(name) for name in cols}
                        candles = []
                        for r in rows:
                            candles.append({
                                "t": r[idx["begin"]],
                                "o": r[idx["open"]],
                                "h": r[idx["high"]],
                                "l": r[idx["low"]],
                                "c": r[idx["close"]],
                                "v": r[idx["volume"]],
                            })
                        return candles
                    except httpx.RequestError as exc:
                        logger.warning(f"MOEX candles request failed for {ticker} via {url}: {exc}")
                        continue
        except Exception as exc:
            logger.error(f"Unexpected error fetching candles for {ticker}: {exc}")

        return []

    def is_futures_ticker(self, ticker: str) -> bool:
        """
        Определить, является ли тикер фьючерсом по формату.
        
        Формат фьючерсов MOEX: {BaseCode}{MonthCode}{YearDigit}
        Примеры: SiH5, RIM5, BRG5, BBZ4
        
        BaseCode: 2-3 буквы
        MonthCode: F,G,H,J,K,M,N,Q,U,V,X,Z
        YearDigit: 4,5,6,7,8,9,0,1,2,3
        """
        if not ticker or len(ticker) < 3:
            return False
        
        # Код месяца
        month_codes = "FGHJKMNQUVXZ"
        
        # Проверяем последний символ (год) - цифра
        if not ticker[-1].isdigit():
            return False
        
        # Проверяем предпоследний символ (месяц)
        if ticker[-2].upper() not in month_codes:
            return False
        
        # Первые символы - буквы (код актива)
        base = ticker[:-2]
        if not base.isalpha():
            return False
        
        return True


# Singleton instance
_moex_service = None


def get_moex_service() -> MoexService:
    """Получить singleton instance MoexService"""
    global _moex_service
    if _moex_service is None:
        _moex_service = MoexService()
    return _moex_service

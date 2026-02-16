"""
MOEX ISS API Service
Получение спецификаций инструментов с Московской биржи

Бесплатный API без авторизации!
Документация: https://iss.moex.com/iss/reference/
"""

import httpx
import logging
from typing import Dict, Optional
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

"""
Тесты Post-Exit Analysis — проверка edge cases

Покрывает сценарии:
1. Выходные дни / праздники MOEX
2. Невалидные входные данные
3. Пустые данные с API
4. Граничные случаи с ценами
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_service import MarketService, MOEX_HOLIDAYS


class TestMOEXTradingCalendar:
    """Тесты торгового календаря MOEX"""
    
    def setup_method(self):
        self.service = MarketService()
    
    def test_saturday_is_not_trading_day(self):
        """Суббота — не торговый день"""
        saturday = datetime(2026, 1, 10)  # Суббота
        assert saturday.weekday() == 5
        assert self.service.is_trading_day(saturday) == False
    
    def test_sunday_is_not_trading_day(self):
        """Воскресенье — не торговый день"""
        sunday = datetime(2026, 1, 11)  # Воскресенье
        assert sunday.weekday() == 6
        assert self.service.is_trading_day(sunday) == False
    
    def test_monday_is_trading_day(self):
        """Понедельник — торговый день (если не праздник)"""
        monday = datetime(2026, 1, 12)  # Понедельник, не праздник
        assert monday.weekday() == 0
        assert self.service.is_trading_day(monday) == True
    
    def test_new_year_holiday(self):
        """Новогодние праздники — не торговые дни"""
        new_year = datetime(2026, 1, 1)
        assert self.service.is_trading_day(new_year) == False
        
        jan_7 = datetime(2026, 1, 7)
        assert self.service.is_trading_day(jan_7) == False
    
    def test_feb_23_holiday(self):
        """23 февраля — не торговый день"""
        feb_23 = datetime(2026, 2, 23)
        assert self.service.is_trading_day(feb_23) == False
    
    def test_regular_workday_is_trading(self):
        """Обычный рабочий день — торговый"""
        regular_day = datetime(2026, 3, 16)  # Понедельник, не праздник
        assert self.service.is_trading_day(regular_day) == True


class TestTradingHours:
    """Тесты торговых часов"""
    
    def setup_method(self):
        self.service = MarketService()
    
    def test_trading_hours_morning(self):
        """10:30 — торговое время"""
        dt = datetime(2026, 1, 12, 10, 30)  # Понедельник 10:30
        assert self.service.is_trading_hours(dt) == True
    
    def test_before_trading_hours(self):
        """09:00 — до начала торгов"""
        dt = datetime(2026, 1, 12, 9, 0)  # Понедельник 09:00
        assert self.service.is_trading_hours(dt) == False
    
    def test_after_trading_hours_stocks(self):
        """19:00 — после основной сессии (для акций)"""
        dt = datetime(2026, 1, 12, 19, 0)  # Понедельник 19:00
        # Для акций (is_futures=False) — не торговое время
        assert self.service.is_trading_hours(dt, is_futures=False) == False
    
    def test_evening_session_futures(self):
        """20:00 — вечерняя сессия (для фьючерсов)"""
        dt = datetime(2026, 1, 12, 20, 0)  # Понедельник 20:00
        # Для фьючерсов — торговое время
        assert self.service.is_trading_hours(dt, is_futures=True) == True
    
    def test_weekend_has_no_trading_hours(self):
        """Выходной — нет торговых часов"""
        saturday_noon = datetime(2026, 1, 10, 12, 0)  # Суббота 12:00
        assert self.service.is_trading_hours(saturday_noon) == False


class TestCountTradingHours:
    """Тесты подсчёта торговых часов"""
    
    def setup_method(self):
        self.service = MarketService()
    
    def test_same_day_trading_hours(self):
        """Часы в течение одного торгового дня"""
        start = datetime(2026, 1, 12, 10, 0)  # Понедельник 10:00
        end = datetime(2026, 1, 12, 14, 0)    # Понедельник 14:00
        hours = self.service.count_trading_hours(start, end)
        assert hours >= 3  # Минимум 3 торговых часа
    
    def test_overnight_counts_correctly(self):
        """Через ночь (вне торговых часов) не считается"""
        start = datetime(2026, 1, 12, 18, 0)  # Понедельник 18:00
        end = datetime(2026, 1, 13, 10, 0)    # Вторник 10:00
        hours = self.service.count_trading_hours(start, end)
        # Между 18:00 пн и 10:00 вт почти нет торговых часов
        assert hours <= 2
    
    def test_weekend_has_zero_trading_hours(self):
        """Выходные имеют 0 торговых часов"""
        start = datetime(2026, 1, 10, 10, 0)  # Суббота 10:00
        end = datetime(2026, 1, 11, 18, 0)    # Воскресенье 18:00
        hours = self.service.count_trading_hours(start, end)
        assert hours == 0


class TestPostExitValidation:
    """Тесты валидации входных данных Post-Exit"""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.asyncio
    async def test_invalid_exit_price_zero(self):
        """exit_price = 0 должен вернуть ошибку"""
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=0,
            exit_time=datetime.now()
        )
        assert "error" in result
        assert result["error"] == "Invalid exit_price"
    
    @pytest.mark.asyncio
    async def test_invalid_exit_price_negative(self):
        """exit_price < 0 должен вернуть ошибку"""
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=-100,
            exit_time=datetime.now()
        )
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_missing_exit_time(self):
        """exit_time = None должен вернуть ошибку"""
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=100,
            exit_time=None
        )
        assert "error" in result
        assert result["error"] == "Missing exit_time"
    
    @pytest.mark.asyncio
    async def test_invalid_direction(self):
        """Невалидный direction должен вернуть ошибку"""
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="INVALID",
            exit_price=100,
            exit_time=datetime.now()
        )
        assert "error" in result
        assert result["error"] == "Invalid direction"
    
    @pytest.mark.asyncio
    async def test_empty_direction(self):
        """Пустой direction должен вернуть ошибку"""
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="",
            exit_price=100,
            exit_time=datetime.now()
        )
        assert "error" in result


class TestPostExitWithMockedAPI:
    """Тесты Post-Exit с моками API"""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    @patch.object(MarketService, 'count_trading_hours')
    async def test_no_candles_returns_unavailable(self, mock_trading_hours, mock_candles):
        """Пустые данные с API — период недоступен"""
        mock_candles.return_value = []
        mock_trading_hours.return_value = 10  # Достаточно торговых часов
        
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=100,
            exit_time=datetime(2026, 1, 12, 15, 0),
            timeframe="1H"
        )
        
        # Все периоды должны быть недоступны
        for period_data in result["periods"].values():
            assert period_data["available"] == False
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    @patch.object(MarketService, 'count_trading_hours')
    async def test_weekend_period_shows_warning(self, mock_trading_hours, mock_candles):
        """Период на выходные показывает предупреждение"""
        mock_trading_hours.return_value = 2  # Мало торговых часов (попали на выходные)
        mock_candles.return_value = []
        
        # Выход в пятницу вечером
        friday_evening = datetime(2026, 1, 9, 18, 0)
        
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=100,
            exit_time=friday_evening,
            periods_hours=[24]  # 24 часа = попадёт на субботу
        )
        
        # Период должен быть помечен как недоступный из-за выходных
        period_24h = result["periods"].get("24h", {})
        assert period_24h.get("available") == False
        assert "нерабочие" in period_24h.get("message", "").lower()
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    @patch.object(MarketService, 'count_trading_hours')
    async def test_long_early_exit_detected(self, mock_trading_hours, mock_candles):
        """LONG: рост цены после выхода = ранний выход"""
        mock_trading_hours.return_value = 10
        
        # Мок свечей: цена выросла после выхода
        mock_candles.return_value = [
            {'open': 100, 'high': 115, 'low': 98, 'close': 110, 'begin': '2026-01-12 16:00'},
            {'open': 110, 'high': 120, 'low': 108, 'close': 118, 'begin': '2026-01-12 17:00'},
        ]
        
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=100,  # Вышли по 100
            exit_time=datetime(2026, 1, 12, 15, 0),
            periods_hours=[4]
        )
        
        period_4h = result["periods"].get("4h", {})
        assert period_4h.get("available") == True
        assert period_4h.get("exit_quality") == "early"
        assert period_4h.get("continuation_move_pct") > 0  # Цена выросла
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    @patch.object(MarketService, 'count_trading_hours')
    async def test_short_early_exit_detected(self, mock_trading_hours, mock_candles):
        """SHORT: падение цены после выхода = ранний выход"""
        mock_trading_hours.return_value = 10
        
        # Мок свечей: цена упала после выхода
        mock_candles.return_value = [
            {'open': 100, 'high': 102, 'low': 85, 'close': 90, 'begin': '2026-01-12 16:00'},
            {'open': 90, 'high': 92, 'low': 80, 'close': 82, 'begin': '2026-01-12 17:00'},
        ]
        
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="SHORT",
            exit_price=100,  # Закрыли шорт по 100
            exit_time=datetime(2026, 1, 12, 15, 0),
            periods_hours=[4]
        )
        
        period_4h = result["periods"].get("4h", {})
        assert period_4h.get("available") == True
        assert period_4h.get("exit_quality") == "early"
        assert period_4h.get("continuation_move_pct") > 0  # Цена продолжила падение
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    @patch.object(MarketService, 'count_trading_hours')
    async def test_good_exit_detected(self, mock_trading_hours, mock_candles):
        """Правильный выход: цена развернулась"""
        mock_trading_hours.return_value = 10
        
        # Мок свечей: цена упала после выхода из LONG
        mock_candles.return_value = [
            {'open': 100, 'high': 100.5, 'low': 92, 'close': 93, 'begin': '2026-01-12 16:00'},
            {'open': 93, 'high': 94, 'low': 88, 'close': 89, 'begin': '2026-01-12 17:00'},
        ]
        
        result = await self.service.calculate_post_exit_analysis(
            ticker="SBER",
            direction="LONG",
            exit_price=100,
            exit_time=datetime(2026, 1, 12, 15, 0),
            periods_hours=[4]
        )
        
        period_4h = result["periods"].get("4h", {})
        assert period_4h.get("available") == True
        assert period_4h.get("exit_quality") == "good"


class TestTimeframePeriods:
    """Тесты выбора периодов по таймфрейму"""
    
    def setup_method(self):
        self.service = MarketService()
    
    def test_scalping_timeframe_periods(self):
        """Скальпинг (1m, 5m) — короткие периоды"""
        periods = self.service._get_post_exit_periods("5m")
        assert 0.25 in periods  # 15 минут
        assert 1 in periods     # 1 час
        assert 4 in periods     # 4 часа
    
    def test_intraday_timeframe_periods(self):
        """Интрадей (15m) — средние периоды"""
        periods = self.service._get_post_exit_periods("15m")
        assert 1 in periods     # 1 час
        assert 4 in periods     # 4 часа
        assert 24 in periods    # 1 день
    
    def test_swing_timeframe_periods(self):
        """Свинг (1H) — длинные периоды"""
        periods = self.service._get_post_exit_periods("1H")
        assert 4 in periods     # 4 часа
        assert 24 in periods    # 1 день
        assert 168 in periods   # 1 неделя
    
    def test_daily_timeframe_periods(self):
        """Дневной (1D) — очень длинные периоды"""
        periods = self.service._get_post_exit_periods("1D")
        assert 168 in periods   # 1 неделя
        assert 720 in periods   # ~1 месяц
    
    def test_unknown_timeframe_uses_default(self):
        """Неизвестный таймфрейм — дефолтные периоды"""
        periods = self.service._get_post_exit_periods("UNKNOWN")
        assert len(periods) > 0


class TestEdgeCases:
    """Граничные случаи"""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.asyncio
    async def test_very_small_price_movement(self):
        """Очень маленькое движение цены — neutral"""
        with patch.object(MarketService, 'get_candles') as mock_candles, \
             patch.object(MarketService, 'count_trading_hours') as mock_hours:
            
            mock_hours.return_value = 10
            # Цена почти не изменилась
            mock_candles.return_value = [
                {'open': 100, 'high': 100.3, 'low': 99.7, 'close': 100.1, 'begin': '2026-01-12 16:00'},
            ]
            
            result = await self.service.calculate_post_exit_analysis(
                ticker="SBER",
                direction="LONG",
                exit_price=100,
                exit_time=datetime(2026, 1, 12, 15, 0),
                periods_hours=[4]
            )
            
            period_4h = result["periods"].get("4h", {})
            assert period_4h.get("exit_quality") == "neutral"
    
    @pytest.mark.asyncio
    async def test_extreme_price_movement(self):
        """Экстремальное движение цены"""
        with patch.object(MarketService, 'get_candles') as mock_candles, \
             patch.object(MarketService, 'count_trading_hours') as mock_hours:
            
            mock_hours.return_value = 10
            # Цена выросла на 50%
            mock_candles.return_value = [
                {'open': 100, 'high': 150, 'low': 100, 'close': 145, 'begin': '2026-01-12 16:00'},
            ]
            
            result = await self.service.calculate_post_exit_analysis(
                ticker="SBER",
                direction="LONG",
                exit_price=100,
                exit_time=datetime(2026, 1, 12, 15, 0),
                periods_hours=[4]
            )
            
            period_4h = result["periods"].get("4h", {})
            assert period_4h.get("exit_quality") == "early"
            assert period_4h.get("continuation_move_pct") >= 45  # ~50% рост


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

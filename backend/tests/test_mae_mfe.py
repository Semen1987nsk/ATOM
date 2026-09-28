"""
Тесты для расчёта MAE/MFE из исторических данных MOEX.
Симуляция всех возможных сценариев.
"""

import pytest
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from typing import List, Dict

sys.path.insert(0, '/workspaces/ATOM/backend')

from market_service import MarketService


# ============================================================================
# ГЕНЕРАТОРЫ ТЕСТОВЫХ ДАННЫХ
# ============================================================================

def generate_candles(
    base_price: float = 100.0,
    num_candles: int = 10,
    volatility: float = 0.02,
    trend: str = "neutral"  # "up", "down", "neutral", "volatile"
) -> List[Dict]:
    """Генерирует тестовые свечи."""
    candles = []
    current_price = base_price
    
    base_time = datetime(2025, 12, 1, 10, 0, 0)
    
    for i in range(num_candles):
        # Определяем тренд
        if trend == "up":
            change = abs(volatility * current_price)
        elif trend == "down":
            change = -abs(volatility * current_price)
        elif trend == "volatile":
            change = (1 if i % 2 == 0 else -1) * volatility * current_price * 2
        else:
            change = 0
        
        open_price = current_price
        close_price = current_price + change
        
        # High и Low с учётом волатильности
        high_price = max(open_price, close_price) + abs(volatility * current_price)
        low_price = min(open_price, close_price) - abs(volatility * current_price)
        
        candle_time = base_time + timedelta(hours=i)
        
        candles.append({
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': 1000,
            'begin': candle_time.strftime("%Y-%m-%d %H:%M:%S"),
            'end': (candle_time + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        })
        
        current_price = close_price
    
    return candles


# ============================================================================
# ТЕСТЫ CALCULATE_MAE_MFE
# ============================================================================

class TestCalculateMaeMfe:
    """Тесты расчёта MAE/MFE."""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_long_trade_bullish_market(self, mock_get_candles):
        """LONG в растущем рынке: MFE > entry, MAE близок к entry."""
        # Свечи с восходящим трендом
        mock_get_candles.return_value = generate_candles(
            base_price=100, num_candles=10, volatility=0.01, trend="up"
        )
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 20, 0, 0)
        )
        
        assert mae is not None
        assert mfe is not None
        assert mfe > mae, "MFE должен быть больше MAE для LONG в растущем рынке"
        # Для LONG: MAE = min price, MFE = max price
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_long_trade_bearish_market(self, mock_get_candles):
        """LONG в падающем рынке: MAE значительно ниже entry."""
        mock_get_candles.return_value = generate_candles(
            base_price=100, num_candles=10, volatility=0.02, trend="down"
        )
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 20, 0, 0)
        )
        
        assert mae is not None
        assert mfe is not None
        assert mae < 100, "MAE должен быть ниже entry для LONG в падающем рынке"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_short_trade_bearish_market(self, mock_get_candles):
        """SHORT в падающем рынке: MFE ниже entry (хорошо для шорта)."""
        mock_get_candles.return_value = generate_candles(
            base_price=100, num_candles=10, volatility=0.02, trend="down"
        )
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="SHORT",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 20, 0, 0)
        )
        
        assert mae is not None
        assert mfe is not None
        # Для SHORT: MAE = max price (против нас), MFE = min price (в нашу пользу)
        assert mfe < mae, "MFE должен быть меньше MAE для SHORT в падающем рынке"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_short_trade_bullish_market(self, mock_get_candles):
        """SHORT в растущем рынке: MAE высоко (убыток)."""
        mock_get_candles.return_value = generate_candles(
            base_price=100, num_candles=10, volatility=0.02, trend="up"
        )
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="SHORT",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 20, 0, 0)
        )
        
        assert mae is not None
        assert mfe is not None
        assert mae > 100, "MAE должен быть выше entry для SHORT в растущем рынке"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_volatile_market(self, mock_get_candles):
        """Волатильный рынок: большой разброс MAE/MFE."""
        mock_get_candles.return_value = generate_candles(
            base_price=100, num_candles=20, volatility=0.05, trend="volatile"
        )
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 2, 6, 0, 0)
        )
        
        assert mae is not None
        assert mfe is not None
        spread = mfe - mae
        assert spread > 5, f"В волатильном рынке разброс должен быть большим, получено: {spread}"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_no_candles_returns_none(self, mock_get_candles):
        """Нет данных — возвращаем None."""
        mock_get_candles.return_value = []
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="UNKNOWN",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 20, 0, 0)
        )
        
        assert mae is None
        assert mfe is None
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_single_candle(self, mock_get_candles):
        """Одна свеча — MAE и MFE из high/low этой свечи."""
        mock_get_candles.return_value = [{
            'open': 100,
            'high': 105,
            'low': 95,
            'close': 102,
            'volume': 1000,
            'begin': '2025-12-01 10:00:00',
            'end': '2025-12-01 11:00:00'
        }]
        
        # MAE-01: времена сделок naive-UTC (конвенция БД); свеча 10:00 МСК = 07:00 UTC
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 7, 0, 0),
            exit_time=datetime(2025, 12, 1, 8, 0, 0)
        )

        assert mae == 95, "MAE для LONG должен быть low"
        assert mfe == 105, "MFE для LONG должен быть high"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_single_candle_short(self, mock_get_candles):
        """Одна свеча для SHORT — логика инвертирована."""
        mock_get_candles.return_value = [{
            'open': 100,
            'high': 105,
            'low': 95,
            'close': 98,
            'volume': 1000,
            'begin': '2025-12-01 10:00:00',
            'end': '2025-12-01 11:00:00'
        }]
        
        # MAE-01: naive-UTC; свеча 10:00 МСК = 07:00 UTC
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="SHORT",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 7, 0, 0),
            exit_time=datetime(2025, 12, 1, 8, 0, 0)
        )

        assert mae == 105, "MAE для SHORT должен быть high (против нас)"
        assert mfe == 95, "MFE для SHORT должен быть low (в нашу пользу)"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_candles_with_none_values(self, mock_get_candles):
        """Свечи с None значениями — пропускаем их."""
        mock_get_candles.return_value = [
            {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'},
            {'open': 100, 'high': 105, 'low': 95, 'close': 102, 'volume': 1000, 'begin': '2025-12-01 11:00:00', 'end': '2025-12-01 12:00:00'},
        ]
        
        # MAE-01: naive-UTC; свечи 10:00-12:00 МСК = 07:00-09:00 UTC
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 7, 0, 0),
            exit_time=datetime(2025, 12, 1, 9, 0, 0)
        )

        # Должен использовать только валидную свечу
        assert mae == 95
        assert mfe == 105
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_all_none_candles(self, mock_get_candles):
        """Все свечи с None — возвращаем None."""
        mock_get_candles.return_value = [
            {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'},
            {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0, 'begin': '2025-12-01 11:00:00', 'end': '2025-12-01 12:00:00'},
        ]
        
        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 12, 0, 0)
        )
        
        assert mae is None
        assert mfe is None


# ============================================================================
# ТЕСТЫ ИНТЕРВАЛА СВЕЧЕЙ
# ============================================================================

class TestCandleIntervalSelection:
    """Тесты выбора интервала свечей в зависимости от длительности сделки."""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_short_trade_uses_1min_candles(self, mock_get_candles):
        """Короткая сделка (< 2 часов) использует 1-минутные свечи."""
        mock_get_candles.return_value = []
        
        await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 11, 30, 0)  # 1.5 часа
        )
        
        # Проверяем что вызвали get_candles с interval=1
        call_args = mock_get_candles.call_args
        assert call_args is not None
        # interval — 4-й позиционный аргумент (0=ticker, 1=start, 2=end, 3=interval)
        interval = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get('interval', 60)
        assert interval == 1, f"Для короткой сделки должен быть interval=1, получено {interval}"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_intraday_trade_uses_10min_candles(self, mock_get_candles):
        """Внутридневная сделка (2-24 часа) использует 10-минутные свечи."""
        mock_get_candles.return_value = []
        
        await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 1, 18, 0, 0)  # 8 часов
        )
        
        call_args = mock_get_candles.call_args
        interval = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get('interval', 60)
        assert interval == 10, f"Для внутридневной сделки должен быть interval=10, получено {interval}"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_multiday_trade_uses_hourly_candles(self, mock_get_candles):
        """Многодневная сделка (1-7 дней) использует часовые свечи."""
        mock_get_candles.return_value = []
        
        await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 4, 10, 0, 0)  # 3 дня
        )
        
        call_args = mock_get_candles.call_args
        interval = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get('interval', 60)
        assert interval == 60, f"Для многодневной сделки должен быть interval=60, получено {interval}"
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_long_term_trade_uses_daily_candles(self, mock_get_candles):
        """Долгосрочная сделка (> 7 дней) использует дневные свечи."""
        mock_get_candles.return_value = []
        
        await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 10, 0, 0),
            exit_time=datetime(2025, 12, 20, 10, 0, 0)  # 19 дней
        )
        
        call_args = mock_get_candles.call_args
        interval = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get('interval', 60)
        assert interval == 24, f"Для долгосрочной сделки должен быть interval=24, получено {interval}"


# ============================================================================
# СИМУЛЯЦИЯ МНОЖЕСТВА СЦЕНАРИЕВ
# ============================================================================

class TestMaeMfeSimulation:
    """Симуляция 1000+ сценариев для MAE/MFE."""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_1000_random_scenarios(self, mock_get_candles):
        """Тест 1000 случайных сценариев — нет падений."""
        import random
        random.seed(42)
        
        crashes = []
        invalid_results = []
        
        for i in range(1000):
            # Генерируем случайные параметры
            base_price = random.uniform(10, 10000)
            num_candles = random.randint(1, 100)
            volatility = random.uniform(0.001, 0.1)
            trend = random.choice(["up", "down", "neutral", "volatile"])
            direction = random.choice(["LONG", "SHORT"])
            
            candles = generate_candles(base_price, num_candles, volatility, trend)
            mock_get_candles.return_value = candles
            
            try:
                mae, mfe = await self.service.calculate_mae_mfe(
                    ticker="TEST",
                    direction=direction,
                    entry_price=base_price,
                    entry_time=datetime(2025, 12, 1, 10, 0, 0),
                    exit_time=datetime(2025, 12, 1, 10, 0, 0) + timedelta(hours=num_candles)
                )
                
                # Проверяем валидность результатов
                if mae is not None and mfe is not None:
                    if mae < 0 or mfe < 0:
                        invalid_results.append(f"Scenario {i}: MAE={mae}, MFE={mfe} — отрицательные значения")
                    
                    if direction == "LONG":
                        # Для LONG: MAE = min, MFE = max, поэтому MFE >= MAE
                        if mfe < mae:
                            invalid_results.append(f"Scenario {i}: LONG — MFE ({mfe}) < MAE ({mae})")
                    else:
                        # Для SHORT: MAE = max, MFE = min, поэтому MAE >= MFE
                        if mae < mfe:
                            invalid_results.append(f"Scenario {i}: SHORT — MAE ({mae}) < MFE ({mfe})")
                            
            except Exception as e:
                crashes.append(f"Scenario {i}: {type(e).__name__}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений:\n" + "\n".join(crashes[:10])
        assert len(invalid_results) == 0, f"Найдено {len(invalid_results)} невалидных результатов:\n" + "\n".join(invalid_results[:10])
    
    @pytest.mark.asyncio
    @patch.object(MarketService, 'get_candles')
    async def test_edge_cases(self, mock_get_candles):
        """Тест граничных случаев."""
        
        test_cases = [
            # (описание, candles, expected_mae_not_none, expected_mfe_not_none)
            ("Пустой список", [], False, False),
            ("Одна свеча", [{'open': 100, 'high': 105, 'low': 95, 'close': 100, 'volume': 1000, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'}], True, True),
            ("Все None", [{'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'}], False, False),
            ("High = Low", [{'open': 100, 'high': 100, 'low': 100, 'close': 100, 'volume': 1000, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'}], True, True),
            ("Очень большие числа", [{'open': 1e10, 'high': 1.1e10, 'low': 0.9e10, 'close': 1e10, 'volume': 1000, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'}], True, True),
            ("Очень маленькие числа", [{'open': 0.0001, 'high': 0.00015, 'low': 0.00005, 'close': 0.0001, 'volume': 1000, 'begin': '2025-12-01 10:00:00', 'end': '2025-12-01 11:00:00'}], True, True),
        ]
        
        errors = []
        
        for description, candles, expect_mae, expect_mfe in test_cases:
            mock_get_candles.return_value = candles
            
            try:
                # MAE-01: naive-UTC; свечи 10:00 МСК = 07:00 UTC
                mae, mfe = await self.service.calculate_mae_mfe(
                    ticker="TEST",
                    direction="LONG",
                    entry_price=100.0,
                    entry_time=datetime(2025, 12, 1, 7, 0, 0),
                    exit_time=datetime(2025, 12, 1, 8, 0, 0)
                )
                
                if expect_mae and mae is None:
                    errors.append(f"{description}: ожидался MAE, получен None")
                if not expect_mae and mae is not None:
                    errors.append(f"{description}: ожидался None для MAE, получен {mae}")
                if expect_mfe and mfe is None:
                    errors.append(f"{description}: ожидался MFE, получен None")
                if not expect_mfe and mfe is not None:
                    errors.append(f"{description}: ожидался None для MFE, получен {mfe}")
                    
            except Exception as e:
                errors.append(f"{description}: падение — {e}")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок:\n" + "\n".join(errors)


# ============================================================================
# ИНТЕГРАЦИОННЫЕ ТЕСТЫ (с реальным API, если доступен)
# ============================================================================

class TestMoexApiIntegration:
    """Интеграционные тесты с реальным MOEX API."""
    
    def setup_method(self):
        self.service = MarketService()
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_sber_candles(self):
        """Тест получения реальных свечей SBER (пропускается без интернета)."""
        try:
            candles = await self.service.get_candles(
                ticker="SBER",
                start_date=datetime(2025, 12, 1),
                end_date=datetime(2025, 12, 10),
                interval=60
            )
            
            # Если получили данные — проверяем структуру
            if candles:
                assert all('high' in c for c in candles)
                assert all('low' in c for c in candles)
                assert all('open' in c for c in candles)
                assert all('close' in c for c in candles)
        except Exception as e:
            pytest.skip(f"MOEX API недоступен: {e}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_futures_candles(self):
        """Тест получения реальных свечей фьючерса Si."""
        try:
            candles = await self.service.get_candles(
                ticker="SiH6",  # Фьючерс на доллар
                start_date=datetime(2025, 12, 1),
                end_date=datetime(2025, 12, 10),
                interval=60
            )
            
            # Фьючерс может не торговаться — это нормально
            # Главное чтобы не было ошибок
            assert isinstance(candles, list)
        except Exception as e:
            pytest.skip(f"MOEX API недоступен: {e}")


# ============================================================================
# ЗАПУСК ТЕСТОВ
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x", "-m", "not integration"])

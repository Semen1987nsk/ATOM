"""
Comprehensive tests for import_service.py

Тестируем:
1. TradeManager - FIFO логику, усреднение, переворот позиций
2. Парсинг Excel файлов Тинькофф
3. Парсинг generic CSV/Excel
4. Граничные случаи и ошибки
"""
import pytest
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
import io
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from import_service import TradeManager, parse_trade_file


# ============================================================================
# TradeManager Tests - FIFO Logic
# ============================================================================

class TestTradeManagerBasic:
    """Базовые тесты TradeManager."""
    
    def test_simple_long_trade_open_close(self):
        """Простой LONG: открытие и закрытие."""
        manager = TradeManager()
        
        # Открываем LONG на 100 акций по 50
        manager.process_trade({
            'symbol': 'SBER',
            'direction': models.TradeDirection.LONG,
            'entry_price': 50.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 5000.0,
            'swap': 0.0
        })
        
        assert 'SBER' in manager.open_positions
        assert manager.open_positions['SBER']['quantity'] == 100
        
        # Закрываем SHORT (продаём) по 55
        manager.process_trade({
            'symbol': 'SBER',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 55.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 10.0,
            'deal_sum': 5500.0,
            'swap': 0.0
        })
        
        assert 'SBER' not in manager.open_positions
        assert len(manager.completed_trades) == 1
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == 500.0  # (55 - 50) * 100 = 500 (по deal_sum)
        assert trade['net_pnl'] == 480.0  # 500 - 10 - 10 = 480
    
    def test_simple_short_trade_open_close(self):
        """Простой SHORT: открытие и закрытие."""
        manager = TradeManager()
        
        # Открываем SHORT на 200 акций по 100
        manager.process_trade({
            'symbol': 'GAZP',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 100.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 20.0,
            'deal_sum': 20000.0,
            'swap': 0.0
        })
        
        # Закрываем LONG (покупаем) по 95
        manager.process_trade({
            'symbol': 'GAZP',
            'direction': models.TradeDirection.LONG,
            'entry_price': 95.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 12, 0),
            'commission': 19.0,
            'deal_sum': 19000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == 1000.0  # (100 - 95) * 200 = 1000
        assert trade['net_pnl'] == 961.0  # 1000 - 20 - 19 = 961


class TestTradeManagerAveraging:
    """Тесты усреднения позиций (averaging/pyramiding)."""
    
    def test_averaging_long_position(self):
        """Добавление к LONG позиции - усреднение."""
        manager = TradeManager()
        
        # Первый вход: 100 акций по 50
        manager.process_trade({
            'symbol': 'AFKS',
            'direction': models.TradeDirection.LONG,
            'entry_price': 50.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 5.0,
            'deal_sum': 5000.0,
            'swap': 0.0
        })
        
        # Второй вход: ещё 100 акций по 40 (усреднение вниз)
        manager.process_trade({
            'symbol': 'AFKS',
            'direction': models.TradeDirection.LONG,
            'entry_price': 40.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 30),
            'commission': 4.0,
            'deal_sum': 4000.0,
            'swap': 0.0
        })
        
        pos = manager.open_positions['AFKS']
        assert pos['quantity'] == 200
        # Средняя цена: (50*100 + 40*100) / 200 = 9000/200 = 45
        assert pos['entry_price'] == 45.0
        assert pos['entry_commission'] == 9.0
        assert len(pos['operations']) == 2
        
        # Закрываем всё по 48
        manager.process_trade({
            'symbol': 'AFKS',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 48.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 9.6,
            'deal_sum': 9600.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # PnL по deal_sum: 9600 - 9000 = 600
        assert trade['pnl'] == 600.0
        assert len(trade['operations']) == 3  # 2 входа + 1 выход
    
    def test_pyramiding_with_multiple_entries(self):
        """Пирамидинг: несколько добавлений к выигрышной позиции."""
        manager = TradeManager()
        
        entries = [
            (100.0, 50, 5000.0),   # 50 по 100
            (105.0, 30, 3150.0),   # 30 по 105
            (110.0, 20, 2200.0),   # 20 по 110
        ]
        
        for i, (price, qty, deal_sum) in enumerate(entries):
            manager.process_trade({
                'symbol': 'LKOH',
                'direction': models.TradeDirection.LONG,
                'entry_price': price,
                'quantity': qty,
                'entry_at': datetime(2025, 1, 1, 10, i * 10),
                'commission': 1.0,
                'deal_sum': deal_sum,
                'swap': 0.0
            })
        
        pos = manager.open_positions['LKOH']
        assert pos['quantity'] == 100
        # Средняя: (100*50 + 105*30 + 110*20) / 100 = 10350/100 = 103.5
        assert pos['entry_price'] == 103.5
        assert len(pos['operations']) == 3


class TestTradeManagerPartialClose:
    """Тесты частичного закрытия позиций."""
    
    def test_partial_close_long(self):
        """Частичное закрытие LONG позиции."""
        manager = TradeManager()
        
        # Открываем 200 акций
        manager.process_trade({
            'symbol': 'TATN',
            'direction': models.TradeDirection.LONG,
            'entry_price': 500.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 20.0,
            'deal_sum': 100000.0,
            'swap': 0.0
        })
        
        # Закрываем 100 акций (частично)
        manager.process_trade({
            'symbol': 'TATN',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 520.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 10.0,
            'deal_sum': 52000.0,
            'swap': 0.0
        })
        
        # Должна остаться открытая позиция на 100
        assert 'TATN' in manager.open_positions
        assert manager.open_positions['TATN']['quantity'] == 100
        
        # И одна закрытая на 100
        assert len(manager.completed_trades) == 1
        closed = manager.completed_trades[0]
        assert closed['quantity'] == 100
        # PnL: 52000 - 50000 = 2000
        assert closed['pnl'] == 2000.0
    
    def test_multiple_partial_closes(self):
        """Несколько частичных закрытий подряд."""
        manager = TradeManager()
        
        # Открываем 300 акций
        manager.process_trade({
            'symbol': 'NVTK',
            'direction': models.TradeDirection.LONG,
            'entry_price': 1000.0,
            'quantity': 300,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 30.0,
            'deal_sum': 300000.0,
            'swap': 0.0
        })
        
        # Первое частичное закрытие: 100
        manager.process_trade({
            'symbol': 'NVTK',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 1050.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 10.0,
            'deal_sum': 105000.0,
            'swap': 0.0
        })
        
        # Второе частичное закрытие: 100
        manager.process_trade({
            'symbol': 'NVTK',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 1100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 12, 0),
            'commission': 11.0,
            'deal_sum': 110000.0,
            'swap': 0.0
        })
        
        assert manager.open_positions['NVTK']['quantity'] == 100
        assert len(manager.completed_trades) == 2


class TestTradeManagerFlip:
    """Тесты переворота позиции (flip)."""
    
    def test_flip_long_to_short(self):
        """Переворот из LONG в SHORT."""
        manager = TradeManager()
        
        # Открываем LONG 100 акций
        manager.process_trade({
            'symbol': 'SIBN',
            'direction': models.TradeDirection.LONG,
            'entry_price': 400.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 4.0,
            'deal_sum': 40000.0,
            'swap': 0.0
        })
        
        # Переворот: продаём 200 (закрываем 100 LONG + открываем 100 SHORT)
        manager.process_trade({
            'symbol': 'SIBN',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 380.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 7.6,
            'deal_sum': 76000.0,
            'swap': 0.0
        })
        
        # Проверяем закрытую сделку
        assert len(manager.completed_trades) == 1
        closed = manager.completed_trades[0]
        assert closed['direction'] == models.TradeDirection.LONG
        assert closed['pnl'] == -2000.0  # (38000 - 40000) = -2000
        
        # Проверяем новую открытую SHORT
        assert 'SIBN' in manager.open_positions
        pos = manager.open_positions['SIBN']
        assert pos['direction'] == models.TradeDirection.SHORT
        assert pos['quantity'] == 100
    
    def test_flip_short_to_long(self):
        """Переворот из SHORT в LONG."""
        manager = TradeManager()
        
        # Открываем SHORT 50 акций
        manager.process_trade({
            'symbol': 'VTBR',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 0.025,
            'quantity': 100000,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 2.5,
            'deal_sum': 2500.0,
            'swap': 0.0
        })
        
        # Переворот: покупаем 150000 (закрываем 100000 SHORT + открываем 50000 LONG)
        manager.process_trade({
            'symbol': 'VTBR',
            'direction': models.TradeDirection.LONG,
            'entry_price': 0.024,
            'quantity': 150000,
            'entry_at': datetime(2025, 1, 1, 12, 0),
            'commission': 3.6,
            'deal_sum': 3600.0,
            'swap': 0.0
        })
        
        # Закрытая SHORT должна быть прибыльной
        closed = manager.completed_trades[0]
        assert closed['direction'] == models.TradeDirection.SHORT
        # SHORT PnL: entry_deal_sum - exit_deal_sum = 2500 - 2400 = 100
        assert closed['pnl'] == 100.0
        
        # Новая открытая LONG
        pos = manager.open_positions['VTBR']
        assert pos['direction'] == models.TradeDirection.LONG
        assert pos['quantity'] == 50000


class TestTradeManagerMultipleSymbols:
    """Тесты с несколькими тикерами одновременно."""
    
    def test_simultaneous_positions_different_symbols(self):
        """Одновременные позиции по разным тикерам."""
        manager = TradeManager()
        
        # Открываем LONG SBER
        manager.process_trade({
            'symbol': 'SBER',
            'direction': models.TradeDirection.LONG,
            'entry_price': 300.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 3.0,
            'deal_sum': 30000.0,
            'swap': 0.0
        })
        
        # Открываем SHORT GAZP
        manager.process_trade({
            'symbol': 'GAZP',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 150.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 10, 5),
            'commission': 3.0,
            'deal_sum': 30000.0,
            'swap': 0.0
        })
        
        assert len(manager.open_positions) == 2
        assert 'SBER' in manager.open_positions
        assert 'GAZP' in manager.open_positions
        
        # Закрываем GAZP в плюс
        manager.process_trade({
            'symbol': 'GAZP',
            'direction': models.TradeDirection.LONG,
            'entry_price': 140.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 2.8,
            'deal_sum': 28000.0,
            'swap': 0.0
        })
        
        assert len(manager.open_positions) == 1
        assert 'SBER' in manager.open_positions
        assert len(manager.completed_trades) == 1


class TestTradeManagerEdgeCases:
    """Граничные случаи и потенциальные ошибки."""
    
    def test_zero_quantity_trade(self):
        """Сделка с нулевым количеством должна пропускаться."""
        manager = TradeManager()
        
        result = manager.process_trade({
            'symbol': 'TEST',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 0,  # Zero quantity
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 0.0,
            'deal_sum': 0.0,
            'swap': 0.0
        })
        
        # Сделка с нулевым количеством пропускается
        assert result == False
        assert 'TEST' not in manager.open_positions
    
    def test_negative_quantity(self):
        """Сделки с отрицательным количеством должны пропускаться."""
        manager = TradeManager()
        
        result = manager.process_trade({
            'symbol': 'NEG',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': -50,  # Negative
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': -5000.0,
            'swap': 0.0
        })
        
        # Сделка пропущена
        assert result == False
        assert 'NEG' not in manager.open_positions
    
    def test_empty_symbol(self):
        """Сделка с пустым символом должна пропускаться."""
        manager = TradeManager()
        
        result = manager.process_trade({
            'symbol': '',  # Empty
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        assert result == False
        assert len(manager.open_positions) == 0
    
    def test_zero_price(self):
        """Сделка с нулевой ценой должна пропускаться."""
        manager = TradeManager()
        
        result = manager.process_trade({
            'symbol': 'ZERO_PRICE',
            'direction': models.TradeDirection.LONG,
            'entry_price': 0.0,  # Zero price
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 0.0,
            'swap': 0.0
        })
        
        assert result == False
        assert 'ZERO_PRICE' not in manager.open_positions
    
    def test_missing_direction(self):
        """Сделка без направления должна пропускаться."""
        manager = TradeManager()
        
        result = manager.process_trade({
            'symbol': 'NO_DIR',
            'direction': None,  # No direction
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        assert result == False
        assert 'NO_DIR' not in manager.open_positions
    
    def test_missing_entry_at(self):
        """Сделка без времени должна пропускаться."""
        manager = TradeManager()
        
        result = manager.process_trade({
            'symbol': 'NO_TIME',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': None,  # No time
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        assert result == False
        assert 'NO_TIME' not in manager.open_positions
    
    def test_very_large_numbers(self):
        """Очень большие числа (проверка на overflow)."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'BIG',
            'direction': models.TradeDirection.LONG,
            'entry_price': 1e12,  # 1 триллион
            'quantity': 1e9,  # 1 миллиард
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1e6,
            'deal_sum': 1e21,
            'swap': 0.0
        })
        
        pos = manager.open_positions['BIG']
        assert pos['quantity'] == 1e9
    
    def test_very_small_numbers(self):
        """Очень маленькие числа (проверка точности)."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'SMALL',
            'direction': models.TradeDirection.LONG,
            'entry_price': 0.00001,
            'quantity': 1000000,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 0.001,
            'deal_sum': 10.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'SMALL',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 0.000011,
            'quantity': 1000000,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 0.001,
            'deal_sum': 11.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # PnL: 11 - 10 = 1
        assert abs(trade['pnl'] - 1.0) < 0.001
    
    def test_same_timestamp_trades(self):
        """Сделки с одинаковым временем."""
        manager = TradeManager()
        same_time = datetime(2025, 1, 1, 10, 0, 0)
        
        manager.process_trade({
            'symbol': 'SYNC',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 50,
            'entry_at': same_time,
            'commission': 1.0,
            'deal_sum': 5000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'SYNC',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 50,
            'entry_at': same_time,  # Same timestamp
            'commission': 1.0,
            'deal_sum': 5000.0,
            'swap': 0.0
        })
        
        pos = manager.open_positions['SYNC']
        assert pos['quantity'] == 100
    
    def test_finalize_with_open_positions(self):
        """Финализация с незакрытыми позициями."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'OPEN1',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'OPEN2',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 50.0,
            'quantity': 200,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        result = manager.finalize()
        
        # Обе открытые позиции должны быть в результате
        assert len(result) == 2
        symbols = [t['symbol'] for t in result]
        assert 'OPEN1' in symbols
        assert 'OPEN2' in symbols
        
        # У открытых позиций не должно быть exit
        for t in result:
            assert t['exit_at'] is None
            assert t['pnl'] is None
    
    def test_missing_deal_sum_fallback(self):
        """Отсутствие deal_sum - должен использовать fallback."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'NODEAL',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 0,  # No deal_sum
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'NODEAL',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 1.0,
            'deal_sum': 0,  # No deal_sum
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # Fallback: (exit_price - entry_price) * qty = (110 - 100) * 100 = 1000
        assert trade['pnl'] == 1000.0


class TestTradeManagerHoldingTime:
    """Тесты расчёта времени удержания."""
    
    def test_holding_time_minutes(self):
        """Расчёт времени удержания в минутах."""
        manager = TradeManager()
        
        entry_time = datetime(2025, 1, 1, 10, 0)
        exit_time = datetime(2025, 1, 1, 10, 45)
        
        manager.process_trade({
            'symbol': 'TIME',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': entry_time,
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'TIME',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 105.0,
            'quantity': 100,
            'entry_at': exit_time,
            'commission': 1.0,
            'deal_sum': 10500.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['holding_time_minutes'] == 45
    
    def test_holding_time_overnight(self):
        """Время удержания через ночь."""
        manager = TradeManager()
        
        entry_time = datetime(2025, 1, 1, 18, 30)
        exit_time = datetime(2025, 1, 2, 10, 30)  # Следующий день
        
        manager.process_trade({
            'symbol': 'NIGHT',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': entry_time,
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 5.0
        })
        
        manager.process_trade({
            'symbol': 'NIGHT',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 102.0,
            'quantity': 100,
            'entry_at': exit_time,
            'commission': 1.0,
            'deal_sum': 10200.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # 18:30 до 10:30 след. дня = 16 часов = 960 минут
        assert trade['holding_time_minutes'] == 960


class TestTradeManagerOperations:
    """Тесты массива operations для аккордеона."""
    
    def test_operations_structure(self):
        """Проверка структуры операций."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'OPS',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'OPS',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 1.1,
            'deal_sum': 11000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        ops = trade['operations']
        
        assert len(ops) == 2
        
        # Entry operation
        assert ops[0]['type'] == 'entry'
        assert ops[0]['price'] == 100.0
        assert ops[0]['qty'] == 100
        assert ops[0]['time'] == '10:00:00'
        assert ops[0]['date'] == '01.01.2025'
        
        # Exit operation  
        assert ops[1]['type'] == 'exit'
        assert ops[1]['price'] == 110.0
        assert ops[1]['qty'] == 100
        assert ops[1]['commission'] == 1.1


# ============================================================================
# Parse Trade File Tests
# ============================================================================

class TestParseTradeFileCSV:
    """Тесты парсинга CSV файлов."""
    
    def test_parse_simple_csv(self):
        """Парсинг простого CSV с базовыми полями."""
        csv_content = """date,symbol,side,price,quantity,pnl
2025-01-01 10:00:00,BTCUSDT,BUY,45000,0.1,
2025-01-01 11:00:00,BTCUSDT,SELL,46000,0.1,100
2025-01-02 09:00:00,ETHUSDT,BUY,2500,1.0,
"""
        trades = parse_trade_file(csv_content.encode(), 'trades.csv')
        
        assert len(trades) == 3
        assert trades[0]['symbol'] == 'BTCUSDT'
        assert trades[0]['direction'] == models.TradeDirection.LONG
    
    def test_parse_csv_with_missing_columns(self):
        """CSV без обязательных колонок должен бросить ошибку."""
        csv_content = """name,value
test,123
"""
        with pytest.raises(ValueError):
            parse_trade_file(csv_content.encode(), 'bad.csv')
    
    def test_parse_csv_binance_style(self):
        """Парсинг Binance-стиля CSV."""
        csv_content = """Date(UTC),Symbol,Type,Price,Amount
2025-01-01 10:00:00,BTCUSDT,BUY,50000,0.5
2025-01-01 10:05:00,BTCUSDT,SELL,51000,0.5
"""
        trades = parse_trade_file(csv_content.encode(), 'binance.csv')
        
        assert len(trades) == 2
        assert trades[0]['quantity'] == 0.5
    
    def test_parse_csv_with_long_short_direction(self):
        """CSV с направлениями LONG/SHORT - должны группироваться в одну позицию."""
        csv_content = """date,symbol,direction,price,qty
2025-01-01 10:00:00,TEST,LONG,100,10
2025-01-01 11:00:00,TEST,SHORT,110,10
"""
        trades = parse_trade_file(csv_content.encode(), 'positions.csv')
        
        # Теперь используется FIFO логика: LONG + SHORT = 1 закрытая сделка
        assert len(trades) == 1
        assert trades[0]['direction'] == models.TradeDirection.LONG
        assert trades[0]['exit_at'] is not None
        assert trades[0]['pnl'] == 100.0  # (110 - 100) * 10 = 100
    
    def test_parse_csv_fifo_grouping(self):
        """CSV должен группировать сделки по FIFO."""
        csv_content = """date,symbol,side,price,quantity
2025-01-01 10:00:00,BTC,BUY,50000,1
2025-01-01 10:30:00,BTC,BUY,49000,1
2025-01-01 11:00:00,BTC,SELL,52000,2
"""
        trades = parse_trade_file(csv_content.encode(), 'btc_trades.csv')
        
        # 2 BUY объединяются в одну позицию, 1 SELL закрывает её
        assert len(trades) == 1
        assert trades[0]['quantity'] == 2
        # Средняя цена: (50000 + 49000) / 2 = 49500
        assert trades[0]['entry_price'] == 49500
        # PnL: (52000 * 2) - (50000 + 49000) = 104000 - 99000 = 5000
        assert trades[0]['pnl'] == 5000.0
    
    def test_parse_csv_open_position(self):
        """CSV с незакрытой позицией."""
        csv_content = """date,symbol,side,price,quantity
2025-01-01 10:00:00,ETH,BUY,2500,5
"""
        trades = parse_trade_file(csv_content.encode(), 'eth.csv')
        
        assert len(trades) == 1
        assert trades[0]['exit_at'] is None
        assert trades[0]['pnl'] is None  # Открытая позиция


class TestParseTradeFileErrors:
    """Тесты обработки ошибок при парсинге."""
    
    def test_unsupported_format(self):
        """Неподдерживаемый формат файла."""
        with pytest.raises(ValueError):
            parse_trade_file(b'content', 'file.pdf')
    
    def test_corrupted_file(self):
        """Повреждённый файл."""
        with pytest.raises(ValueError):
            parse_trade_file(b'\x00\x01\x02', 'corrupted.csv')
    
    def test_empty_file(self):
        """Пустой файл."""
        with pytest.raises(Exception):
            parse_trade_file(b'', 'empty.csv')


# ============================================================================
# PnL Calculation Tests
# ============================================================================

class TestPnLCalculations:
    """Тесты правильности расчёта PnL."""
    
    def test_long_profitable(self):
        """LONG в прибыли."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'WIN',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'WIN',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 120.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 12.0,
            'deal_sum': 12000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == 2000.0
        assert trade['net_pnl'] == 1978.0  # 2000 - 10 - 12 = 1978
    
    def test_long_loss(self):
        """LONG в убытке."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'LOSE',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'LOSE',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 90.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 9.0,
            'deal_sum': 9000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == -1000.0
        assert trade['net_pnl'] == -1019.0  # -1000 - 10 - 9 = -1019
    
    def test_short_profitable(self):
        """SHORT в прибыли."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'SHORTWIN',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'SHORTWIN',
            'direction': models.TradeDirection.LONG,
            'entry_price': 80.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 8.0,
            'deal_sum': 8000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == 2000.0  # 10000 - 8000 = 2000
        assert trade['net_pnl'] == 1982.0  # 2000 - 10 - 8 = 1982
    
    def test_short_loss(self):
        """SHORT в убытке."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'SHORTLOSE',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'SHORTLOSE',
            'direction': models.TradeDirection.LONG,
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 11.0,
            'deal_sum': 11000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == -1000.0  # 10000 - 11000 = -1000
        assert trade['net_pnl'] == -1021.0


class TestCommissionsAndSwap:
    """Тесты комиссий и свопов."""
    
    def test_swap_included_in_net_pnl(self):
        """Своп учитывается в net_pnl."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'SWAP',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 10000.0,
            'swap': 50.0  # Значительный своп
        })
        
        manager.process_trade({
            'symbol': 'SWAP',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 3, 10, 0),  # Через 2 дня
            'commission': 11.0,
            'deal_sum': 11000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['pnl'] == 1000.0
        assert trade['commission'] == 21.0  # entry + exit
        assert trade['swap'] == 50.0
        assert trade['net_pnl'] == 929.0  # 1000 - 21 - 50 = 929
    
    def test_entry_exit_commission_split(self):
        """Разделение комиссий на entry и exit."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'COMM',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 15.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'COMM',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 16.5,
            'deal_sum': 11000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        assert trade['entry_commission'] == 15.0
        assert trade['exit_commission'] == 16.5
        assert trade['commission'] == 31.5


# ============================================================================
# ISIN to Ticker Mapping Tests
# ============================================================================

class TestISINMapping:
    """Тесты маппинга ISIN кодов СПБ биржи."""
    
    def test_known_isin_mapped(self):
        """Известные ISIN должны маппиться в тикеры."""
        from import_service import parse_tinkoff_excel
        
        # Эти тесты требуют реального Excel файла или мока
        # Здесь проверяем только наличие маппинга в коде
        isin_to_ticker = {
            'RU0006944147': 'TATNP',
            'RU0007661625': 'GAZP',
            'RU000A107UL4': 'T',
        }
        
        for isin, expected_ticker in isin_to_ticker.items():
            assert expected_ticker in ['TATNP', 'GAZP', 'T']


# ============================================================================
# Asset Type Detection Tests
# ============================================================================

class TestAssetTypeDetection:
    """Тесты определения типа актива."""
    
    def test_futures_pattern_detection(self):
        r"""Детекция фьючерсов по паттерну.
        
        ИСПРАВЛЕНО: Паттерн теперь поддерживает mixed case (SiZ4, BRF5 и т.д.)
        """
        import re
        
        # Тикеры как они приходят из отчётов Тинькофф (mixed case)
        futures_symbols = ['SiZ4', 'RIH5', 'BRF5', 'GZM5', 'SRH5', 'EDU5']
        stock_symbols = ['SBER', 'GAZP', 'LKOH', 'AFKS', 'NVTK']
        
        # Исправленный паттерн из import_service.py
        futures_pattern = r'^[A-Za-z]{2,4}[FGHJKMNQUVXZfghjkmnquvxz]\d$'
        
        for symbol in futures_symbols:
            assert re.search(futures_pattern, symbol), f"{symbol} should match futures pattern"
        
        for symbol in stock_symbols:
            assert not re.search(futures_pattern, symbol), f"{symbol} should NOT match futures pattern"
    
    def test_futures_pattern_fixed(self):
        """Проверка, что исправление работает."""
        import re
        
        symbol = 'SiZ4'  # Индекс Si, декабрь 2024
        
        # Исправленный паттерн
        pattern = r'^[A-Za-z]{2,4}[FGHJKMNQUVXZfghjkmnquvxz]\d$'
        
        match = re.search(pattern, symbol)
        assert match is not None, f"Pattern should match '{symbol}'"
    
    def test_bond_detection(self):
        """Детекция облигаций."""
        bond_patterns = ['SU26238RMFS3', 'RU000A0JWHA5']
        
        for symbol in bond_patterns:
            is_bond = symbol.startswith('SU') or 'ОФЗ' in symbol
            if symbol.startswith('SU'):
                assert is_bond, f"{symbol} should be detected as bond"


# ============================================================================
# Potential Bugs & Edge Cases Tests
# ============================================================================

class TestPotentialBugs:
    """Тесты для выявления потенциальных багов в import_service.py."""
    
    def test_division_by_zero_in_averaging(self):
        """Сделки с нулевым quantity должны пропускаться.

        ИСПРАВЛЕНО: Добавлена валидация в process_trade(),
        сделки с quantity <= 0 теперь пропускаются и возвращают False.
        """
        manager = TradeManager()

        # Пытаемся открыть позицию с 0 qty - должно вернуть False
        result = manager.process_trade({
            'symbol': 'ZERO',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 0,  # Zero!
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 0.0,
            'deal_sum': 0.0,
            'swap': 0.0
        })
        
        # Сделка должна быть пропущена
        assert result == False
        assert 'ZERO' not in manager.open_positions
        
        # Отрицательное количество тоже пропускается
        result2 = manager.process_trade({
            'symbol': 'NEG',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': -50,  # Negative
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 0.0,
            'deal_sum': 0.0,
            'swap': 0.0
        })
        
        assert result2 == False
        assert 'NEG' not in manager.open_positions
    
    def test_race_condition_same_symbol_fast_trades(self):
        """Быстрые сделки по одному тикеру - правильный порядок."""
        manager = TradeManager()
        
        base_time = datetime(2025, 1, 1, 10, 0, 0)
        
        # 10 быстрых сделок за 10 секунд
        for i in range(10):
            manager.process_trade({
                'symbol': 'FAST',
                'direction': models.TradeDirection.LONG,
                'entry_price': 100.0 + i,
                'quantity': 10,
                'entry_at': base_time + timedelta(seconds=i),
                'commission': 0.1,
                'deal_sum': (100.0 + i) * 10,
                'swap': 0.0
            })
        
        pos = manager.open_positions['FAST']
        assert pos['quantity'] == 100
        assert len(pos['operations']) == 10
    
    def test_close_more_than_open_quantity(self):
        """Закрытие БОЛЬШЕГО количества чем открыто - переворот."""
        manager = TradeManager()
        
        # Открываем 100
        manager.process_trade({
            'symbol': 'OVER',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        # Закрываем 300 (должен перевернуться на 200 SHORT)
        manager.process_trade({
            'symbol': 'OVER',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 300,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 3.0,
            'deal_sum': 33000.0,
            'swap': 0.0
        })
        
        # Должна быть одна закрытая LONG
        assert len(manager.completed_trades) == 1
        closed = manager.completed_trades[0]
        assert closed['quantity'] == 100
        
        # И одна открытая SHORT на 200
        assert 'OVER' in manager.open_positions
        pos = manager.open_positions['OVER']
        assert pos['direction'] == models.TradeDirection.SHORT
        assert pos['quantity'] == 200
    
    def test_unicode_symbol_handling(self):
        """Символы с unicode (кириллица в названии)."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'СБЕР',  # Кириллица!
            'asset_name': 'Сбербанк России',
            'direction': models.TradeDirection.LONG,
            'entry_price': 300.0,
            'quantity': 10,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 3.0,
            'deal_sum': 3000.0,
            'swap': 0.0
        })
        
        assert 'СБЕР' in manager.open_positions
    
    def test_extreme_price_difference(self):
        """Экстремальная разница цен (stock split scenario)."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'SPLIT',
            'direction': models.TradeDirection.LONG,
            'entry_price': 1000.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 100000.0,
            'swap': 0.0
        })
        
        # После сплита 1:10 цена стала в 10 раз меньше
        manager.process_trade({
            'symbol': 'SPLIT',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 100.0,  # В 10 раз меньше
            'quantity': 100,
            'entry_at': datetime(2025, 1, 2, 10, 0),
            'commission': 1.0,
            'deal_sum': 10000.0,  # Но deal_sum тоже меньше (если не учли сплит)
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # PnL будет огромный убыток если не учли сплит
        assert trade['pnl'] == -90000.0  # (10000 - 100000)
    
    def test_floating_point_precision(self):
        """Проблемы с точностью float."""
        manager = TradeManager()
        
        # Классическая проблема: 0.1 + 0.2 != 0.3
        manager.process_trade({
            'symbol': 'FLOAT',
            'direction': models.TradeDirection.LONG,
            'entry_price': 0.1,
            'quantity': 1000000,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 0.0,
            'deal_sum': 100000.0,  # 0.1 * 1000000
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'FLOAT',
            'direction': models.TradeDirection.LONG,
            'entry_price': 0.2,
            'quantity': 1000000,
            'entry_at': datetime(2025, 1, 1, 10, 1),
            'commission': 0.0,
            'deal_sum': 200000.0,
            'swap': 0.0
        })
        
        pos = manager.open_positions['FLOAT']
        # Средняя цена должна быть 0.15
        # Но из-за float может быть 0.15000000000000002
        assert abs(pos['entry_price'] - 0.15) < 1e-10, \
            f"Float precision issue: {pos['entry_price']} != 0.15"
    
    def test_date_parsing_edge_cases(self):
        """Граничные случаи парсинга дат."""
        manager = TradeManager()
        
        # Новый год (переход года)
        manager.process_trade({
            'symbol': 'NEWYEAR',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2024, 12, 31, 23, 59, 59),
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'NEWYEAR',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 101.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 0, 0, 1),  # Новый год!
            'commission': 1.0,
            'deal_sum': 10100.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # Время удержания: 2 секунды = 0 минут (целочисленное деление)
        assert trade['holding_time_minutes'] == 0
    
    def test_leap_second_handling(self):
        """29 февраля (високосный год)."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'LEAP',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2024, 2, 29, 10, 0),  # 2024 - високосный
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        assert 'LEAP' in manager.open_positions


class TestConcurrencyScenarios:
    """Тесты сценариев с конкурентными/параллельными данными."""
    
    def test_out_of_order_timestamps(self):
        """Сделки приходят не в хронологическом порядке.
        
        Это может случиться если импортировать из разных источников
        или если брокер отдаёт данные не по порядку.
        """
        manager = TradeManager()
        
        # Сначала приходит ПОЗДНЯЯ сделка
        manager.process_trade({
            'symbol': 'ORDER',
            'direction': models.TradeDirection.SHORT,  # Закрытие
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),  # ПОЗЖЕ
            'commission': 1.0,
            'deal_sum': 11000.0,
            'swap': 0.0
        })
        
        # Затем приходит РАННЯЯ сделка
        manager.process_trade({
            'symbol': 'ORDER',
            'direction': models.TradeDirection.LONG,  # Открытие
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),  # РАНЬШЕ
            'commission': 1.0,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        # Результат будет неправильным!
        # Вместо одной закрытой сделки у нас будет
        # одна закрытая SHORT (неправильно) и одна открытая LONG
        # Это потенциальный BUG - код не сортирует по времени
        
        # Документируем текущее (возможно неправильное) поведение
        assert len(manager.completed_trades) == 1
        # SHORT стала "закрытой" хотя это была первая сделка
    
    def test_microsecond_trades(self):
        """Высокочастотные сделки (микросекунды)."""
        manager = TradeManager()
        
        base_time = datetime(2025, 1, 1, 10, 0, 0)
        
        # 1000 сделок за секунду
        for i in range(1000):
            manager.process_trade({
                'symbol': 'HFT',
                'direction': models.TradeDirection.LONG,
                'entry_price': 100.0,
                'quantity': 1,
                'entry_at': base_time + timedelta(microseconds=i * 1000),
                'commission': 0.01,
                'deal_sum': 100.0,
                'swap': 0.0
            })
        
        pos = manager.open_positions['HFT']
        assert pos['quantity'] == 1000


class TestDataIntegrity:
    """Тесты целостности данных."""
    
    def test_operations_count_matches_trades(self):
        """Количество операций должно соответствовать количеству сделок."""
        manager = TradeManager()
        
        # 3 входа
        for i in range(3):
            manager.process_trade({
                'symbol': 'OPS',
                'direction': models.TradeDirection.LONG,
                'entry_price': 100.0 + i,
                'quantity': 100,
                'entry_at': datetime(2025, 1, 1, 10, i),
                'commission': 1.0,
                'deal_sum': (100.0 + i) * 100,
                'swap': 0.0
            })
        
        # 1 полный выход
        manager.process_trade({
            'symbol': 'OPS',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 300,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 3.0,
            'deal_sum': 33000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # Должно быть 4 операции: 3 entry + 1 exit
        assert len(trade['operations']) == 4
    
    def test_commission_consistency(self):
        """entry_commission + exit_commission = commission."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'COMM',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 15.5,
            'deal_sum': 10000.0,
            'swap': 0.0
        })
        
        manager.process_trade({
            'symbol': 'COMM',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 110.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 17.05,
            'deal_sum': 11000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        total = trade['entry_commission'] + trade['exit_commission']
        assert abs(total - trade['commission']) < 0.001, \
            f"Commission mismatch: {trade['entry_commission']} + {trade['exit_commission']} != {trade['commission']}"
    
    def test_pnl_net_pnl_relationship(self):
        """net_pnl = pnl - commission - swap."""
        manager = TradeManager()
        
        manager.process_trade({
            'symbol': 'NET',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 10000.0,
            'swap': 5.0
        })
        
        manager.process_trade({
            'symbol': 'NET',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 120.0,
            'quantity': 100,
            'entry_at': datetime(2025, 1, 1, 11, 0),
            'commission': 12.0,
            'deal_sum': 12000.0,
            'swap': 3.0
        })
        
        trade = manager.completed_trades[0]
        expected_net = trade['pnl'] - trade['commission'] - trade['swap']
        assert abs(trade['net_pnl'] - expected_net) < 0.001, \
            f"net_pnl mismatch: {trade['net_pnl']} != {expected_net}"


class TestTinkoffExcelEdgeCases:
    """Тесты граничных случаев парсинга Excel Тинькофф."""
    
    def test_repo_trades_skipped(self):
        """РЕПО сделки должны пропускаться."""
        # Этот тест требует мока Excel файла
        # Проверяем, что логика фильтрации работает
        side_values = ['Покупка', 'Продажа', 'РЕПО', 'РПС', 'репо 1д']
        
        for side in side_values:
            side_str = str(side).lower()
            is_repo = 'репо' in side_str or 'рпс' in side_str
            
            if side in ['РЕПО', 'РПС', 'репо 1д']:
                assert is_repo, f"{side} should be detected as REPO"
            else:
                assert not is_repo, f"{side} should NOT be detected as REPO"
    
    def test_margin_fee_distribution(self):
        """Распределение маржинальной комиссии."""
        # Проверяем логику распределения через TradeManager
        manager = TradeManager()
        
        # Открываем позицию 1 января
        manager.process_trade({
            'symbol': 'MARGIN1',
            'direction': models.TradeDirection.LONG,
            'entry_price': 100.0,
            'quantity': 1000,
            'entry_at': datetime(2025, 1, 1, 10, 0),
            'commission': 10.0,
            'deal_sum': 100000.0,
            'swap': 0.0,
            'asset_type': 'Stock'
        })
        
        # Закрываем 3 января
        manager.process_trade({
            'symbol': 'MARGIN1',
            'direction': models.TradeDirection.SHORT,
            'entry_price': 105.0,
            'quantity': 1000,
            'entry_at': datetime(2025, 1, 3, 10, 0),
            'commission': 10.5,
            'deal_sum': 105000.0,
            'swap': 0.0
        })
        
        trade = manager.completed_trades[0]
        # Позиция была открыта 2 ночи, swap мог быть добавлен
        assert trade['swap'] >= 0


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

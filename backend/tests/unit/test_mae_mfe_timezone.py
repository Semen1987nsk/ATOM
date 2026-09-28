"""
MAE-01 (production-аудит 2026-06-10): времена сделок в БД хранятся UTC-naive
(trade_repo, import_service), а свечи MOEX ISS — в МСК. calculate_mae_mfe
обязан трактовать naive вход как UTC и сдвигать окно фильтра свечей на +3ч
(МСК), иначе окно бьёт мимо сделки и MAE/MFE считается по чужим свечам
либо не считается вовсе.

Регрессия: до фикса _to_msk трактовал naive как МСК — тесты ниже падали.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from market_service import MarketService


def _minute_candles_msk(start_msk: datetime, minutes: int, price: float = 100.0):
    """1-минутные свечи в шкале МСК (как отдаёт MOEX ISS)."""
    candles = []
    for i in range(minutes):
        begin = start_msk + timedelta(minutes=i)
        candles.append({
            "open": price, "close": price,
            "high": price + 1, "low": price - 1,
            "volume": 100,
            "begin": begin.strftime("%Y-%m-%d %H:%M:%S"),
            "end": (begin + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return candles


class TestMaeMfeNaiveUtcConvention:
    def setup_method(self):
        self.service = MarketService()

    @pytest.mark.asyncio
    @patch.object(MarketService, "get_candles")
    async def test_naive_utc_trade_finds_msk_candles(self, mock_get_candles):
        """Сделка 07:30–08:30 UTC = 10:30–11:30 МСК. Свечи существуют только
        в торговые часы МСК. До фикса окно 07:30–08:30 МСК → (None, None)."""
        # Свечи 10:00–12:00 МСК, 1-минутные
        mock_get_candles.return_value = _minute_candles_msk(
            datetime(2025, 12, 1, 10, 0, 0), minutes=120
        )

        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 7, 30, 0),   # naive UTC
            exit_time=datetime(2025, 12, 1, 8, 30, 0),    # naive UTC
        )

        assert mae is not None, (
            "naive-UTC вход должен конвертироваться в МСК-окно 10:30-11:30 "
            "и находить свечи"
        )
        assert mfe is not None

    @pytest.mark.asyncio
    @patch.object(MarketService, "get_candles")
    async def test_extreme_in_last_msk_hours_is_included(self, mock_get_candles):
        """Сделка 07:00–17:00 UTC = 10:00–20:00 МСК. Глобальный минимум 90.0
        в свече 18:30 МСК (внутри сделки). До фикса окно 07:00–17:00 МСК
        отрезало хвост 17:00–20:00 и MAE терял реальный экстремум."""
        candles = _minute_candles_msk(
            datetime(2025, 12, 1, 10, 0, 0), minutes=600, price=100.0
        )
        # Минимум в 18:30 МСК
        for c in candles:
            if c["begin"].startswith("2025-12-01 18:30"):
                c["low"] = 90.0
        mock_get_candles.return_value = candles

        mae, mfe = await self.service.calculate_mae_mfe(
            ticker="SBER",
            direction="LONG",
            entry_price=100.0,
            entry_time=datetime(2025, 12, 1, 7, 0, 0),    # naive UTC = 10:00 МСК
            exit_time=datetime(2025, 12, 1, 17, 0, 0),    # naive UTC = 20:00 МСК
        )

        assert mae == 90.0, (
            f"MAE должен видеть минимум 18:30 МСК (внутри сделки), получили {mae}"
        )

    def test_to_msk_naive_is_utc(self):
        """Контракт _to_msk: naive = UTC (конвенция БД), aware — astimezone."""
        naive_utc = datetime(2025, 12, 1, 7, 0, 0)
        msk = self.service._to_msk(naive_utc)
        assert msk.hour == 10, f"07:00 UTC = 10:00 МСК, получили {msk.hour}:00"
        assert msk.tzinfo is not None

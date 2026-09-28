"""
Практический пример: качаем минутные свечи SBER за вчерашний торговый день,
конвертируем в pandas DataFrame и сохраняем в CSV.

Запуск:
    python candles_fetch_example.py

Что демонстрирует:
  - Корректное определение «вчерашнего торгового дня» (с учётом выходных).
  - Использование MoexClient из moex_client.py.
  - Edge cases: пустой ответ, неполные свечи, сессия 10:00–18:50 MSK.
  - Конвертация ISS naive-MSK datetime в timezone-aware.

В Empirik эта логика частично есть в backend/routers/replay.py (загрузка свечей
для конкретной сделки), но там отсутствует pandas-аналитика — это
демо-скрипт для adhoc-исследований.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, time
from pathlib import Path

import pandas as pd
import pytz

from moex_client import MoexClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MSK = pytz.timezone("Europe/Moscow")

# Праздники МOEX 2025–2026 (минимум, для определения торгового дня).
# В Empirik полный set лежит в backend/market_service.py:MOEX_HOLIDAYS.
HOLIDAYS = {
    datetime(2025, 1, 1).date(),
    datetime(2025, 1, 2).date(),
    datetime(2025, 1, 3).date(),
    datetime(2025, 1, 6).date(),
    datetime(2025, 1, 7).date(),
    datetime(2025, 1, 8).date(),
    datetime(2025, 2, 24).date(),
    datetime(2025, 3, 10).date(),
    datetime(2025, 5, 1).date(),
    datetime(2025, 5, 2).date(),
    datetime(2025, 5, 9).date(),
    datetime(2025, 6, 12).date(),
    datetime(2025, 6, 13).date(),
    datetime(2025, 11, 3).date(),
    datetime(2025, 12, 31).date(),
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


def is_trading_day(d) -> bool:
    if d.weekday() >= 5:
        return False
    if d in HOLIDAYS:
        return False
    return True


def previous_trading_day(reference: datetime) -> datetime.date:
    """Возвращает дату предыдущего торгового дня от reference."""
    d = reference.date() - timedelta(days=1)
    for _ in range(14):
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)
    raise RuntimeError("Не нашёл торговый день в последних 14 днях")


async def fetch_sber_yesterday(out_csv: Path) -> pd.DataFrame:
    """
    Качает минутные свечи SBER за вчерашний торговый день.
    Окно: 10:00:00–18:50:00 MSK.
    """
    yesterday = previous_trading_day(datetime.now(MSK))
    from_dt = datetime.combine(yesterday, time(10, 0, 0))
    till_dt = datetime.combine(yesterday, time(18, 50, 0))

    logger.info("Fetching SBER candles for %s: %s — %s", yesterday, from_dt, till_dt)

    async with MoexClient() as moex:
        candles = await moex.get_candles(
            secid="SBER",
            from_dt=from_dt,
            till_dt=till_dt,
            interval=1,
            board="TQBR",
        )

    # Edge case: пустой ответ — нерабочий день несмотря на нашу проверку,
    # технические работы MOEX, делистинг.
    if not candles:
        logger.warning(
            "Свечи не получены. Возможные причины: технические работы ISS, "
            "перенос торгов, сетевая ошибка."
        )
        return pd.DataFrame()

    # Конвертация в DataFrame. begin/end naive-MSK → tz-aware MSK.
    df = pd.DataFrame(
        [
            {
                "begin_msk": MSK.localize(c.begin) if c.begin else None,
                "end_msk": MSK.localize(c.end) if c.end else None,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )

    # Edge case: неполные свечи. ISS может отдать свечу с volume=0
    # (отсутствие сделок в минуту) — оставляем, но помечаем.
    df["empty_minute"] = df["volume"] == 0

    # Edge case: дыра в данных. На MOEX обед или сбой.
    expected_minutes = int((till_dt - from_dt).total_seconds() / 60) + 1
    received = len(df)
    if received < expected_minutes * 0.9:
        logger.warning(
            "Получено %d свечей из ожидаемых ~%d (%.0f%%). "
            "Возможны дыры в данных.",
            received,
            expected_minutes,
            received / expected_minutes * 100,
        )

    # Базовая аналитика для CLI.
    if not df.empty:
        day_open = df.iloc[0]["open"]
        day_close = df.iloc[-1]["close"]
        day_high = df["high"].max()
        day_low = df["low"].min()
        total_volume = df["volume"].sum()
        change_pct = (day_close - day_open) / day_open * 100

        logger.info(
            "SBER %s: O=%.2f H=%.2f L=%.2f C=%.2f Vol=%.0f Change=%+.2f%%",
            yesterday,
            day_open,
            day_high,
            day_low,
            day_close,
            total_volume,
            change_pct,
        )

    df.to_csv(out_csv, index=False)
    logger.info("Saved %d rows to %s", len(df), out_csv)
    return df


async def main() -> None:
    out_csv = Path(__file__).parent / "sber_yesterday_1m.csv"
    df = await fetch_sber_yesterday(out_csv)

    if df.empty:
        return

    # Дополнительный пример: ресемплинг минутных свечей в 5-минутные локально.
    df5 = (
        df.set_index("begin_msk")
        .resample("5min")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open"])
    )
    out_csv_5m = out_csv.with_name("sber_yesterday_5m.csv")
    df5.to_csv(out_csv_5m)
    logger.info("Resampled to %d 5-minute candles -> %s", len(df5), out_csv_5m)


if __name__ == "__main__":
    asyncio.run(main())

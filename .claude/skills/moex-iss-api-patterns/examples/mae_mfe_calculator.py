"""
MAE/MFE calculator для конкретной сделки в Empirik.

Что внутри:
  - calculate_mae_mfe(trade) → MaeMfeResult.
  - Подбор интервала свечей под длительность сделки.
  - Конвертация UTC (БД) → MSK (свечи).
  - Фильтрация свечей строго внутри окна сделки.
  - Edge cases: сделка <1 минуты, через выходной, gap-открытие.

В Empirik эта логика уже есть в backend/market_service.py:calculate_mae_mfe (~170 строк),
но громоздкая и зависит от sync requests. Этот модуль — рефакторинг на async
с выделением чистых функций. План замены:

  1. Заменить get_moex_service().get_candles на MoexClient.get_candles.
  2. calculate_mae_mfe(...) ←→ Trade-like dataclass, не SQLAlchemy-объект.
  3. Тестируемо: можно мокнуть MoexClient через respx или httpx-mock.

Запуск как CLI:
    python mae_mfe_calculator.py SBER LONG 312.50 "2026-04-15T11:00:00" "2026-04-15T15:30:00"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional

import pytz

from moex_client import Candle, MoexClient

logger = logging.getLogger(__name__)

MSK = pytz.timezone("Europe/Moscow")
UTC = pytz.utc

Direction = Literal["LONG", "SHORT"]


# ════════════════════════════════════════════════════════════════════
#  Models
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TradeInput:
    """
    Минимальный набор полей сделки, нужный для MAE/MFE.

    entry_at, exit_at — UTC (как в БД Empirik).
    Если naive datetime — трактуется как MSK (для совместимости с тестами).
    """
    symbol: str
    direction: Direction
    entry_at: datetime
    exit_at: datetime
    entry_price: float
    exit_price: Optional[float] = None
    board: str = "TQBR"


@dataclass(frozen=True)
class MaeMfeResult:
    mae_price: Optional[float]    # худшая цена против позиции
    mfe_price: Optional[float]    # лучшая цена в нашу сторону
    mae_pct: Optional[float]      # абсолютная просадка от entry, %
    mfe_pct: Optional[float]      # абсолютный апсайд от entry, %
    candles_used: int             # сколько свечей участвовало
    interval: int                 # выбранный интервал свечей (1/10/60/24)
    warnings: list[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
#  Utils
# ════════════════════════════════════════════════════════════════════

def _to_msk_naive(dt: datetime) -> datetime:
    """
    Возвращает datetime в MSK без tzinfo — формат, в котором ISS ждёт даты
    в from/till и отдаёт их в begin/end свечей.
    """
    if dt.tzinfo is None:
        # naive — трактуем как MSK (соглашение Empirik).
        return dt
    return dt.astimezone(MSK).replace(tzinfo=None)


def _pick_interval(duration: timedelta) -> int:
    """
    Подбор интервала под длительность сделки.

    Цель: 100–500 свечей в окне. Меньше — теряем точность, больше —
    превышение лимита 500 свечей за запрос (нужна пагинация).
    """
    h = duration.total_seconds() / 3600
    if h <= 2:
        return 1   # 1m
    if h <= 24:
        return 10  # 10m
    if h <= 24 * 7:
        return 60  # 1h
    return 24      # 1d


def _crosses_weekend(entry_msk: datetime, exit_msk: datetime) -> bool:
    """Покрывает ли окно сделки субботу или воскресенье?"""
    cur = entry_msk.date()
    end = exit_msk.date()
    while cur <= end:
        if cur.weekday() >= 5:
            return True
        cur += timedelta(days=1)
    return False


# ════════════════════════════════════════════════════════════════════
#  Pure logic (тестируемо без сети)
# ════════════════════════════════════════════════════════════════════

def filter_candles_in_window(
    candles: list[Candle], entry_msk: datetime, exit_msk: datetime
) -> list[Candle]:
    """
    Оставляет ТОЛЬКО свечи, целиком лежащие внутри [entry, exit].

    Это критично для корректности: свеча захватывающая момент входа может
    содержать high/low ДО входа, что испортит MAE/MFE.
    """
    result: list[Candle] = []
    for c in candles:
        if c.begin is None or c.end is None:
            continue
        if entry_msk <= c.begin and c.end <= exit_msk:
            result.append(c)
    return result


def compute_mae_mfe(
    candles: list[Candle],
    direction: Direction,
    entry_price: float,
    exit_price: Optional[float] = None,
) -> tuple[Optional[float], Optional[float]]:
    """
    Чистая функция: по списку свечей и направлению возвращает (mae_price, mfe_price).
    """
    if not candles:
        return None, None

    highs = [c.high for c in candles if c.high is not None]
    lows = [c.low for c in candles if c.low is not None]
    if not highs or not lows:
        return None, None

    max_h = max(highs)
    min_l = min(lows)

    # Корректировка по exit_price: цена выхода точно достигалась.
    if exit_price is not None:
        if exit_price > max_h:
            max_h = exit_price
        if exit_price < min_l:
            min_l = exit_price

    if direction == "LONG":
        return min_l, max_h
    return max_h, min_l


def to_pct(price: Optional[float], entry_price: float, direction: Direction, kind: str) -> Optional[float]:
    """
    Конвертирует цену MAE/MFE в %% от entry_price.

    LONG MAE  = (entry - mae) / entry * 100  (просадка >0)
    LONG MFE  = (mfe - entry) / entry * 100  (рост >0)
    SHORT MAE = (mae - entry) / entry * 100
    SHORT MFE = (entry - mfe) / entry * 100
    """
    if price is None or entry_price <= 0:
        return None
    if direction == "LONG":
        delta = entry_price - price if kind == "mae" else price - entry_price
    else:
        delta = price - entry_price if kind == "mae" else entry_price - price
    return max(0.0, delta / entry_price * 100)


# ════════════════════════════════════════════════════════════════════
#  Main entrypoint
# ════════════════════════════════════════════════════════════════════

async def calculate_mae_mfe(trade: TradeInput, moex: MoexClient) -> MaeMfeResult:
    """
    Основной вычислитель MAE/MFE для одной сделки.

    Делает один запрос к ISS (без пагинации, расчёт на этом интервале).
    Если интервал 1m и сделка длинная (>500 минут) — переключается на 10m
    автоматически.
    """
    warnings: list[str] = []

    entry_msk = _to_msk_naive(trade.entry_at)
    exit_msk = _to_msk_naive(trade.exit_at)
    duration = exit_msk - entry_msk

    # Edge case: сделка короче минуты — невозможно посчитать.
    if duration < timedelta(minutes=1):
        warnings.append("Сделка короче 1 минуты — MAE/MFE недоступны.")
        return MaeMfeResult(None, None, None, None, 0, 0, warnings)

    if _crosses_weekend(entry_msk, exit_msk):
        warnings.append("Окно сделки покрывает выходной — возможны дыры в свечах.")

    interval = _pick_interval(duration)
    # Защита от 500-свечного потолка для 1m.
    if interval == 1 and duration > timedelta(minutes=480):
        interval = 10
        warnings.append("Длительность >8ч, переключился с 1m на 10m свечи.")

    # Расширяем окно на 1 минуту с каждой стороны: иначе свеча, идеально
    # совпадающая с entry, может быть отброшена filter_candles_in_window
    # из-за погрешности секунд.
    fetch_from = entry_msk - timedelta(minutes=1)
    fetch_till = exit_msk + timedelta(minutes=1)

    candles = await moex.get_candles(
        secid=trade.symbol,
        from_dt=fetch_from,
        till_dt=fetch_till,
        interval=interval,
        board=trade.board,
    )

    if not candles:
        warnings.append(
            f"Свечи для {trade.symbol} не получены "
            f"({fetch_from} – {fetch_till}, interval={interval})."
        )
        return MaeMfeResult(None, None, None, None, 0, interval, warnings)

    filtered = filter_candles_in_window(candles, entry_msk, exit_msk)

    # Edge case: в строгом окне свечей нет, а в расширенном — есть.
    # Чаще всего из-за gap-открытия (вход прямо на открытии бара).
    if not filtered and candles:
        warnings.append(
            "Нет свечей строго внутри [entry, exit] — возможно gap-открытие. "
            "Используем все полученные свечи."
        )
        filtered = candles

    mae_price, mfe_price = compute_mae_mfe(
        filtered, trade.direction, trade.entry_price, trade.exit_price
    )

    return MaeMfeResult(
        mae_price=mae_price,
        mfe_price=mfe_price,
        mae_pct=to_pct(mae_price, trade.entry_price, trade.direction, "mae"),
        mfe_pct=to_pct(mfe_price, trade.entry_price, trade.direction, "mfe"),
        candles_used=len(filtered),
        interval=interval,
        warnings=warnings,
    )


# ════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════

async def _cli(args: argparse.Namespace) -> None:
    entry_at = datetime.fromisoformat(args.entry_at)
    exit_at = datetime.fromisoformat(args.exit_at)
    trade = TradeInput(
        symbol=args.symbol,
        direction=args.direction,
        entry_at=entry_at,
        exit_at=exit_at,
        entry_price=args.entry_price,
        exit_price=args.exit_price,
    )
    async with MoexClient() as moex:
        res = await calculate_mae_mfe(trade, moex)

    print(f"Symbol:     {trade.symbol}")
    print(f"Direction:  {trade.direction}")
    print(f"Window:     {entry_at} → {exit_at}")
    print(f"Entry:      {trade.entry_price}")
    print(f"Interval:   {res.interval}m" if res.interval < 60 else f"Interval:   {res.interval/60}h")
    print(f"Candles:    {res.candles_used}")
    print(f"MAE:        {res.mae_price}  ({res.mae_pct:.2f}%)" if res.mae_price else "MAE:        n/a")
    print(f"MFE:        {res.mfe_price}  ({res.mfe_pct:.2f}%)" if res.mfe_price else "MFE:        n/a")
    if res.warnings:
        print("Warnings:")
        for w in res.warnings:
            print(f"  - {w}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="MAE/MFE for a single trade")
    p.add_argument("symbol")
    p.add_argument("direction", choices=["LONG", "SHORT"])
    p.add_argument("entry_price", type=float)
    p.add_argument("entry_at", help="ISO datetime, e.g. 2026-04-15T11:00:00")
    p.add_argument("exit_at", help="ISO datetime, e.g. 2026-04-15T15:30:00")
    p.add_argument("--exit-price", dest="exit_price", type=float, default=None)
    args = p.parse_args()
    asyncio.run(_cli(args))


if __name__ == "__main__":
    main()

"""
PnL Service — единый источник правды для всех PnL расчётов.

Централизует логику вычисления PnL, net_pnl, point_value
для акций, фьючерсов, частичного и полного закрытия.

Используется в:
- routers/trades.py  (close, partial close, create opposite)
- routers/real_pnl.py (recalculate)
- tinkoff_service.py  (sync)
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple
import logging

from moex_service import get_moex_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Point Value
# ──────────────────────────────────────────────

def get_point_value(symbol: str) -> Decimal:
    """
    Возвращает стоимость одного пункта цены для инструмента.

    - Акции / облигации / ETF → 1
    - Фьючерсы → min_price_increment_amount / min_price_increment
      (сначала живой MOEX ISS, потом fallback-таблица)
    """
    moex = get_moex_service()
    if moex.is_futures_ticker(symbol):
        return moex.get_point_value(symbol)
    return Decimal(1)


# ──────────────────────────────────────────────
#  Gross PnL
# ──────────────────────────────────────────────

def calculate_gross_pnl(
    entry_price: float,
    exit_price: float,
    quantity: float,
    direction: str,
    symbol: str,
) -> float:
    """
    Рассчитывает *валовый* (gross) PnL для одной сделки.

    Формула:
      gross_pnl = price_diff × quantity × point_value

    Где price_diff = exit − entry  (для LONG)
                   = entry − exit  (для SHORT)

    Args:
        entry_price: Цена входа (средневзвешенная при усреднении).
        exit_price:  Цена выхода.
        quantity:    Количество (контрактов / лотов / штук).
        direction:   "LONG" | "SHORT" (или enum с .value).
        symbol:      Тикер инструмента (SiH5, SBER, и т.д.).

    Returns:
        Gross PnL в виде float, округлённый до 2 знаков.
    """
    pv = get_point_value(symbol)

    ep = Decimal(str(entry_price))
    xp = Decimal(str(exit_price))
    qty = Decimal(str(quantity))

    price_diff = xp - ep
    if _is_short(direction):
        price_diff = -price_diff

    gross = price_diff * qty * pv
    return float(gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ──────────────────────────────────────────────
#  Net PnL
# ──────────────────────────────────────────────

def calculate_net_pnl(
    gross_pnl: float,
    commission: float = 0.0,
    swap: float = 0.0,
) -> float:
    """
    Net PnL = Gross PnL − Commission − Swap.

    Все аргументы — абсолютные значения (комиссия ≥ 0).
    """
    net = Decimal(str(gross_pnl)) - Decimal(str(commission)) - Decimal(str(swap))
    return float(net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ──────────────────────────────────────────────
#  Complete close — заполняет модель Trade
# ──────────────────────────────────────────────

def apply_close_pnl(trade, exit_commission: float = 0.0) -> None:
    """
    Проставляет pnl и net_pnl на модели Trade при полном закрытии.

    Ожидает, что trade уже имеет:
      - entry_price, exit_price, quantity, direction, symbol
      - commission (entry-side, уже записанная)
      - swap

    Дополнительно:
      - exit_commission добавляется к общей комиссии.

    Мутирует trade in-place (не возвращает значение).

    Raises:
        ValueError: if required fields (entry_price, exit_price, quantity, direction, symbol) are None.
    """
    # Validate required fields
    for field in ('entry_price', 'exit_price', 'quantity', 'direction', 'symbol'):
        if getattr(trade, field, None) is None:
            raise ValueError(f"Cannot calculate PnL: trade.{field} is None (trade id={getattr(trade, 'id', '?')})")

    gross = calculate_gross_pnl(
        entry_price=float(trade.entry_price),
        exit_price=float(trade.exit_price),
        quantity=float(trade.quantity),
        direction=_direction_str(trade.direction),
        symbol=trade.symbol,
    )
    trade.pnl = gross

    # Обновляем комиссию выхода
    trade.exit_commission = float(trade.exit_commission or 0) + exit_commission
    trade.commission = float(trade.commission or 0) + exit_commission

    total_commission = float(trade.commission or 0)
    total_swap = float(trade.swap or 0)

    trade.net_pnl = calculate_net_pnl(gross, total_commission, total_swap)


def apply_partial_close_pnl(
    closed_trade,
    original_trade,
    close_quantity: float,
    exit_commission: float = 0.0,
) -> None:
    """
    Проставляет pnl и net_pnl при частичном закрытии (split).

    closed_trade — новый объект Trade, созданный для закрытой части.
    original_trade — исходная открытая сделка (уменьшаем quantity).

    Логика:
      1. Пропорционально делим entry_commission.
      2. Добавляем exit_commission к closed_trade.
      3. Считаем gross и net PnL для closed_trade.
      4. Уменьшаем quantity original_trade.
    """
    available_qty = float(original_trade.quantity)
    ratio = close_quantity / available_qty if available_qty else 0.0

    # ── Split entry commission ──
    original_entry_comm = float(original_trade.entry_commission or 0)
    part_entry_comm = original_entry_comm * ratio
    closed_trade.entry_commission = part_entry_comm

    # Уменьшаем комиссию на исходной сделке
    original_trade.entry_commission = original_entry_comm - part_entry_comm
    original_trade.commission = float(original_trade.commission or 0) - part_entry_comm

    # ── Exit commission ──
    closed_trade.exit_commission = exit_commission
    closed_trade.commission = part_entry_comm + exit_commission

    # ── Swap: пропорционально ──
    original_swap = float(original_trade.swap or 0)
    part_swap = original_swap * ratio
    closed_trade.swap = part_swap
    original_trade.swap = original_swap - part_swap

    # ── PnL ──
    gross = calculate_gross_pnl(
        entry_price=float(closed_trade.entry_price),
        exit_price=float(closed_trade.exit_price),
        quantity=close_quantity,
        direction=_direction_str(closed_trade.direction),
        symbol=closed_trade.symbol,
    )
    closed_trade.pnl = gross
    closed_trade.net_pnl = calculate_net_pnl(
        gross,
        commission=float(closed_trade.commission or 0),
        swap=float(closed_trade.swap or 0),
    )

    # ── Уменьшаем quantity исходной сделки ──
    original_trade.quantity = available_qty - close_quantity


# ──────────────────────────────────────────────
#  Recalculate (bulk)
# ──────────────────────────────────────────────

def recalculate_trade_pnl(trade) -> Tuple[float, float]:
    """
    Пересчитывает pnl и net_pnl для уже закрытой сделки.
    Возвращает (new_pnl, new_net_pnl).

    Используется в POST /real-pnl/recalculate для массового
    пересчёта фьючерсных сделок с правильным point_value.

    Raises:
        ValueError: if required fields are None.
    """
    for field in ('entry_price', 'exit_price', 'quantity', 'direction', 'symbol'):
        if getattr(trade, field, None) is None:
            raise ValueError(f"Cannot recalculate PnL: trade.{field} is None (trade id={getattr(trade, 'id', '?')})")

    gross = calculate_gross_pnl(
        entry_price=float(trade.entry_price),
        exit_price=float(trade.exit_price),
        quantity=float(trade.quantity),
        direction=_direction_str(trade.direction),
        symbol=trade.symbol,
    )
    commission = float(trade.commission or 0)
    swap = float(trade.swap or 0)
    net = calculate_net_pnl(gross, commission, swap)
    return gross, net


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _is_short(direction) -> bool:
    """Универсальный хелпер: принимает enum, str, и т.д."""
    d = direction.value if hasattr(direction, "value") else str(direction)
    return d.upper() == "SHORT"


def _direction_str(direction) -> str:
    """Превращает enum / str в 'LONG' или 'SHORT'."""
    d = direction.value if hasattr(direction, "value") else str(direction)
    return d.upper()

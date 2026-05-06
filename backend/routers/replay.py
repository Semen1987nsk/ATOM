"""
Trade Replay — свечи MOEX вокруг сделки + маркеры entry/exit/SL/TP/MAE/MFE.

Используется на странице /trades/{id}/replay во фронте: показать график цены
с отметками, чтобы трейдер мог визуально оценить «куда я попал, где SL, где
вытаскивал стоп, был ли MAE раньше точки выхода и т.д.».
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database
import models
import auth_service
from logger import get_logger
from moex_service import get_moex_service

log = get_logger("replay")

router = APIRouter(prefix="/trades", tags=["trades"])


class Candle(BaseModel):
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float


class Marker(BaseModel):
    type: str   # entry / exit / sl / tp / mae / mfe
    t: Optional[datetime] = None  # время (для entry/exit/mae/mfe)
    price: float
    label: str


class ReplayResponse(BaseModel):
    trade_id: int
    symbol: str
    direction: str
    interval: str
    interval_auto: bool
    range_start: datetime
    range_end: datetime
    candles: List[Candle]
    markers: List[Marker]
    is_open: bool
    note: Optional[str] = None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.get("/{trade_id}/replay", response_model=ReplayResponse)
def get_trade_replay(
    trade_id: int,
    interval: Optional[str] = Query(None, description="1m/10m/1h/1d/1w/1mo. Пусто = авто."),
    pad_minutes: int = Query(60, ge=0, le=1440, description="Сколько минут до/после сделки добавить в окно."),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    account_id = auth_service.get_account_id(db, current_user)
    trade = (
        db.query(models.Trade)
        .filter(models.Trade.id == trade_id, models.Trade.account_id == account_id)
        .first()
    )
    if not trade:
        raise HTTPException(status_code=404, detail="Сделка не найдена")

    if not trade.entry_at:
        raise HTTPException(status_code=400, detail="У сделки нет даты входа — нечего реплеить.")

    moex = get_moex_service()

    # Окно: entry_at - pad ... exit_at + pad (или now, если открыта).
    is_open = trade.exit_at is None
    end_anchor = trade.exit_at if trade.exit_at else datetime.utcnow()
    range_start = trade.entry_at - timedelta(minutes=pad_minutes)
    range_end = end_anchor + timedelta(minutes=pad_minutes)
    span = range_end - range_start

    # Авто-разрешение свечей под длину окна.
    interval_auto = interval is None
    chosen = interval or moex.auto_interval(span)

    candles_raw = moex.get_candles(
        ticker=trade.symbol,
        interval=chosen,
        start=range_start,
        end=range_end,
    )
    note = None
    if not candles_raw:
        note = (
            f"Свечей для {trade.symbol} в диапазоне {range_start:%Y-%m-%d}–{range_end:%Y-%m-%d} нет. "
            "Возможные причины: тикер не торгуется на MOEX, выходные/праздники, или нерыночное окно."
        )

    candles = []
    for c in candles_raw:
        # MOEX отдаёт datetime в виде строки 'YYYY-MM-DD HH:MM:SS' — pydantic сам распарсит.
        candles.append(Candle(t=c["t"], o=c["o"], h=c["h"], l=c["l"], c=c["c"], v=c["v"]))

    # Маркеры. None-цены не рисуем.
    markers: List[Marker] = []

    entry_price = _to_float(trade.entry_price)
    if entry_price is not None:
        markers.append(Marker(type="entry", t=trade.entry_at, price=entry_price, label="Вход"))

    exit_price = _to_float(trade.exit_price)
    if exit_price is not None and trade.exit_at:
        markers.append(Marker(type="exit", t=trade.exit_at, price=exit_price, label="Выход"))

    sl = _to_float(trade.stop_loss)
    if sl is not None:
        markers.append(Marker(type="sl", price=sl, label="Stop Loss"))

    tp = _to_float(trade.take_profit)
    if tp is not None:
        markers.append(Marker(type="tp", price=tp, label="Take Profit"))

    mae = _to_float(trade.mae_price)
    if mae is not None:
        markers.append(Marker(type="mae", price=mae, label="MAE (худшая)"))

    mfe = _to_float(trade.mfe_price)
    if mfe is not None:
        markers.append(Marker(type="mfe", price=mfe, label="MFE (лучшая)"))

    direction_str = trade.direction.value if hasattr(trade.direction, "value") else str(trade.direction)

    return ReplayResponse(
        trade_id=trade.id,
        symbol=trade.symbol,
        direction=direction_str,
        interval=chosen,
        interval_auto=interval_auto,
        range_start=range_start,
        range_end=range_end,
        candles=candles,
        markers=markers,
        is_open=is_open,
        note=note,
    )

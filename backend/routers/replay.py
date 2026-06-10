"""
Trade Replay — свечи MOEX вокруг сделки + маркеры entry/exit/SL/TP/MAE/MFE.

Используется на странице /trades/{id}/replay во фронте: показать график цены
с отметками, чтобы трейдер мог визуально оценить «куда я попал, где SL, где
вытаскивал стоп, был ли MAE раньше точки выхода и т.д.».
"""
from datetime import datetime, timedelta
from typing import List, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database
import models
import auth_service
from logger import get_logger
from moex_service import get_moex_service

log = get_logger("replay")

MSK_TZ = pytz.timezone("Europe/Moscow")


def _utc_to_msk_naive(dt: datetime) -> datetime:
    """UTC-naive (конвенция БД) → naive-МСК — та же шкала, что строки свечей ISS.

    MAE-02: свечи MOEX приходят в МСК, а времена сделок в БД — UTC. Если отдать
    маркеры/окно как есть, фронт строит ось по new Date() для обеих величин и
    маркер входа встаёт на 3 часа левее реальной свечи."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(MSK_TZ).replace(tzinfo=None)

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
async def get_trade_replay(
    trade_id: int,
    interval: Optional[str] = Query(None, description="1m/10m/1h/1d/1w/1mo. Пусто = авто."),
    pad_minutes: int = Query(60, ge=0, le=1440, description="Сколько минут до/после сделки добавить в окно."),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    # SYNC-04 (Task 1.3): handler async, потому что moex.get_candles теперь async.
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
    # Всё окно и маркеры — в naive-МСК (шкала свечей ISS), см. _utc_to_msk_naive.
    is_open = trade.exit_at is None
    end_anchor = trade.exit_at if trade.exit_at else datetime.utcnow()
    entry_msk = _utc_to_msk_naive(trade.entry_at)
    end_anchor_msk = _utc_to_msk_naive(end_anchor)
    exit_msk = _utc_to_msk_naive(trade.exit_at) if trade.exit_at else None
    range_start = entry_msk - timedelta(minutes=pad_minutes)
    range_end = end_anchor_msk + timedelta(minutes=pad_minutes)
    span = range_end - range_start

    # Авто-разрешение свечей под длину окна.
    interval_auto = interval is None
    chosen = interval or moex.auto_interval(span)

    candles_raw = await moex.get_candles(
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
        markers.append(Marker(type="entry", t=entry_msk, price=entry_price, label="Вход"))

    exit_price = _to_float(trade.exit_price)
    if exit_price is not None and exit_msk is not None:
        markers.append(Marker(type="exit", t=exit_msk, price=exit_price, label="Выход"))

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

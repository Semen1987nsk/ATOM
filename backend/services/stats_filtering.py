"""
Общие хелперы для роутеров статистики.

Вынесено из routers/stats.py чтобы переиспользовать в stats_advanced и т.д.
без cross-router импортов и циклов.

API публичный (без префикса `_`). Старые роутеры импортируют через алиасы:

    from services.stats_filtering import (
        load_filtered_trades as _load_filtered_trades,
        build_equity_curve as _build_equity_curve,
    )
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from utils.datetime_utils import utc_now_naive


def load_filtered_trades(
    db: Session,
    account_id: int,
    period: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    start_trade_id: Optional[int],
    tag: Optional[str],
    limit: Optional[int],
) -> List[models.Trade]:
    """Единственный источник правды для фильтрации трейдов по периоду/тегу/лимиту.

    Возвращает список Trade с непустым PnL, отсортированный по entry_at ASC.
    """
    date_filter: Optional[datetime] = None
    now = utc_now_naive()

    if start_trade_id:
        st = db.query(models.Trade).filter(
            models.Trade.id == start_trade_id,
            models.Trade.account_id == account_id,
        ).first()
        if st:
            date_filter = st.entry_at
    elif period == "today":
        date_filter = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        date_filter = now - timedelta(days=7)
    elif period == "month":
        date_filter = now - timedelta(days=30)
    elif period == "3months":
        date_filter = now - timedelta(days=90)
    elif period == "year":
        date_filter = now - timedelta(days=365)
    elif period == "custom" and start_date:
        try:
            date_filter = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass

    q = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.pnl != None,  # noqa: E711 — SQLAlchemy column != None требует именно так
    )
    if date_filter:
        q = q.filter(
            (models.Trade.exit_at >= date_filter)
            | ((models.Trade.exit_at == None) & (models.Trade.entry_at >= date_filter))  # noqa: E711
        )
    if period == "custom" and end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(
                (models.Trade.exit_at < end_dt)
                | ((models.Trade.exit_at == None) & (models.Trade.entry_at < end_dt))  # noqa: E711
            )
        except ValueError:
            pass

    trades = q.order_by(models.Trade.entry_at.asc()).all()
    if tag:
        tl = tag.lower()
        trades = [t for t in trades if t.tags and any(tg.lower() == tl for tg in t.tags)]
    if limit and limit > 0:
        trades = trades[-limit:]
    return trades


def build_equity_curve(trades) -> list:
    """Кумулятивный баланс по PnL (без учёта депозитов — для DD-метрик это и нужно)."""
    eq: list = []
    running = 0.0
    for t in trades:
        pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
        running += pnl
        eq.append(running)
    return eq

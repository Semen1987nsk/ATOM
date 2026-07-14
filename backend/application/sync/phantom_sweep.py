"""close_phantom_trades: новый этап sync pipeline.

После _stage_mark_to_market закрывает Trade rows, у которых exit_at=None,
но соответствующей позиции нет в Position table. Это означает что Тинькофф
закрыл позицию, а SELL operation в Operations API задержалась.

Best-effort exit_price: last_known_price (из Position.current_price если
есть recent snapshot), fallback на entry_price (P&L = -commission).

Идемпотентно: повторный запуск не двигает уже закрытые Trade rows.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy.orm import Session

import models
from logger import get_logger
from application.sync.phantom_sweep_helpers import (
    last_known_price, has_recent_operations,
)

log = get_logger("phantom_sweep")


def close_phantom_trades(
    session: Session,
    *,
    account_id: int,
    point_value_for: Callable[[Optional[str]], Decimal],
    now: datetime,
) -> int:
    """Закрыть Trade.exit_at=None если нет matching Position.

    Returns: количество закрытых phantom trades.
    """
    live_uids = {
        p.instrument_uid for p in session.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        ).all()
    }

    if not live_uids and has_recent_operations(session, account_id, hours=24, now=now):
        log.warning(
            "phantom_sweep.skipped_empty_positions",
            extra={"account_id": account_id},
        )
        return 0

    open_trades = session.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.is_(None),
    ).all()
    phantoms = [t for t in open_trades if t.instrument_uid not in live_uids]
    if not phantoms:
        return 0

    closed = 0
    for trade in phantoms:
        exit_price = last_known_price(session, trade.instrument_uid)
        if exit_price is None:
            exit_price = Decimal(str(trade.entry_price))

        pv = point_value_for(trade.instrument_uid) if trade.instrument_uid else Decimal(1)
        body_pnl = (
            (exit_price - Decimal(str(trade.entry_price)))
            * Decimal(str(trade.quantity)) * pv
        )
        if trade.direction == models.TradeDirection.SHORT:
            body_pnl = -body_pnl

        commission = abs(Decimal(str(trade.commission or 0)))
        attributed = (
            Decimal(str(trade.varmargin_attributed or 0))
            + Decimal(str(trade.margin_fee_attributed or 0))
            + Decimal(str(trade.service_fee_attributed or 0))
            + Decimal(str(trade.other_fees_attributed or 0))
        )

        trade.exit_at = now
        trade.exit_price = exit_price
        trade.pnl = body_pnl
        trade.net_pnl = body_pnl - commission + attributed
        trade.exit_reason = "phantom_sweep"
        tags = list(trade.tags or [])
        if "phantom_sweep" not in tags:
            tags.append("phantom_sweep")
        trade.tags = tags

        log.warning(
            "phantom_trade_swept",
            extra={
                "trade_id": trade.id,
                "instrument_uid": trade.instrument_uid,
                "entry_price": str(trade.entry_price),
                "exit_price": str(exit_price),
                "net_pnl": str(trade.net_pnl),
            },
        )
        closed += 1

    session.flush()
    return closed

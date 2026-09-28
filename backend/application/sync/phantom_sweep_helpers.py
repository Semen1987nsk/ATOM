"""Helpers для _stage_close_phantom_trades.

Минимальный модуль, не тянет лишних зависимостей. Тестируется отдельно.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

import models


def last_known_price(session: Session, instrument_uid: str) -> Optional[Decimal]:
    """Последняя known цена инструмента из Position.current_price.

    Если позиция уже закрыта (Position row удалён) — возвращает None.
    Caller fallback'ит на Trade.entry_price.
    """
    pos = session.query(models.PositionORM).filter(
        models.PositionORM.instrument_uid == instrument_uid,
    ).first()
    if pos is None or pos.current_price is None:
        return None
    return Decimal(str(pos.current_price))


def has_recent_operations(
    session: Session, account_id: int, hours: int = 24,
    now: Optional[datetime] = None,
) -> bool:
    """Есть ли operations в последние `hours` часов для account.

    Используется как защита от Tinkoff Portfolio blip: если Position table
    стал пустым из-за временной ошибки API, а в Operations есть recent
    активность — sweep НЕ делаем.
    """
    cutoff = (now or datetime.utcnow()) - timedelta(hours=hours)
    count = session.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.executed_at >= cutoff,
    ).limit(1).count()
    return count > 0

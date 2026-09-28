"""
Открытые позиции (PR 12).

`GET /positions` возвращает список открытых позиций с MTM (PR 11):
* current_price, unrealized_pnl, last_priced_at,
* avg_entry_price, signed quantity,
* инструмент: ticker / name / type из локального кэша справочника.

Не дёргает Tinkoff API — берёт данные из локальной БД (которую обновляет
pipeline на каждом sync). Это даёт быстрый отклик в UI и не упирается
в rate-limit.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

import models
from auth_service import get_current_user, get_user_account
from database import get_db
from models import InstrumentORM, PositionORM

router = APIRouter(prefix="/positions", tags=["positions"])


class PositionResponse(BaseModel):
    instrument_uid: str
    instrument_type: str
    figi: Optional[str] = None
    ticker: Optional[str] = None
    name: Optional[str] = None
    quantity: int  # signed: + LONG, - SHORT
    avg_entry_price: str  # Decimal as str (JSON-safe)
    current_price: Optional[str] = None
    unrealized_pnl: Optional[str] = None
    unrealized_pnl_percent: Optional[float] = None
    last_priced_at: Optional[str] = None
    currency: str = "rub"

    model_config = ConfigDict(from_attributes=False)


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    account = get_user_account(db, current_user)
    rows = (
        db.query(PositionORM, InstrumentORM)
        .outerjoin(InstrumentORM, InstrumentORM.uid == PositionORM.instrument_uid)
        .filter(PositionORM.account_id == account.id)
        .all()
    )

    result: list[PositionResponse] = []
    for pos, instr in rows:
        avg_entry = pos.avg_entry_price
        current = pos.current_price
        unr = pos.unrealized_pnl
        pct = None
        if (
            avg_entry is not None
            and current is not None
            and float(avg_entry) > 0
        ):
            pct = round((float(current) - float(avg_entry)) / float(avg_entry) * 100, 4)
        result.append(
            PositionResponse(
                instrument_uid=pos.instrument_uid,
                instrument_type=pos.instrument_type,
                figi=(instr.figi if instr else None),
                ticker=(instr.ticker if instr else None),
                name=(instr.name if instr else None),
                quantity=pos.quantity,
                avg_entry_price=str(avg_entry),
                current_price=str(current) if current is not None else None,
                unrealized_pnl=str(unr) if unr is not None else None,
                unrealized_pnl_percent=pct,
                last_priced_at=pos.last_priced_at.isoformat() if pos.last_priced_at else None,
                currency=pos.currency or "rub",
            )
        )
    return result

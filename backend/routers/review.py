"""
routers.review — Daily Review workflow.

Дневная рефлексия: список сделок + поле reflection + per-trade comments + intention.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from sqlalchemy.orm.attributes import flag_modified

import database
import models
import auth_service

router = APIRouter(prefix="/review", tags=["review"])


class TradeMini(BaseModel):
    id: int
    symbol: str
    direction: str
    pnl: Optional[float]
    entry_at: str
    exit_at: Optional[str]
    setup_name: Optional[str]
    reflection: str = ""

    model_config = {"from_attributes": True}


class DailyReviewOut(BaseModel):
    date: str
    reflection: str
    intention: str
    rating: Optional[int]
    trades: list[TradeMini]
    summary: dict


class SaveReviewIn(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    reflection: Optional[str] = None
    intention: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    trade_reflections: Optional[Dict[str, str]] = None


@router.get("/", response_model=DailyReviewOut)
def get_review(
    date: Optional[str] = None,  # YYYY-MM-DD; default = today
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """Возвращает review за день + список сделок этого дня."""
    target_date = date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Дата должна быть в формате YYYY-MM-DD")

    account_id = auth_service.get_account_id(db, current_user)

    # Загружаем review
    rev = db.query(models.DailyReview).filter(
        models.DailyReview.account_id == account_id,
        models.DailyReview.date == target_date,
    ).first()

    # Загружаем сделки этого дня (entry_at OR exit_at в этот день)
    next_day = date_obj + timedelta(days=1)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        ((models.Trade.entry_at >= date_obj) & (models.Trade.entry_at < next_day))
        | ((models.Trade.exit_at >= date_obj) & (models.Trade.exit_at < next_day)),
    ).order_by(models.Trade.entry_at.asc()).all()

    trade_reflections: Dict[str, str] = (rev.trade_reflections if rev and rev.trade_reflections else {}) or {}

    trades_out = [
        TradeMini(
            id=t.id,
            symbol=t.symbol,
            direction=t.direction.value if hasattr(t.direction, "value") else str(t.direction),
            pnl=float(t.pnl) if t.pnl is not None else None,
            entry_at=t.entry_at.isoformat() if t.entry_at else "",
            exit_at=t.exit_at.isoformat() if t.exit_at else None,
            setup_name=t.setup_name,
            reflection=trade_reflections.get(str(t.id), ""),
        )
        for t in trades
    ]

    pnls = [float(t.pnl or 0) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    summary = {
        "total_trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
        "total_pnl": round(sum(pnls), 2),
    }

    return DailyReviewOut(
        date=target_date,
        reflection=rev.reflection if rev else "",
        intention=rev.intention if rev else "",
        rating=rev.rating if rev else None,
        trades=trades_out,
        summary=summary,
    )


@router.post("/", response_model=DailyReviewOut)
def save_review(
    payload: SaveReviewIn,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """Сохраняет/обновляет review."""
    account_id = auth_service.get_account_id(db, current_user)

    rev = db.query(models.DailyReview).filter(
        models.DailyReview.account_id == account_id,
        models.DailyReview.date == payload.date,
    ).first()

    if not rev:
        rev = models.DailyReview(account_id=account_id, date=payload.date)
        db.add(rev)

    if payload.reflection is not None:
        rev.reflection = payload.reflection
    if payload.intention is not None:
        rev.intention = payload.intention
    if payload.rating is not None:
        rev.rating = payload.rating
    if payload.trade_reflections is not None:
        # merge, не replace — чтобы при сохранении одной сделки остальные не потерять
        existing = (rev.trade_reflections or {}) if isinstance(rev.trade_reflections, dict) else {}
        existing.update(payload.trade_reflections)
        rev.trade_reflections = existing
        flag_modified(rev, "trade_reflections")

    db.commit()
    db.refresh(rev)

    # Возвращаем полный ответ через get_review
    return get_review(payload.date, db, current_user)

"""
Р РѕСѓС‚РµСЂ РґР»СЏ СѓРїСЂР°РІР»РµРЅРёСЏ РґРµРїРѕР·РёС‚РѕРј Рё РёСЃС‚РѕСЂРёРµР№ РёР·РјРµРЅРµРЅРёР№.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

import database
import models
import schemas
import auth_service

router = APIRouter(prefix="/deposits", tags=["deposits"])


# get_account_id is now centralized in auth_service

@router.get("/balance", response_model=schemas.AccountBalanceResponse)
def get_balance(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """РџРѕР»СѓС‡РёС‚СЊ С‚РµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ Рё СЃС‚Р°С‚РёСЃС‚РёРєСѓ РґРµРїРѕР·РёС‚Р°"""
    account_id = auth_service.get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="РђРєРєР°СѓРЅС‚ РЅРµ РЅР°Р№РґРµРЅ")
    
    # РЎСѓРјРјР° РІСЃРµС… РїРѕРїРѕР»РЅРµРЅРёР№
    total_deposits = db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.DEPOSIT
    ).scalar() or 0
    
    # РЎСѓРјРјР° РІСЃРµС… СЃРЅСЏС‚РёР№ (Р°Р±СЃРѕР»СЋС‚РЅРѕРµ Р·РЅР°С‡РµРЅРёРµ)
    total_withdrawals = abs(db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.WITHDRAWAL
    ).scalar() or 0)
    
    # РЎСѓРјРјР° PnL РёР· Р·Р°РєСЂС‹С‚С‹С… СЃРґРµР»РѕРє
    total_pnl = db.query(func.coalesce(func.sum(models.Trade.net_pnl), 0)).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None)
    ).scalar() or 0
    
    initial = float(account.initial_balance or 0)
    current = initial + float(total_deposits) - float(total_withdrawals) + float(total_pnl)
    
    return {
        "account_id": account_id,
        "initial_balance": initial,
        "current_balance": current,
        "total_deposits": float(total_deposits),
        "total_withdrawals": float(total_withdrawals),
        "total_pnl": float(total_pnl),
        "currency": account.currency
    }


@router.post("/initial")
def set_initial_balance(
    amount: float,
    date: Optional[datetime] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """РЈСЃС‚Р°РЅРѕРІРёС‚СЊ РЅР°С‡Р°Р»СЊРЅС‹Р№ РґРµРїРѕР·РёС‚"""
    account_id = auth_service.get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="РђРєРєР°СѓРЅС‚ РЅРµ РЅР°Р№РґРµРЅ")
    
    operation_date = date or datetime.utcnow()
    
    # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё СѓР¶Рµ РЅР°С‡Р°Р»СЊРЅС‹Р№ РґРµРїРѕР·РёС‚
    existing = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.INITIAL
    ).first()
    
    if existing:
        # РћР±РЅРѕРІР»СЏРµРј СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёР№
        existing.amount = amount
        existing.balance_after = amount
        existing.date = operation_date
        account.initial_balance = amount
    else:
        # РЎРѕР·РґР°С‘Рј РЅРѕРІС‹Р№
        history = models.DepositHistory(
            account_id=account_id,
            operation_type=models.DepositOperationType.INITIAL,
            amount=amount,
            balance_after=amount,
            date=operation_date,
            note="РќР°С‡Р°Р»СЊРЅС‹Р№ РґРµРїРѕР·РёС‚"
        )
        db.add(history)
        account.initial_balance = amount
    
    db.commit()
    
    return {"message": f"РќР°С‡Р°Р»СЊРЅС‹Р№ РґРµРїРѕР·РёС‚ СѓСЃС‚Р°РЅРѕРІР»РµРЅ: {amount}", "initial_balance": amount}


@router.post("/add")
def add_deposit(
    amount: float,
    date: datetime,
    note: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Р”РѕР±Р°РІРёС‚СЊ РїРѕРїРѕР»РЅРµРЅРёРµ РґРµРїРѕР·РёС‚Р°"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="РЎСѓРјРјР° РїРѕРїРѕР»РЅРµРЅРёСЏ РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РїРѕР»РѕР¶РёС‚РµР»СЊРЅРѕР№")
    
    account_id = auth_service.get_account_id(db, current_user)
    
    # РџРѕР»СѓС‡Р°РµРј С‚РµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ РЅР° СЌС‚Сѓ РґР°С‚Сѓ
    balance_info = _calculate_balance_at_date(db, account_id, date)
    new_balance = balance_info + amount
    
    history = models.DepositHistory(
        account_id=account_id,
        operation_type=models.DepositOperationType.DEPOSIT,
        amount=amount,
        balance_after=new_balance,
        date=date,
        note=note or "РџРѕРїРѕР»РЅРµРЅРёРµ"
    )
    db.add(history)
    db.commit()
    
    return {"message": f"РџРѕРїРѕР»РЅРµРЅРёРµ РґРѕР±Р°РІР»РµРЅРѕ: +{amount}", "balance_after": new_balance}


@router.post("/withdraw")
def add_withdrawal(
    amount: float,
    date: datetime,
    note: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Р”РѕР±Р°РІРёС‚СЊ СЃРЅСЏС‚РёРµ СЃ РґРµРїРѕР·РёС‚Р°"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="РЎСѓРјРјР° СЃРЅСЏС‚РёСЏ РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РїРѕР»РѕР¶РёС‚РµР»СЊРЅРѕР№")
    
    account_id = auth_service.get_account_id(db, current_user)
    
    # РџРѕР»СѓС‡Р°РµРј С‚РµРєСѓС‰РёР№ Р±Р°Р»Р°РЅСЃ РЅР° СЌС‚Сѓ РґР°С‚Сѓ
    balance_info = _calculate_balance_at_date(db, account_id, date)
    new_balance = balance_info - amount
    
    history = models.DepositHistory(
        account_id=account_id,
        operation_type=models.DepositOperationType.WITHDRAWAL,
        amount=-amount,  # РћС‚СЂРёС†Р°С‚РµР»СЊРЅРѕРµ Р·РЅР°С‡РµРЅРёРµ
        balance_after=new_balance,
        date=date,
        note=note or "РЎРЅСЏС‚РёРµ"
    )
    db.add(history)
    db.commit()
    
    return {"message": f"РЎРЅСЏС‚РёРµ РґРѕР±Р°РІР»РµРЅРѕ: -{amount}", "balance_after": new_balance}


@router.get("/history", response_model=List[schemas.DepositOperationResponse])
def get_deposit_history(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """РџРѕР»СѓС‡РёС‚СЊ РёСЃС‚РѕСЂРёСЋ РѕРїРµСЂР°С†РёР№ СЃ РґРµРїРѕР·РёС‚РѕРј"""
    account_id = auth_service.get_account_id(db, current_user)
    
    history = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id
    ).order_by(models.DepositHistory.date.desc()).all()
    
    return [
        {
            "id": h.id,
            "operation_type": h.operation_type.value,
            "amount": float(h.amount),
            "balance_after": float(h.balance_after),
            "date": h.date,
            "note": h.note,
            "created_at": h.created_at
        }
        for h in history
    ]


@router.delete("/{operation_id}")
def delete_deposit_operation(
    operation_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """РЈРґР°Р»РёС‚СЊ РѕРїРµСЂР°С†РёСЋ СЃ РґРµРїРѕР·РёС‚РѕРј"""
    account_id = auth_service.get_account_id(db, current_user)
    
    operation = db.query(models.DepositHistory).filter(
        models.DepositHistory.id == operation_id,
        models.DepositHistory.account_id == account_id
    ).first()
    
    if not operation:
        raise HTTPException(status_code=404, detail="РћРїРµСЂР°С†РёСЏ РЅРµ РЅР°Р№РґРµРЅР°")
    
    # Р•СЃР»Рё СЌС‚Рѕ РЅР°С‡Р°Р»СЊРЅС‹Р№ РґРµРїРѕР·РёС‚ - РѕР±РЅСѓР»СЏРµРј initial_balance
    if operation.operation_type == models.DepositOperationType.INITIAL:
        account = db.query(models.Account).filter(models.Account.id == account_id).first()
        if account:
            account.initial_balance = 0
    
    db.delete(operation)
    db.commit()
    
    return {"message": "РћРїРµСЂР°С†РёСЏ СѓРґР°Р»РµРЅР°"}


@router.get("/equity-curve")
def get_equity_curve(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    РџРѕР»СѓС‡РёС‚СЊ РєСЂРёРІСѓСЋ РєР°РїРёС‚Р°Р»Р° СЃ СѓС‡С‘С‚РѕРј РґРµРїРѕР·РёС‚РѕРІ.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ РµР¶РµРґРЅРµРІРЅС‹Р№ Р±Р°Р»Р°РЅСЃ = initial + deposits - withdrawals + cumulative_pnl
    """
    account_id = auth_service.get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial_balance = float(account.initial_balance or 0) if account else 0
    
    # РџРѕР»СѓС‡Р°РµРј РІСЃРµ Р·Р°РєСЂС‹С‚С‹Рµ СЃРґРµР»РєРё
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None)
    ).order_by(models.Trade.exit_at).all()
    
    # РџРѕР»СѓС‡Р°РµРј РІСЃРµ РѕРїРµСЂР°С†РёРё СЃ РґРµРїРѕР·РёС‚РѕРј
    deposit_ops = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id
    ).order_by(models.DepositHistory.date).all()
    
    if not trades and not deposit_ops:
        return {"equity_curve": [], "initial_balance": initial_balance}
    
    # РЎРѕР±РёСЂР°РµРј РІСЃРµ СЃРѕР±С‹С‚РёСЏ (СЃРґРµР»РєРё + РѕРїРµСЂР°С†РёРё) РІ С…СЂРѕРЅРѕР»РѕРіРёС‡РµСЃРєРѕРј РїРѕСЂСЏРґРєРµ
    events = []
    
    for trade in trades:
        events.append({
            "date": trade.exit_at.date(),
            "type": "trade",
            "pnl": float(trade.net_pnl or trade.pnl or 0)
        })
    
    for op in deposit_ops:
        if op.operation_type != models.DepositOperationType.INITIAL:
            events.append({
                "date": op.date.date(),
                "type": "deposit" if op.amount > 0 else "withdrawal",
                "amount": float(op.amount)
            })
    
    # РЎРѕСЂС‚РёСЂСѓРµРј РїРѕ РґР°С‚Рµ
    events.sort(key=lambda x: x["date"])
    
    if not events:
        return {"equity_curve": [], "initial_balance": initial_balance}
    
    # РЎС‚СЂРѕРёРј РєСЂРёРІСѓСЋ РєР°РїРёС‚Р°Р»Р°
    equity_curve = []
    current_balance = initial_balance
    deposit_balance = initial_balance  # Р‘Р°Р»Р°РЅСЃ С‚РѕР»СЊРєРѕ РѕС‚ РґРµРїРѕР·РёС‚РѕРІ (Р±РµР· PnL)
    cumulative_pnl = 0
    
    # Р“СЂСѓРїРїРёСЂСѓРµРј СЃРѕР±С‹С‚РёСЏ РїРѕ РґРЅСЏРј
    from collections import defaultdict
    daily_events = defaultdict(lambda: {"pnl": 0, "deposit_change": 0})
    
    for event in events:
        date_str = event["date"].isoformat()
        if event["type"] == "trade":
            daily_events[date_str]["pnl"] += event["pnl"]
        else:
            daily_events[date_str]["deposit_change"] += event["amount"]
    
    # Р“РµРЅРµСЂРёСЂСѓРµРј С‚РѕС‡РєРё РєСЂРёРІРѕР№
    for date_str in sorted(daily_events.keys()):
        day_data = daily_events[date_str]
        
        cumulative_pnl += day_data["pnl"]
        deposit_balance += day_data["deposit_change"]
        current_balance = deposit_balance + cumulative_pnl
        
        equity_curve.append({
            "date": date_str,
            "balance": round(current_balance, 2),
            "pnl_cumulative": round(cumulative_pnl, 2),
            "deposit_balance": round(deposit_balance, 2)
        })
    
    return {
        "equity_curve": equity_curve,
        "initial_balance": initial_balance,
        "current_balance": round(current_balance, 2),
        "total_pnl": round(cumulative_pnl, 2)
    }


def _calculate_balance_at_date(db: Session, account_id: int, date: datetime) -> float:
    """Р’СЃРїРѕРјРѕРіР°С‚РµР»СЊРЅР°СЏ С„СѓРЅРєС†РёСЏ: СЂР°СЃСЃС‡РёС‚Р°С‚СЊ Р±Р°Р»Р°РЅСЃ РЅР° РѕРїСЂРµРґРµР»С‘РЅРЅСѓСЋ РґР°С‚Сѓ"""
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial = float(account.initial_balance or 0) if account else 0
    
    # РЎСѓРјРјР° РѕРїРµСЂР°С†РёР№ РґРѕ СЌС‚РѕР№ РґР°С‚С‹
    deposits = db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.date <= date,
        models.DepositHistory.operation_type != models.DepositOperationType.INITIAL
    ).scalar() or 0
    
    # PnL РґРѕ СЌС‚РѕР№ РґР°С‚С‹
    pnl = db.query(func.coalesce(func.sum(models.Trade.net_pnl), 0)).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None),
        models.Trade.exit_at <= date
    ).scalar() or 0
    
    return initial + float(deposits) + float(pnl)


@router.get("/snapshots")
def get_balance_snapshots(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """РџРѕР»СѓС‡РёС‚СЊ РІСЃРµ СЃРЅРёРјРєРё Р±Р°Р»Р°РЅСЃР° РёР· РѕС‚С‡С‘С‚РѕРІ Р±СЂРѕРєРµСЂР°"""
    account_id = auth_service.get_account_id(db, current_user)
    
    snapshots = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.account_id == account_id
    ).order_by(models.BalanceSnapshot.date).all()
    
    return [
        {
            "id": s.id,
            "date": s.date.isoformat(),
            "balance": float(s.balance),
            "source": s.source,
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in snapshots
    ]


@router.delete("/snapshots/{snapshot_id}")
def delete_balance_snapshot(
    snapshot_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """РЈРґР°Р»РёС‚СЊ СЃРЅРёРјРѕРє Р±Р°Р»Р°РЅСЃР°"""
    account_id = auth_service.get_account_id(db, current_user)
    
    snapshot = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.id == snapshot_id,
        models.BalanceSnapshot.account_id == account_id
    ).first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="РЎРЅРёРјРѕРє Р±Р°Р»Р°РЅСЃР° РЅРµ РЅР°Р№РґРµРЅ")
    
    db.delete(snapshot)
    db.commit()
    
    return {"message": "РЎРЅРёРјРѕРє Р±Р°Р»Р°РЅСЃР° СѓРґР°Р»С‘РЅ"}

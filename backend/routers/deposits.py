"""
Роутер для управления депозитом и историей изменений.
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


def get_account_id(db: Session, current_user: Optional[models.User]) -> int:
    """Получить account_id для пользователя или демо-аккаунт"""
    if current_user:
        account = db.query(models.Account).filter(
            models.Account.user_id == current_user.id
        ).first()
        if not account:
            # Создаём аккаунт для пользователя
            account = models.Account(
                user_id=current_user.id,
                name="Основной счёт",
                balance=0,
                initial_balance=0,
                currency="RUB"
            )
            db.add(account)
            db.commit()
            db.refresh(account)
        return account.id
    # Демо-аккаунт
    return 1


@router.get("/balance", response_model=schemas.AccountBalanceResponse)
def get_balance(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Получить текущий баланс и статистику депозита"""
    account_id = get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    
    # Сумма всех пополнений
    total_deposits = db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.DEPOSIT
    ).scalar() or 0
    
    # Сумма всех снятий (абсолютное значение)
    total_withdrawals = abs(db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.WITHDRAWAL
    ).scalar() or 0)
    
    # Сумма PnL из закрытых сделок
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
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Установить начальный депозит"""
    account_id = get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    
    operation_date = date or datetime.utcnow()
    
    # Проверяем, есть ли уже начальный депозит
    existing = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.INITIAL
    ).first()
    
    if existing:
        # Обновляем существующий
        existing.amount = amount
        existing.balance_after = amount
        existing.date = operation_date
        account.initial_balance = amount
    else:
        # Создаём новый
        history = models.DepositHistory(
            account_id=account_id,
            operation_type=models.DepositOperationType.INITIAL,
            amount=amount,
            balance_after=amount,
            date=operation_date,
            note="Начальный депозит"
        )
        db.add(history)
        account.initial_balance = amount
    
    db.commit()
    
    return {"message": f"Начальный депозит установлен: {amount}", "initial_balance": amount}


@router.post("/add")
def add_deposit(
    amount: float,
    date: datetime,
    note: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Добавить пополнение депозита"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма пополнения должна быть положительной")
    
    account_id = get_account_id(db, current_user)
    
    # Получаем текущий баланс на эту дату
    balance_info = _calculate_balance_at_date(db, account_id, date)
    new_balance = balance_info + amount
    
    history = models.DepositHistory(
        account_id=account_id,
        operation_type=models.DepositOperationType.DEPOSIT,
        amount=amount,
        balance_after=new_balance,
        date=date,
        note=note or "Пополнение"
    )
    db.add(history)
    db.commit()
    
    return {"message": f"Пополнение добавлено: +{amount}", "balance_after": new_balance}


@router.post("/withdraw")
def add_withdrawal(
    amount: float,
    date: datetime,
    note: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Добавить снятие с депозита"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма снятия должна быть положительной")
    
    account_id = get_account_id(db, current_user)
    
    # Получаем текущий баланс на эту дату
    balance_info = _calculate_balance_at_date(db, account_id, date)
    new_balance = balance_info - amount
    
    history = models.DepositHistory(
        account_id=account_id,
        operation_type=models.DepositOperationType.WITHDRAWAL,
        amount=-amount,  # Отрицательное значение
        balance_after=new_balance,
        date=date,
        note=note or "Снятие"
    )
    db.add(history)
    db.commit()
    
    return {"message": f"Снятие добавлено: -{amount}", "balance_after": new_balance}


@router.get("/history", response_model=List[schemas.DepositOperationResponse])
def get_deposit_history(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Получить историю операций с депозитом"""
    account_id = get_account_id(db, current_user)
    
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
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Удалить операцию с депозитом"""
    account_id = get_account_id(db, current_user)
    
    operation = db.query(models.DepositHistory).filter(
        models.DepositHistory.id == operation_id,
        models.DepositHistory.account_id == account_id
    ).first()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    
    # Если это начальный депозит - обнуляем initial_balance
    if operation.operation_type == models.DepositOperationType.INITIAL:
        account = db.query(models.Account).filter(models.Account.id == account_id).first()
        if account:
            account.initial_balance = 0
    
    db.delete(operation)
    db.commit()
    
    return {"message": "Операция удалена"}


@router.get("/equity-curve")
def get_equity_curve(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """
    Получить кривую капитала с учётом депозитов.
    Возвращает ежедневный баланс = initial + deposits - withdrawals + cumulative_pnl
    """
    account_id = get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial_balance = float(account.initial_balance or 0) if account else 0
    
    # Получаем все закрытые сделки
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None)
    ).order_by(models.Trade.exit_at).all()
    
    # Получаем все операции с депозитом
    deposit_ops = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id
    ).order_by(models.DepositHistory.date).all()
    
    if not trades and not deposit_ops:
        return {"equity_curve": [], "initial_balance": initial_balance}
    
    # Собираем все события (сделки + операции) в хронологическом порядке
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
    
    # Сортируем по дате
    events.sort(key=lambda x: x["date"])
    
    if not events:
        return {"equity_curve": [], "initial_balance": initial_balance}
    
    # Строим кривую капитала
    equity_curve = []
    current_balance = initial_balance
    deposit_balance = initial_balance  # Баланс только от депозитов (без PnL)
    cumulative_pnl = 0
    
    # Группируем события по дням
    from collections import defaultdict
    daily_events = defaultdict(lambda: {"pnl": 0, "deposit_change": 0})
    
    for event in events:
        date_str = event["date"].isoformat()
        if event["type"] == "trade":
            daily_events[date_str]["pnl"] += event["pnl"]
        else:
            daily_events[date_str]["deposit_change"] += event["amount"]
    
    # Генерируем точки кривой
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
    """Вспомогательная функция: рассчитать баланс на определённую дату"""
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial = float(account.initial_balance or 0) if account else 0
    
    # Сумма операций до этой даты
    deposits = db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.date <= date,
        models.DepositHistory.operation_type != models.DepositOperationType.INITIAL
    ).scalar() or 0
    
    # PnL до этой даты
    pnl = db.query(func.coalesce(func.sum(models.Trade.net_pnl), 0)).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None),
        models.Trade.exit_at <= date
    ).scalar() or 0
    
    return initial + float(deposits) + float(pnl)

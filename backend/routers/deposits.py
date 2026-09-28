"""
Роутер для управления депозитом и историей изменений.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

import database
import models
import schemas
import auth_service
import import_service
from capital_service import (
    SYNTHETIC_INITIAL_NOTE,
    cleanup_synthetic_initial_balance_history,
    ensure_initial_balance_history,
    sync_initial_balance,
)
# crypto_utils.decrypt_token и tinkoff_service удалены/не нужны после PR 0
# (greenfield rewrite). До восстановления live-портфеля (PR 11+12) deposits
# работает только с локальной БД.
from utils import utc_now_naive

router = APIRouter(prefix="/deposits", tags=["deposits"])


def _get_live_broker_balance(db: Session, account_id: int) -> float | None:
    """
    PR 0: TinkoffService.get_portfolio удалён. До восстановления (PR 11+12)
    fallback'ом служит последний снапшот баланса из БД (`source='tinkoff_api'`),
    либо None — тогда вызывающий код должен сам решить что делать.
    """
    connection = db.query(models.BrokerConnection).filter(
        models.BrokerConnection.account_id == account_id,
        models.BrokerConnection.is_active == True,
    ).first()
    if not connection:
        return None

    latest_snapshot = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.account_id == account_id,
        models.BalanceSnapshot.source == "tinkoff_api",
    ).order_by(models.BalanceSnapshot.date.desc()).first()
    if latest_snapshot:
        return float(latest_snapshot.balance or 0)
    return None


def _upsert_balance_snapshot(
    db: Session,
    *,
    account_id: int,
    snapshot_date: datetime,
    balance: float,
    source: str,
) -> models.BalanceSnapshot:
    existing = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.account_id == account_id,
        models.BalanceSnapshot.date == snapshot_date,
    ).first()

    if existing:
        existing.balance = balance
        existing.source = source
        return existing

    snapshot = models.BalanceSnapshot(
        account_id=account_id,
        date=snapshot_date,
        balance=balance,
        source=source,
    )
    db.add(snapshot)
    return snapshot


# get_account_id is now centralized in auth_service

@router.get("/balance", response_model=schemas.AccountBalanceResponse)
def get_balance(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Получить текущий баланс и статистику депозита"""
    account_id = auth_service.get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    cleanup_synthetic_initial_balance_history(db, account_id, commit=True)
    ensure_initial_balance_history(db, account_id, commit=True)

    manual_initial = db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.INITIAL,
        models.DepositHistory.note != SYNTHETIC_INITIAL_NOTE,
    ).scalar() or 0
    manual_deposits = db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.DEPOSIT,
    ).scalar() or 0
    manual_withdrawals = abs(db.query(func.coalesce(func.sum(models.DepositHistory.amount), 0)).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.WITHDRAWAL,
    ).scalar() or 0)

    broker_deposits = db.query(func.coalesce(func.sum(models.CapitalOperation.amount), 0)).filter(
        models.CapitalOperation.account_id == account_id,
        models.CapitalOperation.operation_type == "deposit",
    ).scalar() or 0
    broker_withdrawals = db.query(func.coalesce(func.sum(models.CapitalOperation.amount), 0)).filter(
        models.CapitalOperation.account_id == account_id,
        models.CapitalOperation.operation_type == "withdrawal",
    ).scalar() or 0

    has_broker_capital = bool((float(broker_deposits) > 0) or (float(broker_withdrawals) > 0))

    if has_broker_capital:
        total_deposits = float(broker_deposits)
        total_withdrawals = float(broker_withdrawals)
        net_deposit = float(broker_deposits) - float(broker_withdrawals)
    else:
        total_deposits = float(manual_deposits)
        total_withdrawals = float(manual_withdrawals)
        net_deposit = float(manual_initial) + float(manual_deposits) - float(manual_withdrawals)

    journal_pnl = db.query(func.coalesce(func.sum(models.Trade.net_pnl), 0)).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None)
    ).scalar() or 0

    local_current_balance = net_deposit + float(journal_pnl)
    broker_current_balance = _get_live_broker_balance(db, account_id)
    broker_pnl = None
    pnl_gap = None
    balance_source = "journal"
    current = local_current_balance
    total_pnl = float(journal_pnl)

    if broker_current_balance is not None:
        current = broker_current_balance
        balance_source = "broker_live"
        # ADR-0010: вычитаем effective deposits = net_deposit + initial_balance
        # (восстановленный стартовый якорь). На счёте без якоря (initial_balance==0)
        # тождественно прежней формуле. Manual-ветка (local_current_balance) не трогается.
        broker_pnl = broker_current_balance - (net_deposit + float(account.initial_balance or 0))
        total_pnl = broker_pnl
        pnl_gap = broker_pnl - float(journal_pnl)
    
    return {
        "account_id": account_id,
        "initial_balance": float(account.initial_balance or 0),
        "current_balance": current,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "total_pnl": float(total_pnl),
        "currency": account.currency,
        "net_deposit": net_deposit,
        "local_current_balance": local_current_balance,
        "journal_pnl": float(journal_pnl),
        "broker_current_balance": broker_current_balance,
        "broker_pnl": broker_pnl,
        "pnl_gap": pnl_gap,
        "balance_source": balance_source,
    }


@router.post("/initial")
def set_initial_balance(
    amount: float,
    date: Optional[datetime] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Установить начальный депозит"""
    account_id = auth_service.get_account_id(db, current_user)
    
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    
    operation_date = date or utc_now_naive()
    
    sync_initial_balance(
        db,
        account_id,
        amount,
        date=operation_date,
        note="Начальный депозит",
        source="manual",
        commit=True,
    )
    
    return {"message": f"Начальный депозит установлен: {amount}", "initial_balance": amount}


@router.post("/add")
def add_deposit(
    amount: float,
    date: datetime,
    note: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Добавить пополнение депозита"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма пополнения должна быть положительной")
    
    account_id = auth_service.get_account_id(db, current_user)
    
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
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Добавить снятие с депозита"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма снятия должна быть положительной")
    
    account_id = auth_service.get_account_id(db, current_user)
    
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
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Получить историю операций с депозитом"""
    account_id = auth_service.get_account_id(db, current_user)
    cleanup_synthetic_initial_balance_history(db, account_id, commit=True)
    ensure_initial_balance_history(db, account_id, commit=True)

    manual_history = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id
    ).order_by(models.DepositHistory.date.asc(), models.DepositHistory.id.asc()).all()
    broker_history = db.query(models.CapitalOperation).filter(
        models.CapitalOperation.account_id == account_id
    ).order_by(models.CapitalOperation.date.asc(), models.CapitalOperation.id.asc()).all()

    items = []
    for h in manual_history:
        if h.operation_type == models.DepositOperationType.INITIAL and h.note == SYNTHETIC_INITIAL_NOTE and broker_history:
            continue
        items.append({
            "id": h.id,
            "operation_type": h.operation_type.value,
            "amount": float(h.amount),
            "date": h.date,
            "note": h.note,
            "created_at": h.created_at,
            "source": "manual",
            "can_delete": True,
        })

    for op in broker_history:
        items.append({
            "id": op.id,
            "operation_type": "deposit" if op.operation_type == "deposit" else "withdrawal",
            "amount": float(op.amount) if op.operation_type == "deposit" else -float(op.amount),
            "date": op.date,
            "note": op.description,
            "created_at": op.created_at,
            "source": "broker",
            "can_delete": False,
        })

    items.sort(key=lambda item: (item["date"], item["created_at"], item["id"]))

    running_balance = 0.0
    normalized = []
    for item in items:
        if item["operation_type"] == "initial":
            running_balance = item["amount"]
        else:
            running_balance += item["amount"]
        normalized.append({
            **item,
            "balance_after": running_balance,
        })

    normalized.sort(key=lambda item: (item["date"], item["created_at"], item["id"]), reverse=True)
    return normalized


@router.get("/balance-snapshots", response_model=List[schemas.BalanceSnapshotResponse])
def get_balance_snapshots(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    account_id = auth_service.get_account_id(db, current_user)
    snapshots = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.account_id == account_id,
    ).order_by(models.BalanceSnapshot.date.asc()).all()

    return [
        {
            "id": snapshot.id,
            "date": snapshot.date,
            "balance": float(snapshot.balance or 0),
            "source": snapshot.source,
            "created_at": snapshot.created_at,
        }
        for snapshot in snapshots
    ]


@router.post("/import-balance-report")
async def import_balance_report(
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Импортирует входящий/исходящий остаток из брокерского Excel-отчёта как исторические снимки баланса."""
    account_id = auth_service.get_account_id(db, current_user)
    contents = await file.read()
    balance_info = import_service.parse_account_balance(contents, file.filename)

    initial_balance = balance_info.get("initial_balance")
    final_balance = balance_info.get("final_balance")
    period_start = balance_info.get("period_start")
    period_end = balance_info.get("period_end")

    if initial_balance is None and final_balance is None:
        raise HTTPException(status_code=400, detail="В отчёте не найден входящий или исходящий остаток")

    saved = []
    source = f"balance_report:{file.filename}"

    if initial_balance is not None:
        snapshot_date = period_start
        if snapshot_date is None:
            raise HTTPException(status_code=400, detail="В отчёте найден входящий остаток, но не определена дата начала периода")
        snapshot = _upsert_balance_snapshot(
            db,
            account_id=account_id,
            snapshot_date=snapshot_date,
            balance=float(initial_balance),
            source=source,
        )
        saved.append(snapshot)

    if final_balance is not None:
        snapshot_date = period_end
        if snapshot_date is None:
            raise HTTPException(status_code=400, detail="В отчёте найден исходящий остаток, но не определена дата конца периода")
        snapshot = _upsert_balance_snapshot(
            db,
            account_id=account_id,
            snapshot_date=snapshot_date,
            balance=float(final_balance),
            source=source,
        )
        saved.append(snapshot)

    db.commit()

    return {
        "message": f"Импортировано снимков баланса: {len(saved)}",
        "snapshots": [
            {
                "id": snapshot.id,
                "date": snapshot.date.isoformat() if snapshot.date else None,
                "balance": float(snapshot.balance or 0),
                "source": snapshot.source,
            }
            for snapshot in saved
        ],
        "hint": "Исторические снимки баланса будут использованы как якоря для более точного расчёта капитала на старт периода.",
    }


@router.delete("/{operation_id}")
def delete_deposit_operation(
    operation_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Удалить операцию с депозитом"""
    account_id = auth_service.get_account_id(db, current_user)
    
    operation = db.query(models.DepositHistory).filter(
        models.DepositHistory.id == operation_id,
        models.DepositHistory.account_id == account_id
    ).first()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    
    # Если это начальный депозит - обнуляем initial_balance
    if operation.operation_type == models.DepositOperationType.INITIAL:
        sync_initial_balance(db, account_id, 0, commit=False)
    
    db.delete(operation)
    db.commit()
    
    return {"message": "Операция удалена"}


@router.get("/equity-curve")
def get_equity_curve(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Получить кривую капитала с учётом депозитов.
    Возвращает ежедневный баланс = initial + deposits - withdrawals + cumulative_pnl
    """
    account_id = auth_service.get_account_id(db, current_user)
    
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


@router.get("/snapshots")
def get_balance_snapshots(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Получить все снимки баланса из отчётов брокера"""
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
    """Удалить снимок баланса"""
    account_id = auth_service.get_account_id(db, current_user)
    
    snapshot = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.id == snapshot_id,
        models.BalanceSnapshot.account_id == account_id
    ).first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Снимок баланса не найден")
    
    db.delete(snapshot)
    db.commit()
    
    return {"message": "Снимок баланса удалён"}

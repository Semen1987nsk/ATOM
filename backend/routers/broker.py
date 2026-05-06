"""
Broker Integration API
Подключение к брокерам и автосинхронизация
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
import asyncio

from database import get_db
from models import BrokerConnection, BrokerType, Account, BalanceSnapshot, CapitalOperation, Trade
from tinkoff_service import TinkoffService
from auth_service import get_current_user, get_user_account
import models
from capital_service import sync_initial_balance
from utils.datetime_utils import utc_now_naive
from sync_scheduler import scheduler
from sqlalchemy import func
from crypto_utils import encrypt_token, decrypt_token, TokenDecryptionError


def _decrypt_or_410(token: str) -> str:
    """
    Decrypt broker token; on failure return HTTP 410 Gone.
    Тихий fallback на ciphertext убран — теперь скажем юзеру явно «переподключи».
    """
    try:
        return decrypt_token(token)
    except TokenDecryptionError:
        raise HTTPException(
            status_code=410,
            detail="Подключение брокера повреждено (возможно, ключ шифрования был ротирован). Переподключите счёт.",
        )

router = APIRouter(prefix="/broker", tags=["broker"])


# ==================== SCHEMAS ====================

class BrokerAccountInfo(BaseModel):
    id: str
    name: str
    type: str
    status: str
    access_level: str


class TokenVerifyResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    accounts: List[BrokerAccountInfo] = []


class ConnectBrokerRequest(BaseModel):
    broker: str = Field(..., description="Тип брокера: tinkoff")
    api_token: str = Field(..., min_length=10, description="API токен от брокера")
    broker_account_id: str = Field(..., description="ID счёта в брокере")
    sync_from_date: Optional[datetime] = Field(None, description="Дата начала синхронизации")
    auto_sync_enabled: bool = Field(True, description="Включить автосинхронизацию")
    sync_interval_minutes: int = Field(60, ge=5, le=1440, description="Интервал синхронизации (мин)")


class BrokerConnectionResponse(BaseModel):
    id: int
    broker: str
    broker_account_id: str
    is_active: bool
    auto_sync_enabled: bool
    sync_interval_minutes: int
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    total_synced_trades: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class SyncResultResponse(BaseModel):
    success: bool
    new_trades: int
    updated_trades: int
    skipped: int
    errors: List[str]
    message: str


class TokenVerifyRequest(BaseModel):
    broker: str = Field(..., description="Тип брокера: tinkoff")
    api_token: str = Field(..., min_length=10, description="API токен")


# ==================== ENDPOINTS ====================

@router.post("/verify-token", response_model=TokenVerifyResponse)
async def verify_broker_token(
    request: TokenVerifyRequest
):
    """
    Проверяет валидность API токена и возвращает список доступных счетов.
    Token передаётся в Body, а не в Query для безопасности.
    """
    if request.broker.lower() != "tinkoff":
        raise HTTPException(status_code=400, detail="Пока поддерживается только Тинькофф")
    
    service = TinkoffService(request.api_token)
    result = await asyncio.to_thread(service.verify_token)
    
    if not result["valid"]:
        return TokenVerifyResponse(
            valid=False,
            error=result.get("error", "Неизвестная ошибка"),
            accounts=[]
        )
    
    accounts = [
        BrokerAccountInfo(
            id=acc["id"],
            name=acc["name"],
            type=acc["type"],
            status=acc["status"],
            access_level=acc.get("access_level", "UNKNOWN")
        )
        for acc in result.get("accounts", [])
    ]
    
    return TokenVerifyResponse(
        valid=True,
        accounts=accounts
    )


@router.post("/connect", response_model=BrokerConnectionResponse)
async def connect_broker(
    request: ConnectBrokerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Подключает брокера к аккаунту для автосинхронизации
    """
    if request.broker.lower() != "tinkoff":
        raise HTTPException(status_code=400, detail="Пока поддерживается только Тинькофф")
    
    # Проверяем токен
    service = TinkoffService(request.api_token)
    verify_result = await asyncio.to_thread(service.verify_token)
    
    if not verify_result["valid"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Невалидный токен: {verify_result.get('error')}"
        )
    
    # Проверяем что выбранный счёт существует
    account_ids = [acc["id"] for acc in verify_result.get("accounts", [])]
    if request.broker_account_id not in account_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Счёт {request.broker_account_id} не найден. Доступные: {account_ids}"
        )
    
    # Получаем аккаунт текущего пользователя
    account = get_user_account(db, current_user)
    
    # Проверяем нет ли уже подключения к этому брокерскому счёту для данного пользователя
    existing = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.broker_account_id == request.broker_account_id,
        BrokerConnection.is_active == True
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Этот брокерский счёт уже подключен"
        )
    
    # Создаём подключение
    connection = BrokerConnection(
        account_id=account.id,
        broker=BrokerType.TINKOFF,
        api_token=encrypt_token(request.api_token),
        broker_account_id=request.broker_account_id,
        auto_sync_enabled=request.auto_sync_enabled,
        sync_interval_minutes=request.sync_interval_minutes,
        sync_from_date=request.sync_from_date
    )
    
    db.add(connection)
    db.commit()
    db.refresh(connection)
    
    return BrokerConnectionResponse(
        id=connection.id,
        broker=connection.broker.value,
        broker_account_id=connection.broker_account_id,
        is_active=connection.is_active,
        auto_sync_enabled=connection.auto_sync_enabled,
        sync_interval_minutes=connection.sync_interval_minutes,
        last_sync_at=connection.last_sync_at,
        last_sync_status=connection.last_sync_status,
        total_synced_trades=connection.total_synced_trades,
        created_at=connection.created_at
    )


@router.get("/connections", response_model=List[BrokerConnectionResponse])
async def get_broker_connections(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Возвращает список подключённых брокеров текущего пользователя
    """
    account = get_user_account(db, current_user)
    connections = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).all()
    
    return [
        BrokerConnectionResponse(
            id=c.id,
            broker=c.broker.value,
            broker_account_id=c.broker_account_id,
            is_active=c.is_active,
            auto_sync_enabled=c.auto_sync_enabled,
            sync_interval_minutes=c.sync_interval_minutes,
            last_sync_at=c.last_sync_at,
            last_sync_status=c.last_sync_status,
            total_synced_trades=c.total_synced_trades,
            created_at=c.created_at
        )
        for c in connections
    ]


@router.post("/connections/{connection_id}/sync", response_model=SyncResultResponse)
async def sync_broker_trades(
    connection_id: int,
    force_full_sync: bool = Query(False, description="Полная синхронизация с начала"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Запускает синхронизацию сделок с брокером
    """
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.id == connection_id,
        BrokerConnection.account_id == get_user_account(db, current_user).id,
        BrokerConnection.is_active == True
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    
    if connection.broker != BrokerType.TINKOFF:
        raise HTTPException(status_code=400, detail="Синхронизация поддерживается только для Тинькофф")
    
    service = TinkoffService(_decrypt_or_410(connection.api_token))
    result = await asyncio.to_thread(
        service.sync_trades,
        db=db,
        connection=connection,
        force_full_sync=force_full_sync
    )
    
    if result["success"]:
        message = f"Синхронизация завершена: +{result['new_trades']} новых, {result['updated_trades']} обновлено"
    else:
        message = f"Синхронизация с ошибками: {'; '.join(result['errors'][:2])}"
    
    return SyncResultResponse(
        success=result["success"],
        new_trades=result["new_trades"],
        updated_trades=result["updated_trades"],
        skipped=result["skipped"],
        errors=result["errors"],
        message=message
    )


@router.delete("/connections/{connection_id}")
async def disconnect_broker(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Отключает брокера (мягкое удаление)
    """
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.id == connection_id,
        BrokerConnection.account_id == get_user_account(db, current_user).id
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    
    connection.is_active = False
    connection.api_token = ""  # Удаляем токен
    db.commit()
    
    return {"message": "Брокер отключён", "id": connection_id}


@router.patch("/connections/{connection_id}")
async def update_broker_connection(
    connection_id: int,
    auto_sync_enabled: Optional[bool] = None,
    sync_interval_minutes: Optional[int] = Query(None, ge=5, le=1440),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Обновляет настройки подключения
    """
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.id == connection_id,
        BrokerConnection.account_id == get_user_account(db, current_user).id,
        BrokerConnection.is_active == True
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    
    if auto_sync_enabled is not None:
        connection.auto_sync_enabled = auto_sync_enabled
    
    if sync_interval_minutes is not None:
        connection.sync_interval_minutes = sync_interval_minutes
    
    connection.updated_at = utc_now_naive()
    db.commit()
    
    return {"message": "Настройки обновлены", "id": connection_id}


@router.get("/sync-status")
async def get_sync_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Возвращает общий статус синхронизации для дашборда
    """
    # Получаем все активные подключения
    account = get_user_account(db, current_user)
    connections = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).all()
    
    if not connections:
        return {
            "has_connections": False,
            "scheduler": scheduler.get_status(),
            "connections": []
        }
    
    connection_statuses = []
    for conn in connections:
        # Вычисляем время до следующей синхронизации
        next_sync_at = None
        if conn.auto_sync_enabled and conn.last_sync_at:
            from datetime import timedelta
            next_sync_at = conn.last_sync_at + timedelta(minutes=conn.sync_interval_minutes)
        
        connection_statuses.append({
            "id": conn.id,
            "broker": conn.broker.value,
            "broker_account_id": conn.broker_account_id,
            "auto_sync_enabled": conn.auto_sync_enabled,
            "sync_interval_minutes": conn.sync_interval_minutes,
            "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
            "last_sync_status": conn.last_sync_status,
            "last_sync_error": conn.last_sync_error,
            "next_sync_at": next_sync_at.isoformat() if next_sync_at else None,
            "total_synced_trades": conn.total_synced_trades,
            "is_syncing": scheduler._sync_in_progress.get(conn.id, False)
        })
    
    return {
        "has_connections": True,
        "scheduler": scheduler.get_status(),
        "connections": connection_statuses
    }


@router.post("/trigger-sync/{connection_id}")
async def trigger_manual_sync(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Запускает ручную синхронизацию для подключения
    """
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.id == connection_id,
        BrokerConnection.account_id == get_user_account(db, current_user).id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    
    triggered = await scheduler.trigger_sync(connection_id)
    
    if not triggered:
        return {
            "success": False,
            "message": "Синхронизация уже выполняется"
        }
    
    return {
        "success": True,
        "message": "Синхронизация запущена"
    }


@router.get("/portfolio")
async def get_portfolio(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Возвращает текущий портфель из Tinkoff API
    """
    account = get_user_account(db, current_user)
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Нет активных подключений к брокеру")
    
    try:
        service = TinkoffService(_decrypt_or_410(conn.api_token))
        portfolio = await asyncio.to_thread(service.get_portfolio, conn.broker_account_id)
        
        # Также получаем initial_balance из аккаунта для расчёта ROI
        account = db.query(Account).filter(Account.id == conn.account_id).first()
        initial_balance = float(account.initial_balance) if account and account.initial_balance else None
        
        # Рассчитываем ROI если есть начальный баланс
        total_balance = float(portfolio["total_balance"])
        roi = None
        if initial_balance and initial_balance > 0:
            roi = ((total_balance - initial_balance) / initial_balance) * 100
        
        return {
            "success": True,
            "total_balance": total_balance,
            "cash": float(portfolio["cash"]),
            "stocks_value": float(portfolio["stocks_value"]),
            "bonds_value": float(portfolio["bonds_value"]),
            "etf_value": float(portfolio["etf_value"]),
            "futures_value": float(portfolio["futures_value"]),
            "unrealized_pnl": float(portfolio["unrealized_pnl"]),
            "initial_balance": initial_balance,
            "roi_percent": roi,
            "positions": [
                {
                    "ticker": p["ticker"],
                    "name": p["name"],
                    "quantity": float(p["quantity"]),
                    "average_price": float(p["average_price"]),
                    "current_price": float(p["current_price"]),
                    "unrealized_pnl": float(p["unrealized_pnl"]),
                    "instrument_type": p["instrument_type"]
                }
                for p in portfolio["positions"]
                if p["ticker"] != "RUB000UTSTOM"  # Исключаем рубли как позицию
            ],
            "updated_at": utc_now_naive().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения портфеля: {str(e)}")


@router.get("/balance-history")
async def get_balance_history(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Возвращает историю баланса для построения Equity Curve
    """
    account = get_user_account(db, current_user)
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        return {"snapshots": [], "metrics": None}
    
    from datetime import timedelta
    from_date = utc_now_naive() - timedelta(days=days)
    
    snapshots = db.query(BalanceSnapshot).filter(
        BalanceSnapshot.account_id == conn.account_id,
        BalanceSnapshot.date >= from_date
    ).order_by(BalanceSnapshot.date.asc()).all()
    
    if not snapshots:
        return {"snapshots": [], "metrics": None}
    
    # Рассчитываем метрики
    balances = [float(s.balance) for s in snapshots]
    first_balance = balances[0]
    last_balance = balances[-1]
    peak = max(balances)
    
    # ROI
    roi = ((last_balance - first_balance) / first_balance * 100) if first_balance > 0 else 0
    
    # Max Drawdown
    max_drawdown = 0
    peak_so_far = balances[0]
    for b in balances:
        if b > peak_so_far:
            peak_so_far = b
        drawdown = (peak_so_far - b) / peak_so_far * 100 if peak_so_far > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # Daily returns for volatility
    daily_returns = []
    for i in range(1, len(balances)):
        if balances[i-1] > 0:
            daily_returns.append((balances[i] - balances[i-1]) / balances[i-1])
    
    # Volatility (annualized)
    import statistics
    volatility = 0
    if len(daily_returns) > 1:
        volatility = statistics.stdev(daily_returns) * (252 ** 0.5) * 100  # Annualized %
    
    # Profit Factor (sum of gains / sum of losses)
    gains = sum(r for r in daily_returns if r > 0)
    losses = abs(sum(r for r in daily_returns if r < 0))
    profit_factor = gains / losses if losses > 0 else float('inf') if gains > 0 else 0
    
    return {
        "snapshots": [
            {
                "date": s.date.isoformat(),
                "balance": float(s.balance),
                "cash": float(s.cash) if s.cash else 0,
                "stocks_value": float(s.stocks_value) if s.stocks_value else 0,
                "futures_value": float(s.futures_value) if s.futures_value else 0,
                "unrealized_pnl": float(s.unrealized_pnl) if s.unrealized_pnl else 0
            }
            for s in snapshots
        ],
        "metrics": {
            "start_balance": first_balance,
            "current_balance": last_balance,
            "peak_balance": peak,
            "roi_percent": round(roi, 2),
            "max_drawdown_percent": round(max_drawdown, 2),
            "volatility_percent": round(volatility, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "в€ћ",
            "trading_days": len(snapshots),
            "profitable_days": sum(1 for r in daily_returns if r > 0),
            "losing_days": sum(1 for r in daily_returns if r < 0)
        }
    }


@router.post("/set-initial-balance")
async def set_initial_balance(
    initial_balance: float,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Устанавливает начальный баланс для расчёта ROI
    """
    account = get_user_account(db, current_user)
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="No active broker connections")
    
    sync_initial_balance(
        db,
        account.id,
        initial_balance,
        note="Initial balance set from broker portfolio",
        commit=True,
    )
    return {"success": True, "initial_balance": initial_balance}


@router.get("/net-deposit")
async def get_net_deposit_on_date(
    date: datetime,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Рассчитывает баланс на дату:
    (Вводы - Выводы) + (Реализованный PnL - Комиссии)
    """
    account = get_user_account(db, current_user)
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Нет активных подключений")
    
    # Делаем срез на конец дня указанной даты
    target_date = date.replace(hour=23, minute=59, second=59)
    
    # 1. Движение средств
    deposits = db.query(func.sum(CapitalOperation.amount)).filter(
        CapitalOperation.account_id == conn.account_id,
        CapitalOperation.operation_type == "deposit",
        CapitalOperation.date <= target_date
    ).scalar() or 0
    
    withdrawals = db.query(func.sum(CapitalOperation.amount)).filter(
        CapitalOperation.account_id == conn.account_id,
        CapitalOperation.operation_type == "withdrawal",
        CapitalOperation.date <= target_date
    ).scalar() or 0
    
    # 2. Результат торговли (только закрытые сделки)
    trade_stats = db.query(
        func.sum(Trade.pnl),
        func.sum(Trade.commission)
    ).filter(
        Trade.account_id == conn.account_id,
        Trade.exit_at <= target_date
    ).first()
    
    realized_pnl = float(trade_stats[0] or 0)
    commissions = float(trade_stats[1] or 0)
    
    # Итоговый баланс (Equity по закрытым сделкам)
    net_deposit = float(deposits) - float(withdrawals)
    total_balance = net_deposit + realized_pnl - commissions
    
    return {
        "date": target_date.isoformat(),
        "deposits": float(deposits),
        "withdrawals": float(withdrawals),
        "realized_pnl": realized_pnl,
        "commissions": commissions,
        "net_deposit": net_deposit,
        "equity_on_date": total_balance,
    }

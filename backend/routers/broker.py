"""
Broker Integration API
РџРѕРґРєР»СЋС‡РµРЅРёРµ Рє Р±СЂРѕРєРµСЂР°Рј Рё Р°РІС‚РѕСЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ
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
from crypto_utils import encrypt_token, decrypt_token

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
    broker: str = Field(..., description="РўРёРї Р±СЂРѕРєРµСЂР°: tinkoff")
    api_token: str = Field(..., min_length=10, description="API С‚РѕРєРµРЅ РѕС‚ Р±СЂРѕРєРµСЂР°")
    broker_account_id: str = Field(..., description="ID СЃС‡С‘С‚Р° РІ Р±СЂРѕРєРµСЂРµ")
    sync_from_date: Optional[datetime] = Field(None, description="Р”Р°С‚Р° РЅР°С‡Р°Р»Р° СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё")
    auto_sync_enabled: bool = Field(True, description="Р’РєР»СЋС‡РёС‚СЊ Р°РІС‚РѕСЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ")
    sync_interval_minutes: int = Field(60, ge=5, le=1440, description="РРЅС‚РµСЂРІР°Р» СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё (РјРёРЅ)")


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
    broker: str = Field(..., description="РўРёРї Р±СЂРѕРєРµСЂР°: tinkoff")
    api_token: str = Field(..., min_length=10, description="API С‚РѕРєРµРЅ")


# ==================== ENDPOINTS ====================

@router.post("/verify-token", response_model=TokenVerifyResponse)
async def verify_broker_token(
    request: TokenVerifyRequest
):
    """
    РџСЂРѕРІРµСЂСЏРµС‚ РІР°Р»РёРґРЅРѕСЃС‚СЊ API С‚РѕРєРµРЅР° Рё РІРѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє РґРѕСЃС‚СѓРїРЅС‹С… СЃС‡РµС‚РѕРІ.
    Token РїРµСЂРµРґР°С‘С‚СЃСЏ РІ Body, Р° РЅРµ РІ Query РґР»СЏ Р±РµР·РѕРїР°СЃРЅРѕСЃС‚Рё.
    """
    if request.broker.lower() != "tinkoff":
        raise HTTPException(status_code=400, detail="РџРѕРєР° РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ РўРёРЅСЊРєРѕС„С„")
    
    service = TinkoffService(request.api_token)
    result = await asyncio.to_thread(service.verify_token)
    
    if not result["valid"]:
        return TokenVerifyResponse(
            valid=False,
            error=result.get("error", "РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР°"),
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
    РџРѕРґРєР»СЋС‡Р°РµС‚ Р±СЂРѕРєРµСЂР° Рє Р°РєРєР°СѓРЅС‚Сѓ РґР»СЏ Р°РІС‚РѕСЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё
    """
    if request.broker.lower() != "tinkoff":
        raise HTTPException(status_code=400, detail="РџРѕРєР° РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ РўРёРЅСЊРєРѕС„С„")
    
    # РџСЂРѕРІРµСЂСЏРµРј С‚РѕРєРµРЅ
    service = TinkoffService(request.api_token)
    verify_result = await asyncio.to_thread(service.verify_token)
    
    if not verify_result["valid"]:
        raise HTTPException(
            status_code=400, 
            detail=f"РќРµРІР°Р»РёРґРЅС‹Р№ С‚РѕРєРµРЅ: {verify_result.get('error')}"
        )
    
    # РџСЂРѕРІРµСЂСЏРµРј С‡С‚Рѕ РІС‹Р±СЂР°РЅРЅС‹Р№ СЃС‡С‘С‚ СЃСѓС‰РµСЃС‚РІСѓРµС‚
    account_ids = [acc["id"] for acc in verify_result.get("accounts", [])]
    if request.broker_account_id not in account_ids:
        raise HTTPException(
            status_code=400,
            detail=f"РЎС‡С‘С‚ {request.broker_account_id} РЅРµ РЅР°Р№РґРµРЅ. Р”РѕСЃС‚СѓРїРЅС‹Рµ: {account_ids}"
        )
    
    # РџРѕР»СѓС‡Р°РµРј Р°РєРєР°СѓРЅС‚ С‚РµРєСѓС‰РµРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    account = get_user_account(db, current_user)
    
    # РџСЂРѕРІРµСЂСЏРµРј РЅРµС‚ Р»Рё СѓР¶Рµ РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє СЌС‚РѕРјСѓ Р±СЂРѕРєРµСЂСЃРєРѕРјСѓ СЃС‡С‘С‚Сѓ РґР»СЏ РґР°РЅРЅРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
    existing = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.broker_account_id == request.broker_account_id,
        BrokerConnection.is_active == True
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Р­С‚РѕС‚ Р±СЂРѕРєРµСЂСЃРєРёР№ СЃС‡С‘С‚ СѓР¶Рµ РїРѕРґРєР»СЋС‡РµРЅ"
        )
    
    # РЎРѕР·РґР°С‘Рј РїРѕРґРєР»СЋС‡РµРЅРёРµ
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
    force_full_sync: bool = Query(False, description="РџРѕР»РЅР°СЏ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ СЃ РЅР°С‡Р°Р»Р°"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Р—Р°РїСѓСЃРєР°РµС‚ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ СЃРґРµР»РѕРє СЃ Р±СЂРѕРєРµСЂРѕРј
    """
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.id == connection_id,
        BrokerConnection.account_id == get_user_account(db, current_user).id,
        BrokerConnection.is_active == True
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    
    if connection.broker != BrokerType.TINKOFF:
        raise HTTPException(status_code=400, detail="РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ РґР»СЏ РўРёРЅСЊРєРѕС„С„")
    
    service = TinkoffService(decrypt_token(connection.api_token))
    result = await asyncio.to_thread(
        service.sync_trades,
        db=db,
        connection=connection,
        force_full_sync=force_full_sync
    )
    
    if result["success"]:
        message = f"РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ Р·Р°РІРµСЂС€РµРЅР°: +{result['new_trades']} РЅРѕРІС‹С…, {result['updated_trades']} РѕР±РЅРѕРІР»РµРЅРѕ"
    else:
        message = f"РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ СЃ РѕС€РёР±РєР°РјРё: {'; '.join(result['errors'][:2])}"
    
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
    РћС‚РєР»СЋС‡Р°РµС‚ Р±СЂРѕРєРµСЂР° (РјСЏРіРєРѕРµ СѓРґР°Р»РµРЅРёРµ)
    """
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.id == connection_id,
        BrokerConnection.account_id == get_user_account(db, current_user).id
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    
    connection.is_active = False
    connection.api_token = ""  # РЈРґР°Р»СЏРµРј С‚РѕРєРµРЅ
    db.commit()
    
    return {"message": "Р‘СЂРѕРєРµСЂ РѕС‚РєР»СЋС‡С‘РЅ", "id": connection_id}


@router.patch("/connections/{connection_id}")
async def update_broker_connection(
    connection_id: int,
    auto_sync_enabled: Optional[bool] = None,
    sync_interval_minutes: Optional[int] = Query(None, ge=5, le=1440),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    РћР±РЅРѕРІР»СЏРµС‚ РЅР°СЃС‚СЂРѕР№РєРё РїРѕРґРєР»СЋС‡РµРЅРёСЏ
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
    
    return {"message": "РќР°СЃС‚СЂРѕР№РєРё РѕР±РЅРѕРІР»РµРЅС‹", "id": connection_id}


@router.get("/sync-status")
async def get_sync_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚ РѕР±С‰РёР№ СЃС‚Р°С‚СѓСЃ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё РґР»СЏ РґР°С€Р±РѕСЂРґР°
    """
    # РџРѕР»СѓС‡Р°РµРј РІСЃРµ Р°РєС‚РёРІРЅС‹Рµ РїРѕРґРєР»СЋС‡РµРЅРёСЏ
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
        # Р’С‹С‡РёСЃР»СЏРµРј РІСЂРµРјСЏ РґРѕ СЃР»РµРґСѓСЋС‰РµР№ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёРё
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
    Р—Р°РїСѓСЃРєР°РµС‚ СЂСѓС‡РЅСѓСЋ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ РґР»СЏ РїРѕРґРєР»СЋС‡РµРЅРёСЏ
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
            "message": "РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ СѓР¶Рµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ"
        }
    
    return {
        "success": True,
        "message": "РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ Р·Р°РїСѓС‰РµРЅР°"
    }


@router.get("/portfolio")
async def get_portfolio(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚ С‚РµРєСѓС‰РёР№ РїРѕСЂС‚С„РµР»СЊ РёР· Tinkoff API
    """
    account = get_user_account(db, current_user)
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="РќРµС‚ Р°РєС‚РёРІРЅС‹С… РїРѕРґРєР»СЋС‡РµРЅРёР№ Рє Р±СЂРѕРєРµСЂСѓ")
    
    try:
        service = TinkoffService(decrypt_token(conn.api_token))
        portfolio = await asyncio.to_thread(service.get_portfolio, conn.broker_account_id)
        
        # РўР°РєР¶Рµ РїРѕР»СѓС‡Р°РµРј initial_balance РёР· Р°РєРєР°СѓРЅС‚Р° РґР»СЏ СЂР°СЃС‡С‘С‚Р° ROI
        account = db.query(Account).filter(Account.id == conn.account_id).first()
        initial_balance = float(account.initial_balance) if account and account.initial_balance else None
        
        # Р Р°СЃСЃС‡РёС‚С‹РІР°РµРј ROI РµСЃР»Рё РµСЃС‚СЊ РЅР°С‡Р°Р»СЊРЅС‹Р№ Р±Р°Р»Р°РЅСЃ
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
                if p["ticker"] != "RUB000UTSTOM"  # РСЃРєР»СЋС‡Р°РµРј СЂСѓР±Р»Рё РєР°Рє РїРѕР·РёС†РёСЋ
            ],
            "updated_at": utc_now_naive().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РїРѕСЂС‚С„РµР»СЏ: {str(e)}")


@router.get("/balance-history")
async def get_balance_history(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚ РёСЃС‚РѕСЂРёСЋ Р±Р°Р»Р°РЅСЃР° РґР»СЏ РїРѕСЃС‚СЂРѕРµРЅРёСЏ Equity Curve
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
    
    # Р Р°СЃСЃС‡РёС‚С‹РІР°РµРј РјРµС‚СЂРёРєРё
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
    РЈСЃС‚Р°РЅР°РІР»РёРІР°РµС‚ РЅР°С‡Р°Р»СЊРЅС‹Р№ Р±Р°Р»Р°РЅСЃ РґР»СЏ СЂР°СЃС‡С‘С‚Р° ROI
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
    Р Р°СЃСЃС‡РёС‚С‹РІР°РµС‚ Р±Р°Р»Р°РЅСЃ РЅР° РґР°С‚Сѓ:
    (Р’РІРѕРґС‹ - Р’С‹РІРѕРґС‹) + (Р РµР°Р»РёР·РѕРІР°РЅРЅС‹Р№ PnL - РљРѕРјРёСЃСЃРёРё)
    """
    account = get_user_account(db, current_user)
    conn = db.query(BrokerConnection).filter(
        BrokerConnection.account_id == account.id,
        BrokerConnection.is_active == True
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="РќРµС‚ Р°РєС‚РёРІРЅС‹С… РїРѕРґРєР»СЋС‡РµРЅРёР№")
    
    # Р”РµР»Р°РµРј СЃСЂРµР· РЅР° РєРѕРЅРµС† РґРЅСЏ СѓРєР°Р·Р°РЅРЅРѕР№ РґР°С‚С‹
    target_date = date.replace(hour=23, minute=59, second=59)
    
    # 1. Р”РІРёР¶РµРЅРёРµ СЃСЂРµРґСЃС‚РІ
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
    
    # 2. Р РµР·СѓР»СЊС‚Р°С‚ С‚РѕСЂРіРѕРІР»Рё (С‚РѕР»СЊРєРѕ Р·Р°РєСЂС‹С‚С‹Рµ СЃРґРµР»РєРё)
    trade_stats = db.query(
        func.sum(Trade.pnl),
        func.sum(Trade.commission)
    ).filter(
        Trade.account_id == conn.account_id,
        Trade.exit_at <= target_date
    ).first()
    
    realized_pnl = float(trade_stats[0] or 0)
    commissions = float(trade_stats[1] or 0)
    
    # РС‚РѕРіРѕРІС‹Р№ Р±Р°Р»Р°РЅСЃ (Equity РїРѕ Р·Р°РєСЂС‹С‚С‹Рј СЃРґРµР»РєР°Рј)
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

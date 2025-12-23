from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal
import models

class TradeBase(BaseModel):
    symbol: str
    direction: models.TradeDirection
    entry_price: Decimal
    quantity: Decimal
    entry_at: datetime
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    risk_amount: Optional[Decimal] = None
    setup_name: Optional[str] = None
    notes: Optional[str] = None

class TradeCreate(TradeBase):
    account_id: int

class TradeClose(BaseModel):
    exit_price: Decimal
    exit_at: datetime
    mae_price: Optional[Decimal] = None
    mfe_price: Optional[Decimal] = None

class Trade(TradeBase):
    id: int
    account_id: int
    exit_price: Optional[Decimal] = None
    exit_at: Optional[datetime] = None
    pnl: Optional[Decimal] = None
    mae_price: Optional[Decimal] = None
    mfe_price: Optional[Decimal] = None

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_pnl: Decimal
    win_rate: float
    total_trades: int
    profitable_trades: int
    optimal_f: float
    mae_mfe_analysis: Optional[dict] = None

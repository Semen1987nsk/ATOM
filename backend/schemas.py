from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
import models

class TradeBase(BaseModel):
    symbol: str
    direction: models.TradeDirection
    entry_price: float
    quantity: float
    entry_at: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_amount: Optional[float] = None
    setup_name: Optional[str] = None
    timeframe: Optional[str] = None
    exit_reason: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = []

class TradeCreate(TradeBase):
    account_id: int

class TradeClose(BaseModel):
    exit_price: float
    exit_at: datetime
    exit_reason: Optional[str] = None
    mae_price: Optional[float] = None
    mfe_price: Optional[float] = None

class Trade(TradeBase):
    id: int
    account_id: int
    exit_price: Optional[float] = None
    exit_at: Optional[datetime] = None
    pnl: Optional[float] = None
    mae_price: Optional[float] = None
    mfe_price: Optional[float] = None
    ai_analysis: Optional[dict] = None

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_pnl: float
    win_rate: float
    total_trades: int
    profitable_trades: int
    optimal_f: float
    sqn: Optional[dict] = None
    z_score: Optional[dict] = None
    profit_factor: float = 0
    r_expectancy: float = 0
    recovery_factor: float = 0
    ahpr: float = 0
    mae_mfe_analysis: Optional[dict] = None
    equity_curve: List[dict] = [] # Данные для графика: [{"date": "...", "balance": ...}]
    tag_stats: List[dict] = [] # Статистика по тегам: [{"tag": "...", "pnl": ..., "win_rate": ...}]

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
import models

class TradeBase(BaseModel):
    symbol: str
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None
    direction: models.TradeDirection
    entry_price: float
    quantity: float
    leverage: Optional[float] = 1.0
    entry_at: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_amount: Optional[float] = None
    setup_name: Optional[str] = None
    timeframe: Optional[str] = None
    news_event: Optional[str] = None
    screenshot_url: Optional[str] = None
    entry_reason: Optional[str] = None  # Причина/логика входа
    exit_reason: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = []
    commission: Optional[float] = 0
    entry_commission: Optional[float] = 0
    exit_commission: Optional[float] = 0
    swap: Optional[float] = 0
    confidence: Optional[int] = Field(None, ge=1, le=10)
    # Новые поля
    currency: Optional[str] = "RUB"
    operations: Optional[list] = []  # Детали операций для аккордеона

class TradeCreate(TradeBase):
    account_id: int

class TradeClose(BaseModel):
    exit_price: float
    exit_at: datetime
    exit_reason: Optional[str] = None
    mae_price: Optional[float] = None
    mfe_price: Optional[float] = None

class TradeUpdate(BaseModel):
    symbol: Optional[str] = None
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None
    direction: Optional[models.TradeDirection] = None
    entry_price: Optional[float] = None
    quantity: Optional[float] = None
    leverage: Optional[float] = None
    entry_at: Optional[datetime] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_amount: Optional[float] = None
    setup_name: Optional[str] = None
    timeframe: Optional[str] = None
    news_event: Optional[str] = None
    screenshot_url: Optional[str] = None
    entry_reason: Optional[str] = None
    exit_reason: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    commission: Optional[float] = None
    entry_commission: Optional[float] = None
    exit_commission: Optional[float] = None
    swap: Optional[float] = None
    confidence: Optional[int] = Field(None, ge=1, le=10)

class Trade(TradeBase):
    id: int
    account_id: int
    exit_price: Optional[float] = None
    exit_at: Optional[datetime] = None
    pnl: Optional[float] = None
    net_pnl: Optional[float] = None
    mae_price: Optional[float] = None
    mfe_price: Optional[float] = None
    ai_analysis: Optional[dict] = None
    # Новые поля
    position_id: Optional[int] = None
    r_multiple: Optional[float] = None
    holding_time_minutes: Optional[int] = None

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
    total_roi: float = 0
    expected_ghpr: float = 0
    sortino_ratio: float = 0
    max_drawdown_pct: float = 0
    max_drawdown_abs: float = 0
    current_drawdown_pct: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    largest_win: float = 0
    largest_loss: float = 0
    max_win_streak: int = 0
    max_loss_streak: int = 0
    current_streak: int = 0
    current_streak_type: Optional[str] = None
    tail_ratio: float = 0
    risk_of_ruin: Optional[dict] = None
    r_distribution: Optional[dict] = None
    trade_duration: Optional[dict] = None
    monte_carlo: Optional[dict] = None
    time_patterns: Optional[dict] = None
    mae_mfe_analysis: Optional[dict] = None
    equity_curve: List[dict] = [] # Данные для графика: [{"date": "...", "balance": ...}]
    tag_stats: List[dict] = [] # Статистика по тегам: [{"tag": "...", "pnl": ..., "win_rate": ...}]

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Enum, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
import datetime

Base = declarative_base()

class TradeDirection(enum.Enum):
    LONG = "long"
    SHORT = "short"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    settings = Column(JSON, default={})

    accounts = relationship("Account", back_populates="owner")

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    balance = Column(Numeric(precision=18, scale=8), default=0)
    currency = Column(String, default="RUB")

    owner = relationship("User", back_populates="accounts")
    trades = relationship("Trade", back_populates="account")

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    symbol = Column(String, index=True, nullable=False)
    asset_name = Column(String) # Полное название (напр. "АФК Система")
    asset_type = Column(String) # Тип (Stock, Futures, Bond, Currency)
    direction = Column(Enum(TradeDirection), nullable=False)
    
    # Вход и выход
    entry_price = Column(Numeric(precision=18, scale=8), nullable=False)
    exit_price = Column(Numeric(precision=18, scale=8))
    exit_reason = Column(String) # Причина выхода (Strategy, Time, Panic, etc.)
    quantity = Column(Numeric(precision=18, scale=8), nullable=False)
    leverage = Column(Float, default=1.0) # Плечо
    entry_at = Column(DateTime, nullable=False)
    exit_at = Column(DateTime)
    
    # Риск-менеджмент
    stop_loss = Column(Numeric(precision=18, scale=8))
    take_profit = Column(Numeric(precision=18, scale=8))
    risk_amount = Column(Numeric(precision=18, scale=8)) # Риск в валюте (напр. $100)
    
    # Продвинутые метрики (MAE/MFE)
    mae_price = Column(Numeric(precision=18, scale=8)) # Худшая цена во время сделки
    mfe_price = Column(Numeric(precision=18, scale=8)) # Лучшая цена во время сделки
    
    # Результат
    pnl = Column(Numeric(precision=18, scale=8))
    commission = Column(Numeric(precision=18, scale=8), default=0)
    
    # Метаданные
    setup_name = Column(String) # Название стратегии (Тактика)
    timeframe = Column(String) # Таймфрейм (1m, 5m, 1H, 4H, 1D)
    news_event = Column(String) # Событие рядом (напр. "Отчетность", "Ставка ЦБ")
    screenshot_url = Column(String) # Ссылка на скриншот графика
    emotions = Column(String)
    notes = Column(String)
    tags = Column(JSON, default=[]) # Теги сделки (напр. ["FOMO", "Trend"])
    ai_analysis = Column(JSON) # Результат анализа от AI
    
    account = relationship("Account", back_populates="trades")

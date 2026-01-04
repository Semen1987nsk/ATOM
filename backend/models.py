from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Enum, Numeric, Index
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
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)  # nullable for OAuth users
    is_active = Column(Integer, default=1)  # 1 = active, 0 = disabled
    is_admin = Column(Integer, default=0)  # 1 = admin, 0 = regular user
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login = Column(DateTime, nullable=True)  # Последний вход
    settings = Column(JSON, default={})
    
    # OAuth fields
    oauth_provider = Column(String, nullable=True)  # google, yandex, sber, tinkoff
    oauth_provider_id = Column(String, nullable=True)  # ID from provider
    
    # Marketing / Analytics fields
    registration_source = Column(String, default="email")  # email, google, yandex, sber, tinkoff
    utm_source = Column(String, nullable=True)  # Источник трафика
    utm_medium = Column(String, nullable=True)  # Канал (cpc, organic, social)
    utm_campaign = Column(String, nullable=True)  # Название кампании
    referrer = Column(String, nullable=True)  # Откуда пришёл пользователь

    accounts = relationship("Account", back_populates="owner")
    subscriptions = relationship("Subscription", back_populates="user")
    payments = relationship("Payment", back_populates="user")


class SubscriptionPlan(enum.Enum):
    FREE = "free"
    PRO = "pro"  # 399₽/мес для РФ
    CORPORATE = "corporate"  # Индивидуально (проп-трейдинг)


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class Subscription(Base):
    """Модель подписки пользователя"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.FREE)
    is_active = Column(Integer, default=1)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    auto_renew = Column(Integer, default=1)  # 1 = auto-renew, 0 = cancel at expiry
    
    # Лимиты по плану
    max_trades = Column(Integer, nullable=True)  # None = unlimited
    max_accounts = Column(Integer, default=1)
    ai_analysis_enabled = Column(Integer, default=0)
    
    user = relationship("User", back_populates="subscriptions")


class Payment(Base):
    """История платежей"""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    currency = Column(String, default="RUB")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    
    # Данные платежа
    payment_method = Column(String)  # card, yookassa, sberbank, tinkoff
    external_id = Column(String, nullable=True)  # ID в платёжной системе
    description = Column(String, nullable=True)
    
    # Карта (маскированная)
    card_last4 = Column(String(4), nullable=True)
    card_type = Column(String, nullable=True)  # visa, mastercard, mir
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="payments")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String, nullable=False)
    balance = Column(Numeric(precision=18, scale=8), default=0)
    currency = Column(String, default="RUB")

    owner = relationship("User", back_populates="accounts")
    trades = relationship("Trade", back_populates="account")

class Trade(Base):
    __tablename__ = "trades"
    
    # Составные индексы для оптимизации частых запросов
    __table_args__ = (
        Index('ix_trades_account_symbol', 'account_id', 'symbol'),
        Index('ix_trades_symbol_entry_at', 'symbol', 'entry_at'),
        Index('ix_trades_entry_at', 'entry_at'),
        Index('ix_trades_exit_at', 'exit_at'),
        Index('ix_trades_direction', 'direction'),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    symbol = Column(String, index=True, nullable=False)
    asset_name = Column(String) # Полное название (напр. "АФК Система")
    asset_type = Column(String) # Тип (Stock, Futures, Bond, Currency)
    direction = Column(Enum(TradeDirection), nullable=False)
    
    # Вход и выход
    entry_price = Column(Numeric(precision=18, scale=8), nullable=False)
    exit_price = Column(Numeric(precision=18, scale=8))
    entry_reason = Column(String) # Причина/логика входа (для ИИ анализа)
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
    net_pnl = Column(Numeric(precision=18, scale=8)) # Чистая прибыль (PnL - Comm - Swap)
    commission = Column(Numeric(precision=18, scale=8), default=0)
    entry_commission = Column(Numeric(precision=18, scale=8), default=0)
    exit_commission = Column(Numeric(precision=18, scale=8), default=0)
    swap = Column(Numeric(precision=18, scale=8), default=0) # Плата за перенос позиции
    
    # Метаданные
    setup_name = Column(String) # Название стратегии (Тактика)
    timeframe = Column(String) # Таймфрейм (1m, 5m, 1H, 4H, 1D)
    news_event = Column(String) # Событие рядом (напр. "Отчетность", "Ставка ЦБ")
    screenshot_url = Column(String) # Ссылка на скриншот графика
    emotions = Column(String)
    confidence = Column(Integer) # Уверенность при входе (1-10)
    notes = Column(String)
    tags = Column(JSON, default=[]) # Теги сделки (напр. ["FOMO", "Trend"])
    ai_analysis = Column(JSON) # Результат анализа от AI
    
    # Новые поля для группировки и аналитики
    currency = Column(String, default="RUB") # Валюта сделки
    position_id = Column(Integer, index=True) # ID позиции (группирует операции)
    operations = Column(JSON, default=[]) # Детали операций для аккордеона
    # Пример: [{"type": "entry", "price": 14.117, "qty": 7000, "time": "09:50:45", "commission": 50}]
    
    r_multiple = Column(Float) # PnL / Risk = сколько "R" заработал
    holding_time_minutes = Column(Integer) # Время удержания позиции в минутах
    
    account = relationship("Account", back_populates="trades")


class ArticleCategory(enum.Enum):
    NEWS = "news"  # Новости
    GUIDES = "guides"  # Гайды и обучение
    ANALYTICS = "analytics"  # Аналитика рынка
    TIPS = "tips"  # Советы трейдерам
    UPDATES = "updates"  # Обновления платформы


class Article(Base):
    """Статьи блога"""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)  # URL-friendly ID
    title = Column(String, nullable=False)
    excerpt = Column(String, nullable=True)  # Краткое описание для превью
    content = Column(String, nullable=False)  # Markdown контент
    cover_image = Column(String, nullable=True)  # URL обложки
    
    category = Column(Enum(ArticleCategory), default=ArticleCategory.NEWS)
    tags = Column(JSON, default=[])  # ["trading", "psychology", "risk"]
    
    author_id = Column(Integer, ForeignKey("users.id"), index=True)
    is_published = Column(Integer, default=0)  # 0 = draft, 1 = published
    is_featured = Column(Integer, default=0)  # 1 = показывать в топе
    
    views_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    
    # SEO
    meta_title = Column(String, nullable=True)
    meta_description = Column(String, nullable=True)
    
    author = relationship("User")

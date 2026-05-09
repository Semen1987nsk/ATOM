from pydantic import BaseModel, Field, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional, List, Any, Dict
from decimal import Decimal
import models


# ==================== GENERIC RESPONSES ====================
# Общие схемы — для эндпоинтов, которые раньше возвращали dict без response_model.
# Это дисциплинирует OpenAPI и не пускает наружу случайные внутренние поля.

class MessageResponse(BaseModel):
    """Простой ответ с сообщением (для action endpoints без объекта)."""
    message: str
    detail: Optional[str] = None


class ImportResultResponse(BaseModel):
    """Ответ от /trades/import."""
    message: str
    imported: int
    skipped: int
    duplicates_found: int
    total_in_file: int
    balance_saved: bool = False
    range_processed: Optional[Dict[str, int]] = None


class HealthResponse(BaseModel):
    """Ответ /health."""
    status: str
    service: str
    version: Optional[str] = None


class ReadinessCheck(BaseModel):
    ok: bool
    error: Optional[str] = None
    note: Optional[str] = None


class ReadinessResponse(BaseModel):
    """Ответ /ready."""
    status: str
    service: str
    version: str
    checks: Dict[str, ReadinessCheck]


# ==================== AUTH SCHEMAS ====================

class UserCreate(BaseModel):
    """Схема для регистрации пользователя"""
    email: EmailStr
    name: Optional[str] = None
    # OWASP 2024: минимум 12 символов для финансового SaaS.
    # Раньше было 6 — недопустимо при наличии денежных операций.
    password: str = Field(..., min_length=12, max_length=128)
    # 152-ФЗ ст. 9: явное согласие на обработку ПД обязательно при регистрации.
    # Без этого поля регистрация юридически невалидна для РФ-граждан.
    pd_consent: bool = Field(..., description="Согласие на обработку персональных данных (152-ФЗ)")


class DeleteAccountRequest(BaseModel):
    """Запрос на удаление аккаунта (152-ФЗ ст. 14)."""
    password: str = Field(..., min_length=1, description="Пароль для подтверждения")
    reason: Optional[str] = Field(None, max_length=500, description="Причина удаления (опционально, для feedback)")


class PdDeletionsStatusResponse(BaseModel):
    """Статус очереди удалений для админа (152-ФЗ ст. 21 ч. 5)."""
    pending_count: int = Field(..., description="Сколько аккаунтов в grace period (ждут финализации)")
    overdue_count: int = Field(..., description="Сколько уже истекли (>30 дней) и должны быть анонимизированы")
    finalized_count: int = Field(..., description="Сколько аккаунтов уже анонимизированы (email = deleted-*@anon.eqio)")
    grace_period_days: int = Field(30, description="Текущий grace period")
    next_finalization_at: Optional[datetime] = Field(None, description="Когда финализируется ближайший аккаунт (UTC)")
    last_scheduler_run_at: Optional[datetime] = Field(None, description="Когда scheduler последний раз отрабатывал finalize")


class UserDataExport(BaseModel):
    """
    Экспорт всех персональных данных пользователя (152-ФЗ ст. 14 — право доступа).

    Содержит ВСЁ что мы храним на пользователя, кроме:
    - hashed_password (это дайджест, не сам пароль; не возвращаем)
    - BrokerConnection.api_token (зашифрован Fernet, в открытом виде не отдаём)
    - Внутренние счётчики и кеши

    Формат — JSON. Пользователь сам решает что с ним делать (в т.ч. передать
    в другой сервис для миграции).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Метаинформация экспорта
    export_version: str = Field("1", description="Версия формата экспорта (для будущих миграций)")
    exported_at: datetime = Field(..., description="Когда сформирован экспорт (UTC)")
    request_id: Optional[str] = Field(None, description="X-Request-ID для аудита запроса")
    policy_version: str = Field(..., description="Версия политики конфиденциальности на момент экспорта")

    # Данные пользователя — каждая категория отдельным dict/list, чтобы JSON был самоописательный
    user: Dict[str, Any]
    accounts: List[Dict[str, Any]]
    subscriptions: List[Dict[str, Any]]
    payments: List[Dict[str, Any]]
    pd_consents: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    daily_reviews: List[Dict[str, Any]]
    setups: List[Dict[str, Any]]
    deposit_history: List[Dict[str, Any]]
    capital_operations: List[Dict[str, Any]]
    balance_snapshots: List[Dict[str, Any]]
    broker_connections: List[Dict[str, Any]]  # БЕЗ api_token

    # Сводка
    counts: Dict[str, int] = Field(..., description="Количество записей по каждой категории")


class UserLogin(BaseModel):
    """Схема для входа"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """Ответ с данными пользователя (без пароля)"""
    id: int
    email: str
    name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None
    settings: dict = {}
    oauth_provider: Optional[str] = None
    registration_source: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    """Схема для обновления профиля"""
    name: Optional[str] = None
    settings: Optional[dict] = None

class Token(BaseModel):
    """JWT токен (legacy, только access)"""
    access_token: str
    token_type: str = "bearer"


class TokenPair(BaseModel):
    """Пара JWT токенов: access + refresh"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # Время жизни access токена в секундах (30 мин)


class TokenRefreshRequest(BaseModel):
    """Запрос на обновление токенов"""
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    """Данные из токена"""
    user_id: Optional[int] = None
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Запрос на смену пароля"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)


# ==================== DEPOSIT SCHEMAS ====================

class DepositOperationCreate(BaseModel):
    """Создание операции с депозитом"""
    operation_type: str  # initial, deposit, withdrawal
    amount: float
    date: datetime
    note: Optional[str] = None

class DepositOperationResponse(BaseModel):
    """Ответ с операцией депозита"""
    id: int
    operation_type: str
    amount: float
    balance_after: float
    date: datetime
    note: Optional[str] = None
    created_at: datetime
    source: str = "manual"
    can_delete: bool = True
    
    model_config = ConfigDict(from_attributes=True)

class AccountBalanceResponse(BaseModel):
    """Информация о балансе аккаунта"""
    account_id: int
    initial_balance: float
    current_balance: float  # initial + deposits - withdrawals + pnl
    total_deposits: float
    total_withdrawals: float
    total_pnl: float
    currency: str
    net_deposit: float = 0
    local_current_balance: float = 0
    journal_pnl: float = 0
    broker_current_balance: Optional[float] = None
    broker_pnl: Optional[float] = None
    pnl_gap: Optional[float] = None
    balance_source: str = "journal"

class EquityCurvePoint(BaseModel):
    """Точка кривой капитала"""
    date: str
    balance: float
    pnl_cumulative: float
    deposit_balance: float  # Баланс без учёта PnL (только депозиты)


class BalanceSnapshotResponse(BaseModel):
    id: int
    date: datetime
    balance: float
    source: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==================== TRADE SCHEMAS ====================

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
    confidence: Optional[int] = Field(None, ge=1, le=5)  # Уверенность 1-5
    # Психо-трекер
    mood: Optional[int] = Field(None, ge=1, le=5)  # Настроение: 1=😤 2=😟 3=😐 4=😊 5=🚀
    discipline: Optional[int] = Field(None, ge=1, le=5)  # Следование плану 1-5
    # Сетап
    setup_id: Optional[int] = None
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
    exit_commission: Optional[float] = 0
    swap: Optional[float] = None  # If provided, overrides existing swap on trade

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
    confidence: Optional[int] = Field(None, ge=1, le=5)
    mood: Optional[int] = Field(None, ge=1, le=5)
    discipline: Optional[int] = Field(None, ge=1, le=5)
    setup_id: Optional[int] = None


# Setup/Strategy schemas
class SetupBase(BaseModel):
    name: str
    description: Optional[str] = None
    rules: Optional[str] = None
    color: Optional[str] = "#00d4aa"
    icon: Optional[str] = "📈"
    is_active: Optional[bool] = True

class SetupCreate(SetupBase):
    account_id: int

class SetupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None

class Setup(SetupBase):
    id: int
    account_id: int
    created_at: datetime
    
    # Статистика (добавляется динамически)
    trades_count: Optional[int] = 0
    win_rate: Optional[float] = 0
    avg_pnl: Optional[float] = 0
    total_pnl: Optional[float] = 0
    
    model_config = ConfigDict(from_attributes=True)


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
    # Setup relation (simplified)
    setup: Optional[SetupBase] = None

    model_config = ConfigDict(from_attributes=True)

class DashboardStats(BaseModel):
    total_pnl: float
    unrealized_pnl: float = 0
    total_pnl_with_unrealized: float = 0
    initial_balance: float = 0
    current_balance: float = 0
    period_start_balance: Optional[float] = None
    period_end_balance: float = 0
    period_start_date: Optional[str] = None
    period_start_net_deposit: float = 0
    period_start_realized_pnl: float = 0
    period_start_balance_reliable: bool = True
    period_start_balance_source: str = "derived"
    period_start_balance_reason: Optional[str] = None
    win_rate: float
    total_trades: int
    profitable_trades: int
    optimal_f: float  # Основное значение (PnL-метод)
    optimal_f_data: Optional[dict] = None  # Полные данные: pnl_method, r_method, сравнение
    sqn: Optional[dict] = None
    z_score: Optional[dict] = None
    profit_factor: float = 0
    r_expectancy: float = 0
    recovery_factor: float = 0
    total_roi: Optional[float] = None
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
    calmar_ratio: Optional[dict] = None
    risk_of_ruin: Optional[dict] = None
    r_distribution: Optional[dict] = None
    trade_duration: Optional[dict] = None
    monte_carlo: Optional[dict] = None
    time_patterns: Optional[dict] = None
    mae_mfe_analysis: Optional[dict] = None
    equity_curve: List[dict] = [] # Данные для графика: [{"date": "...", "balance": ...}]
    imoex_curve: List[dict] = [] # IMOEX overlay для сравнения: [{"date": "YYYY-MM-DD", "value": ...}]
    tag_stats: List[dict] = [] # Статистика по тегам: [{"tag": "...", "pnl": ..., "win_rate": ...}]

# ==================== BLOG SCHEMAS ====================

class ArticleCreate(BaseModel):
    """Создание статьи"""
    title: str = Field(..., min_length=3, max_length=200)
    slug: Optional[str] = None  # Если не указан, генерируется из title
    excerpt: Optional[str] = Field(None, max_length=500)
    content: str = Field(..., min_length=10)
    cover_image: Optional[str] = None
    category: str = "news"  # news, guides, analytics, tips, updates
    tags: List[str] = []
    is_published: bool = False
    is_featured: bool = False
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None

class ArticleUpdate(BaseModel):
    """Обновление статьи"""
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    slug: Optional[str] = None
    excerpt: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = Field(None, min_length=10)
    cover_image: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None

class ArticleResponse(BaseModel):
    """Ответ со статьёй"""
    id: int
    slug: str
    title: str
    excerpt: Optional[str] = None
    content: str
    cover_image: Optional[str] = None
    category: str
    tags: List[str] = []
    author_id: int
    author_name: Optional[str] = None
    is_published: bool
    is_featured: bool
    views_count: int
    likes_count: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class ArticleListItem(BaseModel):
    """Краткая информация о статье для списка"""
    id: int
    slug: str
    title: str
    excerpt: Optional[str] = None
    cover_image: Optional[str] = None
    category: str
    tags: List[str] = []
    author_name: Optional[str] = None
    views_count: int
    likes_count: int
    created_at: datetime
    published_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

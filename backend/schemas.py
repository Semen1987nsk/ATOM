from pydantic import BaseModel, Field, EmailStr, ConfigDict, computed_field, model_validator
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
    finalized_count: int = Field(..., description="Сколько аккаунтов уже анонимизированы (email = deleted-*@anon.empirik)")
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
    totp_code: Optional[str] = None

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


class AuthSuccess(BaseModel):
    """SEC-08: успешная авторизация без токенов в теле.

    Токены ставятся только в httpOnly cookies (set_auth_cookies). Тело
    несёт лишь метаданные сессии — frontend читает токены исключительно из кук.
    """
    token_type: str = "bearer"
    expires_in: int
    authenticated: bool = True


class TokenRefreshRequest(BaseModel):
    """Запрос на обновление токенов"""
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    """Данные из токена.

    PR 26: добавлены jti + expires_at для поддержки revocation.
    """
    user_id: Optional[int] = None
    email: Optional[str] = None
    jti: Optional[str] = None
    # Unix timestamp срока действия — нужен при записи в revoked_tokens,
    # чтобы знать когда строку можно удалить (cleanup cron).
    exp_ts: Optional[int] = None
    # API-07: Unix timestamp выпуска (iat) — сверяется с User.tokens_valid_after
    # для инвалидации сессий при reset/change-password.
    iat_ts: Optional[int] = None


class TotpEnableResponse(BaseModel):
    """PR 26 Phase 2: ответ /auth/2fa/enable с QR data."""
    secret: str
    provisioning_uri: str


class TotpVerifyRequest(BaseModel):
    code: str


class PasswordResetRequest(BaseModel):
    """PR 26: запрос ссылки для сброса пароля."""
    email: str


class PasswordResetConfirm(BaseModel):
    """PR 26: установить новый пароль по one-time token."""
    token: str
    new_password: str = Field(..., min_length=12, max_length=128)


class ChangePasswordRequest(BaseModel):
    """Запрос на смену пароля"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12, max_length=128)


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
    # Сервер резолвит активный счёт (auth_service.get_account_id);
    # поле опционально для обратной совместимости со старыми клиентами.
    account_id: Optional[int] = None

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
    # Cost-basis в валюте инструмента (рубли для MOEX). Сумма абсолютных
    # payment'ов входных/выходных лотов FIFO. PR 18 — нужно для корректного
    # pnl_pct у фьючерсов где entry_price хранится в пунктах.
    entry_value: Optional[float] = None
    exit_value: Optional[float] = None
    mae_price: Optional[float] = None
    mfe_price: Optional[float] = None
    ai_analysis: Optional[dict] = None
    # Новые поля
    position_id: Optional[int] = None
    r_multiple: Optional[float] = None
    holding_time_minutes: Optional[int] = None
    # PR 19: greenfield Tinkoff fields для UI (иконки типа актива, источник
    # данных, ссылка на InstrumentORM по UID для drill-down).
    instrument_uid: Optional[str] = None
    instrument_figi: Optional[str] = None
    instrument_type_v2: Optional[str] = None  # share|bond|etf|futures|option|currency
    data_source: Optional[str] = None  # tinkoff_v2|legacy|manual
    # Phase 9 (2026-05-17): per-trade point_value snapshot для futures.
    # Backfilled через empirical formula |payment|/(qty×price) для existing
    # trades. Future trades заполняются в pipeline на момент closing.
    point_value: Optional[float] = None
    point_value_source: Optional[str] = None  # live_api|cache|empirical_payment|manual_override
    # Setup relation (simplified)
    setup: Optional[SetupBase] = None

    @model_validator(mode='after')
    def _normalize_asset_type(self) -> 'Trade':
        # BUG-005: брокерские сделки в БД могут хранить asset_type как T-API
        # lowercase enum ('share'/'futures'/'etf'...) либо как NULL (Tinkoff
        # пишет в instrument_type_v2). Frontend EditTradeModal dropdown
        # ожидает Capitalized ('Stock'/'Futures'/...) — при mismatch select
        # схлопывается на дефолт 'Stock' и PATCH перепишет real type.
        # Маппим T-API enum → UI strings (consistent с AddTradeModal options).
        mapping = {
            'share': 'Stock',
            'bond': 'Bond',
            'etf': 'ETF',
            'futures': 'Futures',
            'option': 'Option',
            'currency': 'Currency',
        }
        if self.asset_type and self.asset_type.lower() in mapping:
            self.asset_type = mapping[self.asset_type.lower()]
        elif not self.asset_type and self.instrument_type_v2:
            self.asset_type = mapping.get(
                self.instrument_type_v2.lower(),
                self.instrument_type_v2.capitalize(),
            )
        return self

    @computed_field  # type: ignore[misc]
    @property
    def body_from_prices(self) -> Optional[float]:
        """Phase 9 (2026-05-17): прозрачный body P&L из цен открытия/закрытия.

        Для FUTURES: `body = (exit - entry) × qty × point_value × sign(direction)`.
        Это математически тождественно сумме всех variation margin от entry
        до exit + post-clearing settlement (MOEX telescoping identity).

        Для SHARES/ETF/BOND/CURRENCY: возвращает Trade.pnl (он уже = (exit-entry)*qty).

        Используется в журнале как "наглядный body" — отдельно от Trade.net_pnl
        (который для futures в Phase 6/7 архитектуре складывается через
        varmargin attribution). Read-only computed field, не пишется в БД.

        Returns None если:
        - open trade (нет exit_price)
        - futures без point_value snapshot (нужен backfill)
        """
        if self.exit_price is None or self.entry_price is None or self.quantity is None:
            return None
        # Non-futures: Trade.pnl уже = body. Возвращаем как есть.
        if self.instrument_type_v2 != "futures":
            return float(self.pnl) if self.pnl is not None else None
        # Futures: требуем point_value snapshot
        if self.point_value is None or self.point_value <= 0:
            return None
        direction_str = str(self.direction).lower()
        if "long" in direction_str:
            sign = 1.0
        elif "short" in direction_str:
            sign = -1.0
        else:
            return None
        return float(
            (float(self.exit_price) - float(self.entry_price))
            * float(self.quantity)
            * float(self.point_value)
            * sign
        )

    @computed_field  # type: ignore[misc]
    @property
    def pnl_pct(self) -> Optional[float]:
        """
        Процент прибыли/убытка относительно cost-basis в валюте сделки.

        Приоритеты знаменателя:
        1. `entry_value` (рубли) — точная сумма входа от FIFO. Это
           правильное значение для **всех** типов, включая фьючерсы,
           где entry_price в пунктах, а pnl в рублях.
        2. Fallback: `entry_price × |quantity|` — работает для акций
           и legacy/manual-сделок без entry_value.

        Знак pnl_pct всегда совпадает со знаком pnl (direction учтён в pnl).
        """
        if self.pnl is None:
            return None
        # Primary: entry_value в валюте.
        if self.entry_value is not None and self.entry_value > 0:
            return round((float(self.pnl) / float(self.entry_value)) * 100, 4)
        # Fallback: price × qty (только для legacy / акций).
        if (
            self.entry_price is None
            or self.entry_price <= 0
            or self.quantity is None
        ):
            return None
        entry_total = float(self.entry_price) * abs(float(self.quantity))
        if entry_total == 0:
            return None
        return round((float(self.pnl) / entry_total) * 100, 4)

    model_config = ConfigDict(from_attributes=True)


# ─────────────── TR1: Trade Journal aggregation ───────────────


class TradeExecution(BaseModel):
    """Один execution внутри position_id round-trip.

    Соответствует одной Trade ORM row — либо closed slice (entry+exit),
    либо open lot (entry only, exit_at=None).
    """

    id: int
    entry_at: datetime
    exit_at: Optional[datetime] = None
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    direction: str  # 'long' | 'short'
    pnl: Optional[float] = None
    net_pnl: Optional[float] = None
    commission: Optional[float] = None
    entry_value: Optional[float] = None
    exit_value: Optional[float] = None
    # TR1.1: power-user fields для drill-down
    mae_price: Optional[float] = None  # Max Adverse Excursion на этом execution
    mfe_price: Optional[float] = None  # Max Favorable Excursion
    screenshot_url: Optional[str] = None
    setup_name: Optional[str] = None
    risk_amount: Optional[float] = None
    # TR1.3: per-execution attributed fees
    varmargin_attributed: Optional[float] = None
    margin_fee_attributed: Optional[float] = None
    service_fee_attributed: Optional[float] = None
    other_fees_attributed: Optional[float] = None
    # Phase 9 (2026-05-17): point_value snapshot для futures + computed body_from_prices
    point_value: Optional[float] = None
    point_value_source: Optional[str] = None
    instrument_type_v2: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def body_from_prices(self) -> Optional[float]:
        """Phase 9: body = (exit-entry)*qty*pv*sign(direction) для futures.

        Для не-futures Trade.pnl уже хранит body. См. schemas.Trade.body_from_prices.
        """
        if self.exit_price is None or self.entry_price is None:
            return None
        if self.instrument_type_v2 != "futures":
            return float(self.pnl) if self.pnl is not None else None
        if self.point_value is None or self.point_value <= 0:
            return None
        direction_str = str(self.direction).lower()
        if "long" in direction_str:
            sign = 1.0
        elif "short" in direction_str:
            sign = -1.0
        else:
            return None
        return float(
            (float(self.exit_price) - float(self.entry_price))
            * float(self.quantity)
            * float(self.point_value)
            * sign
        )

    model_config = ConfigDict(from_attributes=True)


class PositionTrade(BaseModel):
    """Агрегированная позиция = round-trip lifecycle от quantity=0 до 0.

    Группа Trade rows с одинаковым `position_id`. Включает scaled-in
    добавления и partial closes. Используется UI Journal для one-row-per-trade
    представления (Tradervue / TraderSync / TradeZella pattern).
    """

    # Composite identity (position_id уникален только внутри (account_id, instrument_uid))
    position_id: int
    account_id: int
    instrument_uid: Optional[str] = None
    symbol: str
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None
    direction: str  # 'long' | 'short' (from first execution)

    # Aggregated metrics
    total_quantity: float  # абсолют total объёма (для closed = сумма exit qty; для open = remaining)
    weighted_entry_price: float
    weighted_exit_price: Optional[float] = None  # None если позиция open
    realized_pnl: Optional[float] = None  # Σ net_pnl закрытых rows
    unrealized_pnl: Optional[float] = None  # Σ PositionORM.unrealized_pnl открытых rows
    total_commission: float = 0
    total_entry_value: Optional[float] = None
    total_exit_value: Optional[float] = None

    # Lifecycle timing
    first_entry_at: datetime
    last_exit_at: Optional[datetime] = None  # None если позиция всё ещё open
    holding_time_minutes: Optional[int] = None  # для closed positions

    # Status
    status: str  # 'open' | 'closed'
    execution_count: int
    is_scale_in: bool  # true если execution_count >= 2

    # Setup / tags (от первого execution; решение по AskUserQuestion 2026-05-16)
    setup_id: Optional[int] = None
    setup_name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

    # TR1.1: power-user metrics (aggregated)
    pnl_pct: Optional[float] = None  # (P&L / total_entry_value) × 100
    r_multiple: Optional[float] = None  # realized_pnl / Σ risk_amount
    total_risk_amount: Optional[float] = None  # знаменатель для R
    mae_price: Optional[float] = None  # MIN(execution.mae_price) — worst price
    mfe_price: Optional[float] = None  # MAX(execution.mfe_price) — best price

    # TR1.1: row indicators (для gutter иконок)
    has_screenshot: bool = False
    has_notes: bool = False

    # TR1.1: journaling-specific (от первого execution)
    confidence: Optional[int] = None  # 1-5
    mood: Optional[int] = None  # 1-5
    discipline: Optional[int] = None  # 1-5
    timeframe: Optional[str] = None
    news_event: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    entry_reason: Optional[str] = None
    exit_reason: Optional[str] = None
    screenshot_url: Optional[str] = None  # от первого execution (для quick preview)

    # TR1.3: aggregated attributed fees (Σ по executions)
    total_varmargin: Optional[float] = None
    total_margin_fee: Optional[float] = None
    total_service_fee: Optional[float] = None
    total_other_fees: Optional[float] = None
    # Body P&L (gross без any fees) — для breakdown «Из чего сложился P&L»
    body_pnl: Optional[float] = None

    # Individual executions для accordion drill-down
    executions: list[TradeExecution] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[misc]
    @property
    def body_from_prices(self) -> Optional[float]:
        """Phase 9 (2026-05-17): Σ body_from_prices по всем executions.

        Для futures aggregated value = sum of (exit-entry)*qty*pv*sign per execution.
        Для не-futures = sum of Trade.pnl (= body для shares).
        None если ни одна closed execution не имеет данных.
        """
        if not self.executions:
            return None
        total: float = 0.0
        any_valid = False
        for ex in self.executions:
            bp = ex.body_from_prices
            if bp is not None:
                total += bp
                any_valid = True
        return total if any_valid else None


class DashboardStats(BaseModel):
    total_pnl: float
    unrealized_pnl: float = 0
    # TR1.2: account-level varmargin (futures daily settlement). Tinkoff API
    # не атрибутирует varmargin к конкретной позиции (нет instrument_uid),
    # поэтому показываем суммой по аккаунту. Это REAL realized P&L для
    # futures — деньги уже выплачены в cash через ежедневный clearing.
    varmargin_total: float = 0
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
    # PR 23: для broker-юзера — текущий баланс счёта (cash из portfolio.total_amount).
    # Это единственная честная цифра при margin/futures-трейдинге.
    current_cash_balance: Optional[float] = None
    open_positions_count: Optional[int] = None
    initial_balance_source: Optional[str] = None
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
    max_drawdown_peak_date: Optional[str] = None
    max_drawdown_trough_date: Optional[str] = None
    max_drawdown_duration_days: Optional[int] = None
    max_drawdown_peak_value: Optional[float] = None
    max_drawdown_trough_value: Optional[float] = None
    drawdown_baseline: float = 0  # реальный capital baseline для % метрик (для UI шапки кривой)
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
    equity_curve_gross: List[dict] = []  # Phase 11: gross variant equity curve (без commissions/fees)
    imoex_curve: List[dict] = [] # IMOEX overlay для сравнения: [{"date": "YYYY-MM-DD", "value": ...}]
    tag_stats: List[dict] = [] # Статистика по тегам: [{"tag": "...", "pnl": ..., "win_rate": ...}]
    # Phase 10 (2026-05-17): P&L Health Check cached status для UI badge.
    # {status: ok|warning|mismatch|na|stale, diff_pct, diff_rub, checked_at, breakdown}
    pnl_health: Optional[dict] = None
    # Phase 11 (2026-05-17): gross variants для toggle 'с/без комиссий'.
    # Net (default, matches broker) vs Gross (только body P&L от движения цены).
    total_pnl_gross: float = 0
    total_pnl_with_unrealized_gross: float = 0
    account_level_adjustments_gross: float = 0
    # Phase 12 (2026-05-17): отдельная карточка «Расходы» (best practices).
    # total_costs = разница net vs gross headline.
    # breakdown: {broker_commission, margin_fees, service_fees, taxes}
    # (2026-05-18: margin_fees + service_fees заменили общий attributed_fees
    # для гранулярного UI карточки расходов на дашборде.)
    total_costs: float = 0
    total_costs_breakdown: dict = {}
    # Phase 6.4 (2026-05-18): broker cash truth для PnLHealthBadge.
    # cash_truth_pnl = last_portfolio_value − Σ NET_DEPOSIT. Surface'ится отдельно
    # от headline (total_pnl_with_unrealized = realized + unrealized, journal-style).
    cash_truth_pnl: float = 0

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

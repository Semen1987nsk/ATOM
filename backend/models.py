from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Enum, Numeric, Index, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
import enum
from utils.datetime_utils import utc_now_naive

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
    created_at = Column(DateTime, default=utc_now_naive)
    last_login = Column(DateTime, nullable=True)  # Последний вход
    settings = Column(JSON, default=dict)
    
    # OAuth fields
    oauth_provider = Column(String, nullable=True)  # google, yandex, sber, tinkoff
    oauth_provider_id = Column(String, nullable=True)  # ID from provider
    
    # Marketing / Analytics fields
    registration_source = Column(String, default="email")  # email, google, yandex, sber, tinkoff
    utm_source = Column(String, nullable=True)  # Источник трафика
    utm_medium = Column(String, nullable=True)  # Канал (cpc, organic, social)
    utm_campaign = Column(String, nullable=True)  # Название кампании
    referrer = Column(String, nullable=True)  # Откуда пришёл пользователь

    # 152-ФЗ: запрос на удаление аккаунта (soft-delete, 30-дневный grace period)
    deletion_requested_at = Column(DateTime, nullable=True, index=True)

    accounts = relationship("Account", back_populates="owner", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    pd_consents = relationship("PdConsent", back_populates="user", cascade="all, delete-orphan")


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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.FREE)
    is_active = Column(Integer, default=1)
    started_at = Column(DateTime, default=utc_now_naive)
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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    
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
    
    created_at = Column(DateTime, default=utc_now_naive)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="payments")


class DepositOperationType(enum.Enum):
    INITIAL = "initial"      # Начальный депозит
    DEPOSIT = "deposit"      # Пополнение
    WITHDRAWAL = "withdrawal"  # Снятие


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name = Column(String, nullable=False)
    balance = Column(Numeric(precision=18, scale=8), default=0)
    initial_balance = Column(Numeric(precision=18, scale=8), default=0)  # Начальный депозит
    currency = Column(String, default="RUB")

    owner = relationship("User", back_populates="accounts")
    trades = relationship("Trade", back_populates="account", cascade="all, delete-orphan")
    deposit_history = relationship("DepositHistory", back_populates="account", cascade="all, delete-orphan")
    setups = relationship("Setup", back_populates="account", cascade="all, delete-orphan")


class DailyReview(Base):
    """
    Daily Review — рефлексия дня + намерение на завтра.

    1 строка = 1 день для конкретного account. Reflection — общий разбор дня.
    Trade reflections (per-trade comments) хранятся в trade_reflections JSON
    как { "trade_id": "комментарий" }.
    """
    __tablename__ = "daily_reviews"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    reflection = Column(String, default="")  # как прошёл день
    intention = Column(String, default="")  # что планирую на завтра
    trade_reflections = Column(JSON, default=dict)  # { trade_id: comment }
    rating = Column(Integer, nullable=True)  # 1-5 общая оценка дня
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint("account_id", "date", name="uq_review_account_date"),
    )


class DepositHistory(Base):
    """История изменений депозита (пополнения/снятия)"""
    __tablename__ = "deposit_history"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    operation_type = Column(Enum(DepositOperationType), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)  # Положительное для депозита, отрицательное для снятия
    balance_after = Column(Numeric(precision=18, scale=8), nullable=False)  # Баланс после операции
    date = Column(DateTime, nullable=False)  # Дата операции
    note = Column(String, nullable=True)  # Комментарий
    created_at = Column(DateTime, default=utc_now_naive)

    account = relationship("Account", back_populates="deposit_history")


class BalanceSnapshot(Base):
    """Снимок баланса на определённую дату (из отчётов брокера или API)"""
    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    date = Column(DateTime, nullable=False, index=True)  # Дата снимка
    balance = Column(Numeric(precision=18, scale=8), nullable=False)  # Общий баланс
    
    # Детализация баланса (для API-снапшотов)
    cash = Column(Numeric(precision=18, scale=8), default=0)  # Свободные деньги
    stocks_value = Column(Numeric(precision=18, scale=8), default=0)  # Стоимость акций
    bonds_value = Column(Numeric(precision=18, scale=8), default=0)  # Стоимость облигаций
    etf_value = Column(Numeric(precision=18, scale=8), default=0)  # Стоимость ETF
    futures_value = Column(Numeric(precision=18, scale=8), default=0)  # Стоимость фьючерсов
    unrealized_pnl = Column(Numeric(precision=18, scale=8), default=0)  # Нереализованный P/L
    
    source = Column(String, nullable=True)  # Источник: "tinkoff_api", "import", "manual"
    created_at = Column(DateTime, default=utc_now_naive)

    account = relationship("Account")
    
    __table_args__ = (
        Index('ix_balance_snapshots_account_date', 'account_id', 'date'),
    )


class CapitalOperation(Base):
    """Операции ввода/вывода средств"""
    __tablename__ = "capital_operations"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    broker_id = Column(String, index=True)  # ID операции у брокера
    operation_type = Column(String, nullable=False)  # "deposit" или "withdrawal"
    amount = Column(Numeric(precision=18, scale=8), nullable=False)  # Сумма
    currency = Column(String, default="RUB")
    date = Column(DateTime, nullable=False, index=True)
    description = Column(String)  # Описание (напр. "Пополнение с карты")
    created_at = Column(DateTime, default=utc_now_naive)
    
    account = relationship("Account")
    
    __table_args__ = (
        Index('ix_capital_ops_account_date', 'account_id', 'date'),
    )


class Setup(Base):
    """Сетап/Стратегия торговли"""
    __tablename__ = "setups"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    name = Column(String, nullable=False)  # Название: "Breakout", "Mean Reversion"
    description = Column(String)  # Описание стратегии
    rules = Column(String)  # Правила входа/выхода
    color = Column(String, default="#00d4aa")  # Цвет для UI
    icon = Column(String, default="📈")  # Emoji иконка
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now_naive)
    
    account = relationship("Account", back_populates="setups")
    trades = relationship("Trade", back_populates="setup")


class Trade(Base):
    __tablename__ = "trades"

    # Составные индексы + защита от дублей.
    # PR 7: расширен ключ до (account_id, symbol, entry_at, exit_at,
    # direction, data_source). Без exit_at FIFO-движок не мог создать
    # несколько trades для одной buy-операции с partial-SELL'ами (одинаковый
    # entry_at). Без data_source legacy/tinkoff_v2/manual сидели в одном
    # namespace, мешая replace-стратегии нового sync.
    __table_args__ = (
        UniqueConstraint(
            'account_id', 'symbol', 'entry_at', 'exit_at', 'direction', 'data_source',
            name='uq_trades_dedup_v2',
        ),
        Index('ix_trades_account_symbol', 'account_id', 'symbol'),
        Index('ix_trades_symbol_entry_at', 'symbol', 'entry_at'),
        Index('ix_trades_entry_at', 'entry_at'),
        Index('ix_trades_exit_at', 'exit_at'),
        Index('ix_trades_direction', 'direction'),
        # Composite index под частый паттерн: stats / analytics страницы
        # фильтруют по account и сортируют/режут по диапазону дат.
        Index('ix_trades_account_entry_exit', 'account_id', 'entry_at', 'exit_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
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
    # leverage и r_multiple — финансовые величины, Float тут даёт накопление ошибок
    # при последующих умножениях. Numeric(10,6) — точность до 0.000001.
    leverage = Column(Numeric(precision=10, scale=6), default=1) # Плечо
    entry_at = Column(DateTime, nullable=False)
    exit_at = Column(DateTime)
    
    # Риск-менеджмент
    stop_loss = Column(Numeric(precision=18, scale=8))
    take_profit = Column(Numeric(precision=18, scale=8))
    risk_amount = Column(Numeric(precision=18, scale=8)) # Риск в валюте (напр. $100)
    
    # Продвинутые метрики (MAE/MFE)
    mae_price = Column(Numeric(precision=18, scale=8)) # Худшая цена во время сделки
    mfe_price = Column(Numeric(precision=18, scale=8)) # Лучшая цена во время сделки
    post_exit_analysis = Column(JSON) # Анализ движения цены после закрытия
    
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
    emotions = Column(String)  # Deprecated, use mood instead
    confidence = Column(Integer) # Уверенность при входе (1-5)
    notes = Column(String)
    
    # Психо-трекер
    mood = Column(Integer)  # Настроение при входе: 1=😤 2=😟 3=😐 4=😊 5=🚀
    discipline = Column(Integer)  # Следование плану: 1-5
    
    # Сетап/Стратегия
    setup_id = Column(Integer, ForeignKey("setups.id", ondelete="SET NULL"), nullable=True)
    tags = Column(JSON, default=list) # Теги сделки (напр. ["FOMO", "Trend"])
    ai_analysis = Column(JSON) # Результат анализа от AI
    
    # Новые поля для группировки и аналитики
    currency = Column(String, default="RUB") # Валюта сделки
    position_id = Column(Integer, index=True) # ID позиции (группирует операции)
    operations = Column(JSON, default=list) # Детали операций для аккордеона
    # Пример: [{"type": "entry", "price": 14.117, "qty": 7000, "time": "09:50:45", "commission": 50}]
    
    r_multiple = Column(Numeric(precision=10, scale=6)) # PnL / Risk = сколько "R" заработал
    holding_time_minutes = Column(Integer) # Время удержания позиции в минутах

    # PR 0 (greenfield Tinkoff rewrite): источник данных сделки.
    # 'legacy'     — импортирована старым tinkoff_service (удалён в PR 0).
    # 'tinkoff_v2' — новый sync (появится в PR 5+).
    # 'manual'     — ручной ввод / Excel-импорт.
    # На уровне БД — обычный String (см. миграцию 0003), валидируется в Python.
    data_source = Column(String(32), nullable=False, default="legacy", server_default="legacy")

    # PR 2: UID/figi инструмента из T-Invest API. instrument_uid — primary
    # для нового sync (стабилен при делистинге, единственный для опционов).
    # instrument_type_v2 дублирует asset_type, но точнее (enum из T-API
    # вместо строки). Все три поля nullable — legacy-сделки их не имеют.
    instrument_uid = Column(String(64), nullable=True, index=True)
    instrument_figi = Column(String(32), nullable=True)
    position_uid = Column(String(64), nullable=True, index=True)
    instrument_type_v2 = Column(String(32), nullable=True)  # share|bond|etf|futures|option|currency

    account = relationship("Account", back_populates="trades")
    setup = relationship("Setup", back_populates="trades")


class BrokerType(enum.Enum):
    TINKOFF = "tinkoff"
    BCS = "bcs"  # Будущее
    FINAM = "finam"  # Будущее


class BrokerConnection(Base):
    """Подключение к брокеру для автосинхронизации"""
    __tablename__ = "broker_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    broker = Column(Enum(BrokerType), nullable=False)
    
    # Токен API (зашифрованный в будущем)
    api_token = Column(String, nullable=False)
    broker_account_id = Column(String, nullable=True)  # ID счёта в брокере
    
    # Статус
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)  # success, error, partial
    last_sync_error = Column(String, nullable=True)
    
    # Настройки синхронизации
    auto_sync_enabled = Column(Boolean, default=True)
    sync_interval_minutes = Column(Integer, default=60)  # Каждые N минут
    sync_from_date = Column(DateTime, nullable=True)  # С какой даты синхронизировать
    
    # Статистика
    total_synced_trades = Column(Integer, default=0)

    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    # ── PR 2: greenfield Tinkoff rewrite ──
    # Курсор последней успешной синхронизации (OperationsByCursor).
    # Пустая строка = full sync на следующем запуске (первое подключение
    # или ручной reset).
    sync_cursor = Column(String(256), nullable=True)
    # PR 4: ID мастер-ключа AESGCM, которым зашифрован api_token.
    # При ротации мастер-ключа увеличиваем номер; старые записи
    # расшифровываются по своему key_id.
    key_id = Column(Integer, nullable=False, default=1, server_default="1")
    # PR 15: счётчик подряд идущих ошибок и время до которого circuit
    # breaker открыт (orchestrator пропускает аккаунт пока circuit_open_until > now).
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default="0")
    circuit_open_until = Column(DateTime, nullable=True)
    # PR 4: время последней записи в token_audit_log (для оптимизации
    # фильтров «у каких аккаунтов давно не было запросов к API»).
    last_audit_at = Column(DateTime, nullable=True)

    account = relationship("Account", backref="broker_connections")


# ════════════════════════════════════════════════════════════════════════
# PR 2: новые таблицы для greenfield Tinkoff rewrite
# ════════════════════════════════════════════════════════════════════════


class InstrumentORM(Base):
    """Кэш справочника инструментов из T-Invest API.

    Заполняется в bootstrap_instruments_cache (PR 6) и обновляется лениво
    при первом столкновении с неизвестным UID. Domain-уровень — `domain.entities.Instrument`.
    """

    __tablename__ = "instruments"
    __table_args__ = (
        Index("ix_instruments_figi", "figi"),
        Index("ix_instruments_ticker_class", "ticker", "class_code"),
        Index("ix_instruments_type", "instrument_type"),
    )

    uid = Column(String(64), primary_key=True)
    figi = Column(String(32), nullable=True)
    ticker = Column(String(32), nullable=True)
    class_code = Column(String(32), nullable=True)
    instrument_type = Column(String(32), nullable=False)  # share|bond|etf|futures|option|currency
    isin = Column(String(32), nullable=True)
    name = Column(String(256), nullable=True)
    lot = Column(Integer, nullable=False, default=1, server_default="1")
    currency = Column(String(8), nullable=False, default="rub", server_default="rub")

    nominal = Column(Numeric(precision=18, scale=8), nullable=True)
    min_price_increment = Column(Numeric(precision=18, scale=8), nullable=True)
    min_price_increment_amount = Column(Numeric(precision=18, scale=8), nullable=True)

    # Bond:
    coupon_quantity_per_year = Column(Integer, nullable=True)
    amortization_flag = Column(Boolean, nullable=False, default=False, server_default="0")
    floating_coupon_flag = Column(Boolean, nullable=False, default=False, server_default="0")
    maturity_date = Column(DateTime, nullable=True)
    placement_price = Column(Numeric(precision=18, scale=8), nullable=True)

    # Future / Option:
    expiration_date = Column(DateTime, nullable=True)
    basic_asset_size = Column(Numeric(precision=18, scale=8), nullable=True)
    basic_asset_uid = Column(String(64), nullable=True)
    strike_price = Column(Numeric(precision=18, scale=8), nullable=True)
    option_direction = Column(String(8), nullable=True)
    option_style = Column(String(16), nullable=True)
    option_multiplier = Column(Integer, nullable=True)

    # Любые дополнительные поля по типу инструмента (для расширения без миграций).
    extra = Column(JSON, nullable=True)

    cached_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)


class PositionORM(Base):
    """Текущие открытые позиции с mark-to-market PnL (PR 11).

    Один (account_id, instrument_uid) — одна запись. После закрытия
    позиции запись либо удаляется, либо помечается quantity=0 и не
    отображается в UI.
    """

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "instrument_uid", name="uq_positions_account_instrument"),
        Index("ix_positions_account_id", "account_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    instrument_uid = Column(String(64), nullable=False)
    instrument_type = Column(String(32), nullable=False)

    quantity = Column(Integer, nullable=False, default=0, server_default="0")
    avg_entry_price = Column(Numeric(precision=18, scale=8), nullable=False)
    current_price = Column(Numeric(precision=18, scale=8), nullable=True)
    unrealized_pnl = Column(Numeric(precision=18, scale=8), nullable=True)
    last_priced_at = Column(DateTime, nullable=True)
    currency = Column(String(8), nullable=False, default="rub", server_default="rub")

    # Bond: current_aci, remaining_nominal, coupons_received.
    # Future: accumulated_varmargin, point_value_snapshot.
    # Option: multiplier, strike, expiration_date, basic_asset_uid.
    extra = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)


class TokenAuditLogORM(Base):
    """Audit log использования брокерского токена.

    НЕ хранит сам токен — только factual метаданные о вызовах: какой метод
    дёрнули, какой статус вернулся, latency. Нужен для:
    * Compliance и расследований (если токен утёк);
    * Отладки rate-limit'ов и ошибок Tinkoff API в продакшне;
    * Аналитики «давно не было запросов» → подсветка пользователю.
    """

    __tablename__ = "token_audit_log"
    __table_args__ = (
        Index("ix_token_audit_account_time", "account_id", "created_at"),
        Index("ix_token_audit_status", "status_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # account_id (наш) — без FK CASCADE, потому что audit log должен переживать
    # удаление аккаунта (для compliance расследований post-mortem).
    account_id = Column(Integer, nullable=False)
    # SHA-256 от user_id (без соли) — анонимизация в логах. PII в audit
    # храним по минимуму.
    user_id_hash = Column(String(64), nullable=True)
    method = Column(String(64), nullable=False)  # 'get_accounts', 'get_operations_by_cursor', ...
    endpoint = Column(String(128), nullable=False)
    status_code = Column(Integer, nullable=False)  # gRPC status code
    latency_ms = Column(Integer, nullable=False)
    error_detail = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now_naive, index=True)


class OperationORM(Base):
    """Сырая операция из T-Invest API (PR 5).

    Источник истины для FIFO-движка (PR 7). UPSERT по (account_id, operation_id) —
    Tinkoff гарантирует уникальность `id` per аккаунт.

    Денежные поля разложены на units/nano/currency, чтобы:
    * вообще не использовать float (Decimal с потерями преобразуется в БД);
    * легко поднимать обратно в `MoneyValue` без потерь точности;
    * быстро фильтровать в SQL по знаку payment'а (Numeric тоже работал бы,
      но Numeric в SQLite — это TEXT, сравнения медленнее).

    `account_id` (Integer) — FK на `accounts.id` (наш внутренний).
    `broker_account_id` (String) — id счёта у Тинькофф (например, '2135909232').
    """

    __tablename__ = "operations"
    __table_args__ = (
        # operation_id у Tinkoff уникален per аккаунт. Дедупликация только
        # по нему — NULL в instrument_uid (PayIn/PayOut/Tax) сломал бы
        # композитный UNIQUE при участии instrument_uid.
        UniqueConstraint("account_id", "operation_id", name="uq_operations_account_opid"),
        Index("ix_operations_account_executed_at", "account_id", "executed_at"),
        Index("ix_operations_instrument_uid", "instrument_uid"),
        Index("ix_operations_type", "operation_type"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # ── ownership / linkage ──
    account_id = Column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    # Хранится отдельно от account_id, потому что счетов в одном Account.id
    # может быть несколько (БС/ИИС/SECURITIES).
    broker_account_id = Column(String(64), nullable=False, index=True)

    # ── Tinkoff identifiers ──
    operation_id = Column(String(64), nullable=False)
    parent_operation_id = Column(String(64), nullable=True)
    instrument_uid = Column(String(64), nullable=True)
    instrument_figi = Column(String(32), nullable=True)
    instrument_type = Column(String(32), nullable=True)  # share|bond|etf|futures|option|currency

    # ── core ──
    operation_type = Column(String(48), nullable=False)  # 'buy'|'sell'|'coupon'|...
    state = Column(String(32), nullable=False)  # 'executed'|'canceled'|'progress'
    quantity = Column(Integer, nullable=False, default=0, server_default="0")

    # ── MoneyValue tuples (units, nano, currency) ──
    price_units = Column(Integer, nullable=True)
    price_nano = Column(Integer, nullable=True)
    price_currency = Column(String(8), nullable=True)

    payment_units = Column(Integer, nullable=True)
    payment_nano = Column(Integer, nullable=True)
    payment_currency = Column(String(8), nullable=True)

    commission_units = Column(Integer, nullable=True)
    commission_nano = Column(Integer, nullable=True)
    commission_currency = Column(String(8), nullable=True)

    # Накопленный купонный доход (для облигаций).
    aci_units = Column(Integer, nullable=True)
    aci_nano = Column(Integer, nullable=True)
    aci_currency = Column(String(8), nullable=True)

    # ── meta ──
    executed_at = Column(DateTime, nullable=False)
    description = Column(String(512), nullable=True)
    synced_at = Column(DateTime, nullable=False, default=utc_now_naive)


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
    tags = Column(JSON, default=list)  # ["trading", "psychology", "risk"]
    
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    is_published = Column(Integer, default=0)  # 0 = draft, 1 = published
    is_featured = Column(Integer, default=0)  # 1 = показывать в топе
    
    views_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    published_at = Column(DateTime, nullable=True)
    
    # SEO
    meta_title = Column(String, nullable=True)
    meta_description = Column(String, nullable=True)

    author = relationship("User")


class PdConsent(Base):
    """
    Журнал согласий на обработку персональных данных (152-ФЗ ст. 9 ч. 4).

    Каждое согласие записывается отдельной строкой с версией текста, IP и UA — это
    доказательная база при проверке РКН. Отзыв согласия не удаляет запись (revoked_at),
    а ставит timestamp.
    """
    __tablename__ = "pd_consents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    consent_text_version = Column(String, nullable=False)  # "v1", "v2" — версия политики
    accepted_at = Column(DateTime, default=utc_now_naive, nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv4 (15) или IPv6 (45)
    user_agent = Column(String, nullable=True)
    revoked_at = Column(DateTime, nullable=True)  # NULL = активно, заполнено = отозвано

    user = relationship("User", back_populates="pd_consents")

    __table_args__ = (
        Index("ix_pd_consents_user_active", "user_id", "revoked_at"),
    )

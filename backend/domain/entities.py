"""
Domain entities (Pydantic v2). Иммутабельные DTO между adapter-слоем
и application-слоем.

Почему Pydantic v2, а не dataclass? Здесь нужна валидация (`uid` непустой,
`quantity > 0`, и т.п.) и сериализация (FastAPI response_model в PR 12).
Dataclass для value_objects подходит, для domain-сущностей с входной
валидацией — Pydantic.

Все модели с `model_config = ConfigDict(frozen=True)` — read-only после
создания, безопасно передавать между корутинами.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDirection,
)
from domain.value_objects import MoneyValue


# ── Operation ──


class Operation(BaseModel):
    """Одна операция из T-Invest API.

    Уникальна в рамках `(account_id, instrument_uid, operation_id)`.
    Это и есть unique-key для UPSERT в `operations` таблице (PR 5).

    Не путать с `Trade`: операции — сырые события из брокера (BUY/SELL,
    DIVIDEND, COUPON, и т.п.). Trade — результат FIFO-матчинга
    операций trading_types (PR 7).
    """

    model_config = ConfigDict(frozen=True)

    operation_id: str = Field(..., min_length=1)
    parent_operation_id: Optional[str] = None
    account_id: str = Field(..., min_length=1)
    instrument_uid: Optional[str] = None  # nullable для PayIn/PayOut и налогов
    instrument_figi: Optional[str] = None  # secondary, для логов
    instrument_type: Optional[InstrumentType] = None
    operation_type: OperationType
    state: OperationState

    # Количество в штуках (или contracts для фьючерсов / лотов для валют —
    # уточняется на уровне instrument.lot и pnl/<type>.py).
    quantity: int = Field(default=0, ge=0)
    # Цена за единицу. Может быть None для не-торговых операций.
    price: Optional[MoneyValue] = None
    # Итоговая сумма в валюте счёта. Знак: BUY < 0, SELL > 0, DIVIDEND > 0.
    payment: Optional[MoneyValue] = None
    # Комиссия (если известна на уровне самой операции).
    commission: Optional[MoneyValue] = None
    # Накопленный купонный доход для облигаций (НКД).
    asset_uid_aci: Optional[MoneyValue] = None

    executed_at: datetime  # UTC
    description: Optional[str] = None
    trades_id: Optional[str] = None  # internal Tinkoff trade_id для cross-reference


# ── Trade ──


class Trade(BaseModel):
    """FIFO-сматченная сделка для журнала.

    Получается из последовательности `Operation` объектов одного инструмента
    с применением FIFO-движка (см. application/fifo_matching.py, PR 7).
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    instrument_uid: str
    instrument_figi: Optional[str] = None
    instrument_type: InstrumentType
    direction: TradeDirection

    quantity: int = Field(..., gt=0)
    entry_price: Decimal
    exit_price: Optional[Decimal] = None  # None = открытая
    entry_at: datetime
    exit_at: Optional[datetime] = None  # None = открытая

    pnl: Optional[Decimal] = None  # gross PnL до комиссий и налогов
    net_pnl: Optional[Decimal] = None  # после комиссий, налогов, varmargin
    commission_total: Decimal = Field(default=Decimal(0))
    tax_total: Decimal = Field(default=Decimal(0))
    # Cost-basis в валюте инструмента (рубли для MOEX). Сумма абсолютных
    # значений payment'ов входных лотов FIFO. Используется для расчёта
    # pnl_pct корректно для всех типов инструментов (особенно фьючерсов,
    # где entry_price в пунктах, а pnl в рублях). PR 18.
    entry_value: Optional[Decimal] = None
    exit_value: Optional[Decimal] = None
    currency: str = "rub"

    entry_operation_ids: tuple[str, ...] = ()
    exit_operation_ids: tuple[str, ...] = ()

    # TR1: round-trip group ID. Все Trade rows одного position lifecycle
    # (от open от quantity=0 до полного close) разделяют один position_id.
    # Используется UI Journal для агрегации scaled-in добавлений.
    position_id: Optional[int] = None

    # TR1.3: per-trade attribution для account-level fees (margin_fee,
    # service_fee, varmargin без uid, generic tax). Заполняется в pipeline
    # после FIFO match через domain/pnl/fee_attribution.py.
    varmargin_attributed: Optional[Decimal] = None
    margin_fee_attributed: Optional[Decimal] = None
    service_fee_attributed: Optional[Decimal] = None
    other_fees_attributed: Optional[Decimal] = None

    # Phase 9 (2026-05-17): point_value snapshot для futures.
    # При FIFO match вычисляется empirically (|payment|/(qty×price)) или
    # берётся из InstrumentORM cache. Snapshot защищает historical Trade
    # от изменений instrument cache (Tinkoff dynamically обновляет FX-scaling
    # для USD-denominated futures). Используется в schemas.Trade.body_from_prices
    # для прозрачного отображения P&L в журнале.
    point_value: Optional[Decimal] = None
    point_value_source: Optional[str] = None  # live_api|cache|empirical_payment|manual_override

    # Для фьючерсов сохраняем point_value снепшотом момента сделки (PR 9).
    extra: dict[str, Any] = Field(default_factory=dict)


# ── Position ──


class Position(BaseModel):
    """Текущая открытая позиция с mark-to-market PnL.

    Один инструмент в одном аккаунте — одна Position. После закрытия
    позиции запись либо удаляется, либо помечается `quantity=0`.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    instrument_uid: str
    instrument_type: InstrumentType
    quantity: int  # signed: положительное = LONG, отрицательное = SHORT
    avg_entry_price: Decimal
    current_price: Optional[Decimal] = None  # MTM, обновляется в pipeline
    unrealized_pnl: Optional[Decimal] = None
    last_priced_at: Optional[datetime] = None
    currency: str = "rub"

    # Per-instrument context:
    # bonds:    {'current_aci': '12.50', 'remaining_nominal': '1000.00', 'coupons_received': '24.00'}
    # futures:  {'accumulated_varmargin': '1500.00', 'point_value_snapshot': '10.0'}
    # options:  {'multiplier': 100, 'strike': '4000.00', 'expiration_date': '2026-06-19T00:00:00Z'}
    extra: dict[str, Any] = Field(default_factory=dict)


# ── Instrument ──


class Instrument(BaseModel):
    """Кэшируемый справочник инструмента.

    Заполняется в bootstrap_instruments_cache (PR 6) и обновляется лениво
    при первом столкновении с неизвестным UID. Поля — только те, которые
    нужны journal-у; полный proto-объект мы не храним.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    figi: Optional[str] = None
    ticker: Optional[str] = None
    class_code: Optional[str] = None
    instrument_type: InstrumentType
    isin: Optional[str] = None
    name: Optional[str] = None
    lot: int = 1
    currency: str = "rub"

    # Финансовая специфика — заполняется по типу.
    nominal: Optional[Decimal] = None  # Bond: номинал; Currency: размер лота в валюте
    min_price_increment: Optional[Decimal] = None  # Future: шаг цены в пунктах
    min_price_increment_amount: Optional[Decimal] = None  # Future: цена шага в RUB

    # Bond:
    coupon_quantity_per_year: Optional[int] = None
    amortization_flag: bool = False
    floating_coupon_flag: bool = False
    maturity_date: Optional[datetime] = None
    placement_price: Optional[Decimal] = None

    # Future / Option:
    expiration_date: Optional[datetime] = None
    basic_asset_size: Optional[Decimal] = None
    basic_asset_uid: Optional[str] = None  # для опционов — UID базового актива

    # Option-specific:
    strike_price: Optional[Decimal] = None
    option_direction: Optional[str] = None  # 'call' | 'put'
    option_style: Optional[str] = None  # 'american' | 'european'
    option_multiplier: Optional[int] = None  # обычно 100

    cached_at: Optional[datetime] = None


# ── BrokerReport (PR 26 Phase 3) ──


class BrokerReportTradeRow(BaseModel):
    """Одна строка из официального брокерского отчёта T-Bank.

    Это **независимый источник истины**: то самое, что Tinkoff показывает
    в личном кабинете в разделе «Отчёты». Используется в reconciliation
    как ground truth против наших аггрегатов из GetOperationsByCursor.

    Поля соответствуют BrokerReport message из investAPI/operations.proto.
    """

    model_config = ConfigDict(frozen=True)

    trade_id: str
    order_id: Optional[str] = None
    figi: Optional[str] = None
    ticker: Optional[str] = None
    name: Optional[str] = None
    class_code: Optional[str] = None
    execute_sign: Optional[str] = None  # 'Б' (buy) / 'П' (sell) кириллицей
    direction: Optional[str] = None  # 'buy' | 'sell' нормализованное
    exchange: Optional[str] = None
    trade_datetime: datetime  # UTC
    quantity: int = Field(default=0)
    price: Optional[Decimal] = None
    # order_amount = quantity × price (без ACI)
    order_amount: Optional[Decimal] = None
    # total_order_amount = order_amount + aci_value
    total_order_amount: Optional[Decimal] = None
    aci_value: Optional[Decimal] = None
    broker_commission: Optional[Decimal] = None
    exchange_commission: Optional[Decimal] = None
    exchange_clearing_commission: Optional[Decimal] = None
    repo_rate: Optional[Decimal] = None
    party: Optional[str] = None
    currency: str = "rub"


class BrokerReportSummary(BaseModel):
    """Агрегированные итоги периода из broker report.

    Вычисляется на стороне сервиса reconciliation_service (т.к. сам Tinkoff
    не возвращает summary напрямую — пагинированные row-level записи).
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    period_start: datetime
    period_end: datetime
    trade_count: int = 0

    # 8 метрик которые мы сверяем с нашими расчётами (D2).
    realized_pnl: Decimal = Field(default=Decimal(0))
    broker_commission_total: Decimal = Field(default=Decimal(0))
    exchange_commission_total: Decimal = Field(default=Decimal(0))
    clearing_commission_total: Decimal = Field(default=Decimal(0))
    dividends_gross: Decimal = Field(default=Decimal(0))
    ndfl_withheld: Decimal = Field(default=Decimal(0))
    net_cash_flow: Decimal = Field(default=Decimal(0))  # deposits − withdrawals
    end_cash_balance: Optional[Decimal] = None


class BrokerReport(BaseModel):
    """Полный broker report за период: метаданные + список trades + summary."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    period_start: datetime
    period_end: datetime
    fetched_at: datetime
    trades: tuple[BrokerReportTradeRow, ...] = ()
    summary: BrokerReportSummary
    # Опционально — сырой JSON-ответ для аудита и golden-master тестов.
    raw: Optional[dict[str, Any]] = None

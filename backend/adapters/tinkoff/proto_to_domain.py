"""
Конвертеры protobuf-сообщений из tinkoff-investments SDK в domain-сущности.

Это единственное место в коде, где разрешено импортировать `tinkoff.invest.*`
типы и работать с их полями. Всё остальное приложение видит только
`domain.entities.*`, благодаря чему:

* domain не зависит от версии SDK — при обновлении proto всё ломается здесь;
* unit-тестирование domain не требует gRPC-моков;
* при смене брокера (если когда-нибудь) этот файл переписывается, остальное
  не трогается.

Функции в этом модуле — pure (без I/O, без сети). Они НЕ ловят исключения
SDK — это делается уровнем выше через `error_mapper.wrap_sdk_errors()`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from domain.entities import Instrument, Operation
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
)
from domain.value_objects import MoneyValue, Quotation


# ════════════════════════════════════════════════════════════════════════
# Money / Quotation
# ════════════════════════════════════════════════════════════════════════


def money_to_money_value(m: Any) -> Optional[MoneyValue]:
    """Tinkoff `MoneyValue` (units, nano, currency) → domain MoneyValue.

    Пустые значения (units==0, nano==0, currency пустая) трактуем как None,
    потому что SDK заполняет нулями вместо отсутствия. Денежные операции
    с реальным нулевым значением встречаются (например, нулевая комиссия
    у sandbox-ордера) — для них передаём currency='rub' явно, и они дадут
    MoneyValue(0, 0, 'rub'), не None.
    """
    if m is None:
        return None
    units = getattr(m, "units", 0) or 0
    nano = getattr(m, "nano", 0) or 0
    currency = getattr(m, "currency", "") or ""
    if units == 0 and nano == 0 and not currency:
        return None
    return MoneyValue(units=units, nano=nano, currency=currency.lower())


def quotation_to_decimal(q: Any) -> Optional[Decimal]:
    """Tinkoff `Quotation` → Decimal. None если q отсутствует или нулевое."""
    if q is None:
        return None
    return Quotation(units=getattr(q, "units", 0) or 0, nano=getattr(q, "nano", 0) or 0).to_decimal()


def money_to_decimal(m: Any) -> Optional[Decimal]:
    """Удобная обёртка: MoneyValue из proto сразу в Decimal."""
    mv = money_to_money_value(m)
    return mv.to_decimal() if mv is not None else None


# ════════════════════════════════════════════════════════════════════════
# Enum mapping
# ════════════════════════════════════════════════════════════════════════


# Маппинг proto-enum → domain enum. SDK возвращает строки вида
# `OPERATION_TYPE_BUY`, `INSTRUMENT_TYPE_SHARE` (через `.name` или
# `__str__()` на enum). Domain хранит строки T-API без префикса.

_OPERATION_TYPE_MAP: dict[str, OperationType] = {
    f"OPERATION_TYPE_{ot.value.upper()}": ot for ot in OperationType
}

_OPERATION_STATE_MAP: dict[str, OperationState] = {
    "OPERATION_STATE_EXECUTED": OperationState.EXECUTED,
    "OPERATION_STATE_CANCELED": OperationState.CANCELED,
    "OPERATION_STATE_PROGRESS": OperationState.PROGRESS,
    "OPERATION_STATE_UNSPECIFIED": OperationState.UNSPECIFIED,
}

_INSTRUMENT_TYPE_MAP: dict[str, InstrumentType] = {
    "INSTRUMENT_TYPE_SHARE": InstrumentType.SHARE,
    "INSTRUMENT_TYPE_BOND": InstrumentType.BOND,
    "INSTRUMENT_TYPE_ETF": InstrumentType.ETF,
    "INSTRUMENT_TYPE_FUTURES": InstrumentType.FUTURES,
    "INSTRUMENT_TYPE_OPTION": InstrumentType.OPTION,
    "INSTRUMENT_TYPE_CURRENCY": InstrumentType.CURRENCY,
    "INSTRUMENT_TYPE_SP": InstrumentType.SP,
    "INSTRUMENT_TYPE_UNSPECIFIED": InstrumentType.UNSPECIFIED,
}


def _enum_name(value: Any) -> str:
    """Достать строковое имя enum, аккуратно к разным типам."""
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if name:
        return name
    return str(value).upper()


def parse_operation_type(value: Any) -> OperationType:
    return _OPERATION_TYPE_MAP.get(_enum_name(value), OperationType.UNSPECIFIED)


def parse_operation_state(value: Any) -> OperationState:
    return _OPERATION_STATE_MAP.get(_enum_name(value), OperationState.UNSPECIFIED)


def parse_instrument_type(value: Any) -> Optional[InstrumentType]:
    """Принимает proto-enum или строку из API (`'share'`, `'bond'`...)."""
    if value is None:
        return None
    name = _enum_name(value)
    if name in _INSTRUMENT_TYPE_MAP:
        return _INSTRUMENT_TYPE_MAP[name]
    # Строки из OperationItem.instrument_type ('share', 'bond', ...).
    raw = str(value).lower()
    for it in InstrumentType:
        if it.value == raw:
            return it
    return InstrumentType.UNSPECIFIED


# ════════════════════════════════════════════════════════════════════════
# DateTime
# ════════════════════════════════════════════════════════════════════════


def _ensure_utc(dt: Any) -> datetime:
    """Привести datetime к timezone-aware UTC.

    Tinkoff SDK возвращает datetime'ы из protobuf — обычно tz-aware UTC,
    но иногда naive (зависит от версии protobuf). Принудительно нормируем.
    """
    if not isinstance(dt, datetime):
        # Может прилететь Timestamp protobuf. ToDatetime() даёт naive UTC.
        if hasattr(dt, "ToDatetime"):
            dt = dt.ToDatetime()
        else:
            raise TypeError(f"Cannot interpret datetime from {type(dt).__name__}")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ════════════════════════════════════════════════════════════════════════
# Operation
# ════════════════════════════════════════════════════════════════════════


def operation_from_proto(op: Any, *, account_id: Optional[str] = None) -> Operation:
    """OperationItem (из get_operations_by_cursor.items) → domain Operation.

    `account_id` обычно есть в самом ответе как `broker_account_id`, но
    иногда отсутствует у legacy/sandbox операций — тогда передаём извне.
    """
    raw_account = getattr(op, "broker_account_id", "") or account_id or ""

    return Operation(
        operation_id=getattr(op, "id", "") or "",
        parent_operation_id=getattr(op, "parent_operation_id", None) or None,
        account_id=raw_account,
        instrument_uid=(getattr(op, "instrument_uid", None) or None) or None,
        instrument_figi=(getattr(op, "figi", None) or None) or None,
        instrument_type=parse_instrument_type(getattr(op, "instrument_type", None)),
        operation_type=parse_operation_type(getattr(op, "type", None)),
        state=parse_operation_state(getattr(op, "state", None)),
        quantity=int(getattr(op, "quantity", 0) or 0),
        price=money_to_money_value(getattr(op, "price", None)),
        payment=money_to_money_value(getattr(op, "payment", None)),
        commission=money_to_money_value(getattr(op, "commission", None)),
        asset_uid_aci=money_to_money_value(getattr(op, "accrued_int", None)),
        executed_at=_ensure_utc(getattr(op, "date", None)),
        description=getattr(op, "description", None) or None,
        trades_id=None,  # trades_info — это список, мы не сохраняем подробности
    )


# ════════════════════════════════════════════════════════════════════════
# Instrument
# ════════════════════════════════════════════════════════════════════════


def _instrument_common(raw: Any, instrument_type: InstrumentType) -> dict[str, Any]:
    """Поля, общие для Share / Bond / Etf / Future / Option / Currency."""
    return {
        "uid": getattr(raw, "uid", "") or "",
        "figi": getattr(raw, "figi", None) or None,
        "ticker": getattr(raw, "ticker", None) or None,
        "class_code": getattr(raw, "class_code", None) or None,
        "instrument_type": instrument_type,
        "isin": getattr(raw, "isin", None) or None,
        "name": getattr(raw, "name", None) or None,
        "lot": int(getattr(raw, "lot", 1) or 1),
        "currency": (getattr(raw, "currency", "rub") or "rub").lower(),
    }


def instrument_from_proto(
    raw: Any,
    instrument_type: InstrumentType,
    *,
    cached_at: Optional[datetime] = None,
) -> Instrument:
    """
    Универсальный конвертер. `raw` может быть `Share`, `Bond`, `Etf`, `Future`,
    `Option`, `Currency` — поля специфичные подтягиваются по типу.
    """
    common = _instrument_common(raw, instrument_type)
    extra: dict[str, Any] = {}

    nominal = quotation_to_decimal(getattr(raw, "nominal", None))
    min_pi = quotation_to_decimal(getattr(raw, "min_price_increment", None))
    min_pi_amount: Optional[Decimal] = None

    coupon_qty = None
    amortization = bool(getattr(raw, "amortization_flag", False))
    floating = bool(getattr(raw, "floating_coupon_flag", False))
    maturity = None
    placement_price: Optional[Decimal] = None

    expiration = None
    basic_asset_size: Optional[Decimal] = None
    basic_asset_uid: Optional[str] = None

    strike_price: Optional[Decimal] = None
    option_direction: Optional[str] = None
    option_style: Optional[str] = None
    option_multiplier: Optional[int] = None

    if instrument_type == InstrumentType.BOND:
        coupon_qty = getattr(raw, "coupon_quantity_per_year", None)
        maturity_dt = getattr(raw, "maturity_date", None)
        maturity = _ensure_utc(maturity_dt) if maturity_dt else None
        placement_price = money_to_decimal(getattr(raw, "placement_price", None))

    elif instrument_type == InstrumentType.FUTURES:
        min_pi_amount = money_to_decimal(getattr(raw, "min_price_increment_amount", None))
        exp_dt = getattr(raw, "expiration_date", None)
        expiration = _ensure_utc(exp_dt) if exp_dt else None
        bas_size = getattr(raw, "basic_asset_size", None)
        basic_asset_size = quotation_to_decimal(bas_size)
        basic_asset_uid = getattr(raw, "basic_asset_position_uid", None) or None
        extra["basic_asset"] = getattr(raw, "basic_asset", None) or None

    elif instrument_type == InstrumentType.OPTION:
        # Опционы: strike, direction (CALL/PUT), style (AMERICAN/EUROPEAN).
        strike_price = quotation_to_decimal(getattr(raw, "strike_price", None))
        # SDK enum: OptionDirection.OPTION_DIRECTION_CALL / OPTION_DIRECTION_PUT
        dir_name = _enum_name(getattr(raw, "direction", None))
        if dir_name.endswith("CALL"):
            option_direction = "call"
        elif dir_name.endswith("PUT"):
            option_direction = "put"
        style_name = _enum_name(getattr(raw, "style", None))
        if "AMERICAN" in style_name:
            option_style = "american"
        elif "EUROPEAN" in style_name:
            option_style = "european"
        bas_size = getattr(raw, "basic_asset_size", None)
        basic_asset_size = quotation_to_decimal(bas_size)
        basic_asset_uid = getattr(raw, "basic_asset_position_uid", None) or None
        # Tinkoff multiplier обычно не передаётся в Option-сообщении явно;
        # вычисляется как basic_asset_size. Сохраняем как поле для наглядности,
        # но также оставляем в extra.
        if basic_asset_size is not None and basic_asset_size > 0:
            option_multiplier = int(basic_asset_size)
        exp_dt = getattr(raw, "expiration_date", None)
        expiration = _ensure_utc(exp_dt) if exp_dt else None

    elif instrument_type == InstrumentType.CURRENCY:
        # У Currency лот = размер партии, nominal — обычно сама валюта.
        # Деталей хватает того, что есть в _instrument_common.
        pass

    return Instrument(
        **common,
        nominal=nominal,
        min_price_increment=min_pi,
        min_price_increment_amount=min_pi_amount,
        coupon_quantity_per_year=coupon_qty,
        amortization_flag=amortization,
        floating_coupon_flag=floating,
        maturity_date=maturity,
        placement_price=placement_price,
        expiration_date=expiration,
        basic_asset_size=basic_asset_size,
        basic_asset_uid=basic_asset_uid,
        strike_price=strike_price,
        option_direction=option_direction,
        option_style=option_style,
        option_multiplier=option_multiplier,
        cached_at=cached_at or datetime.now(tz=timezone.utc),
    )

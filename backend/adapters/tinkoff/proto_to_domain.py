"""
Конвертеры protobuf-сообщений из t-tech-investments SDK в domain-сущности.

Это единственное место в коде, где разрешено импортировать `t_tech.invest.*`
типы и работать с их полями (раньше `tinkoff.invest.*` до AU10 migration).
Всё остальное приложение видит только `domain.entities.*`, благодаря чему:

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

from domain.entities import BrokerReportTradeRow, Instrument, Operation
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
)
from domain.value_objects import MoneyValue, Quotation

from logger import get_logger

_log = get_logger("tinkoff.proto_to_domain")

# PR 26 (Phase 3, T5 fix): bounds check для nano поля.
# По T-API спецификации nano всегда |nano| < 1_000_000_000 (это «доли единицы»).
# Если присылают больше — это либо bug API либо corrupted data; молча
# принимать → portfolio value ×10. Log warning + clamp до безопасного значения.
_NANO_MAX = 999_999_999


# ════════════════════════════════════════════════════════════════════════
# Money / Quotation
# ════════════════════════════════════════════════════════════════════════


def _clamp_nano(nano: int, units: int, context: str = "") -> int:
    """PR 26 (Phase 3, T5): защита от malformed nano > 1e9.

    Молча принимать nano=2_000_000_000 → portfolio value ×10. Log warning
    и clamp до безопасного значения с сохранением знака.
    """
    if abs(nano) <= _NANO_MAX:
        return nano
    sign = -1 if nano < 0 else 1
    _log.warning(
        "nano out of bounds — clamping",
        extra={"nano": nano, "units": units, "context": context, "clamp_to": sign * _NANO_MAX},
    )
    return sign * _NANO_MAX


def money_to_money_value(m: Any) -> Optional[MoneyValue]:
    """Tinkoff `MoneyValue` (units, nano, currency) → domain MoneyValue.

    Пустые значения (units==0, nano==0, currency пустая) трактуем как None,
    потому что SDK заполняет нулями вместо отсутствия. Денежные операции
    с реальным нулевым значением встречаются (например, нулевая комиссия
    у sandbox-ордера) — для них передаём currency='rub' явно, и они дадут
    MoneyValue(0, 0, 'rub'), не None.

    PR 26 (Phase 3, T5): nano поле bounds-checked, malformed → clamp + warn.
    """
    if m is None:
        return None
    units = getattr(m, "units", 0) or 0
    nano = _clamp_nano(getattr(m, "nano", 0) or 0, units, context="MoneyValue")
    currency = getattr(m, "currency", "") or ""
    if units == 0 and nano == 0 and not currency:
        return None
    return MoneyValue(units=units, nano=nano, currency=currency.lower())


def quotation_to_decimal(q: Any) -> Optional[Decimal]:
    """Tinkoff `Quotation` → Decimal. None если q отсутствует или нулевое.

    PR 26 (Phase 3, T5): nano поле bounds-checked.
    """
    if q is None:
        return None
    units = getattr(q, "units", 0) or 0
    nano = _clamp_nano(getattr(q, "nano", 0) or 0, units, context="Quotation")
    return Quotation(units=units, nano=nano).to_decimal()


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


def _compute_executed_quantity(op: Any) -> int:
    """AU4 / T9: правильный executed quantity для частично исполненных ордеров.

    Tinkoff `quantity` — это ЗАЯВЛЕННОЕ количество в ордере (см. наш
    `docs/TINKOFF_OPERATIONS.md:12-44`). Для лимитных ордеров (особенно
    OTC по выходным) часть заявки может быть НЕ исполнена. Правильный
    executed qty по приоритету:

    1. Σ `trades_info.trades[].quantity` — рекомендуемый способ T-Bank docs.
       `trades_info` — это `OperationTradesData(trades=[OperationTrade(...)])`.
    2. Fallback: `quantity - quantity_rest`.
    3. Fallback: `quantity` (для legacy ops без trades_info).
    """
    trades_info = getattr(op, "trades_info", None)
    if trades_info is not None:
        trades = getattr(trades_info, "trades", None) or []
        if trades:
            executed = sum(int(getattr(t, "quantity", 0) or 0) for t in trades)
            if executed > 0:
                return executed

    qty_declared = int(getattr(op, "quantity", 0) or 0)
    qty_rest = int(getattr(op, "quantity_rest", 0) or 0)
    if qty_rest > 0 and qty_declared > qty_rest:
        return qty_declared - qty_rest

    return qty_declared


def operation_from_proto(op: Any, *, account_id: Optional[str] = None) -> Operation:
    """OperationItem (из get_operations_by_cursor.items) → domain Operation.

    `account_id` обычно есть в самом ответе как `broker_account_id`, но
    иногда отсутствует у legacy/sandbox операций — тогда передаём извне.

    Sanity check (PR 18): Tinkoff иногда отдаёт `quantity`, не соответствующее
    `payment / price`. Пример: buy с qty=30, price=3535 ₽, но payment=-3535 ₽
    (за одну акцию). При этом description ясно: "Покупка 1 акции Озон".
    Если такой mismatch найден — доверяем payment'у и пересчитываем quantity
    через `round(abs(payment) / price)`, потому что payment всегда в правильных
    рублях (от него зависят реальные деньги на счёте).

    AU4 (T9): для частично исполненных заявок используем
    `_compute_executed_quantity` который приоритет отдаёт `trades_info`.
    """
    raw_account = getattr(op, "broker_account_id", "") or account_id or ""

    qty_raw = _compute_executed_quantity(op)
    price_mv = money_to_money_value(getattr(op, "price", None))
    payment_mv = money_to_money_value(getattr(op, "payment", None))
    op_type = parse_operation_type(getattr(op, "type", None))

    inst_type = parse_instrument_type(getattr(op, "instrument_type", None))
    qty_corrected = _reconcile_quantity(
        qty_raw=qty_raw,
        price=price_mv,
        payment=payment_mv,
        op_type=op_type,
        instrument_type=inst_type,
    )

    return Operation(
        operation_id=getattr(op, "id", "") or "",
        parent_operation_id=getattr(op, "parent_operation_id", None) or None,
        account_id=raw_account,
        instrument_uid=(getattr(op, "instrument_uid", None) or None) or None,
        instrument_figi=(getattr(op, "figi", None) or None) or None,
        instrument_type=inst_type,
        operation_type=op_type,
        state=parse_operation_state(getattr(op, "state", None)),
        quantity=qty_corrected,
        price=price_mv,
        payment=payment_mv,
        commission=money_to_money_value(getattr(op, "commission", None)),
        asset_uid_aci=money_to_money_value(getattr(op, "accrued_int", None)),
        executed_at=_ensure_utc(getattr(op, "date", None)),
        description=getattr(op, "description", None) or None,
        trades_id=None,  # trades_info — это список, мы не сохраняем подробности
    )


def _reconcile_quantity(*, qty_raw, price, payment, op_type, instrument_type=None) -> int:
    """
    Защита от грязных данных Tinkoff: если payment и price есть и
    quantity сильно не сходится с (payment/price) — возвращаем реконструкцию
    из payment/price. Применяется только к торговым операциям (buy/sell)
    для акций/облигаций/ETF, где payment в рублях и price в рублях.

    PR 24: для фьючерсов/опционов реконсиляция **выключена**, потому что:
    - price для фьючерса хранится в пунктах (`pt`), не рублях
    - payment для BUY/SELL фьючерса — это гарантийное обеспечение (ГО)
      в рублях, а не цена × qty в пунктах
    Деление `payment_rub / price_pt` даёт бессмысленное число, реконсиляция
    перезаписывает корректный qty мусором.
    """
    from domain.enums import OperationType, InstrumentType

    trade_types = {
        OperationType.BUY,
        OperationType.BUY_CARD,
        OperationType.BUY_MARGIN,
        OperationType.SELL,
        OperationType.SELL_CARD,  # PR 24: было пропущено
        OperationType.SELL_MARGIN,
    }
    if op_type not in trade_types:
        return qty_raw
    # PR 24: блокировка для маржинальных инструментов с pt-ценой.
    if instrument_type in (InstrumentType.FUTURES, InstrumentType.OPTION):
        return qty_raw
    if price is None or payment is None:
        return qty_raw
    try:
        price_d = price.to_decimal()
        payment_d = payment.to_decimal()
    except Exception:
        return qty_raw
    if price_d <= 0 or payment_d == 0:
        return qty_raw
    # quantity, реконструированное из суммы и цены за единицу.
    expected_qty = abs(payment_d) / price_d
    # Допуск: если |expected - raw| / max(raw, expected) > 10% — значит
    # данные не сходятся. Округляем до целого (для акций/фьючерсов qty всегда
    # целое; для дробных future-расширений — поменять на Decimal).
    expected_int = int(round(float(expected_qty)))
    if qty_raw <= 0:
        return expected_int if expected_int > 0 else qty_raw
    deviation = abs(expected_int - qty_raw) / max(qty_raw, expected_int, 1)
    if deviation > 0.1 and expected_int > 0:
        # Doverяем payment'у. quantity_raw, скорее всего, баг Tinkoff API
        # (например: «Покупка 1 акции» приходит как quantity=30).
        return expected_int
    return qty_raw


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
        # T1 fix (AU10 follow-up): SDK schema объявляет
        # `min_price_increment_amount: Quotation` (не MoneyValue!), см.
        # t_tech/invest/schemas.py:1042. Старый код использовал
        # `money_to_decimal` — оно ожидало поле .currency на объекте и
        # возвращало None потому что у Quotation его нет. В результате
        # ВСЕ futures сохранялись с amount=NULL → T1 warning + fallback
        # point_value=1.0 в futures.py → P&L занижен в 100x для SiH6/RTS.
        min_pi_amount = quotation_to_decimal(
            getattr(raw, "min_price_increment_amount", None)
        )
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


# ════════════════════════════════════════════════════════════════════════
# BrokerReport (PR 26 Phase 3 — Three-way reconciliation)
# ════════════════════════════════════════════════════════════════════════


_EXECUTE_SIGN_TO_DIRECTION: dict[str, str] = {
    "Б": "buy",   # «Покупка» в кириллице
    "B": "buy",
    "BUY": "buy",
    "П": "sell",  # «Продажа»
    "S": "sell",
    "SELL": "sell",
}


def _normalize_direction(execute_sign: Optional[str]) -> Optional[str]:
    if not execute_sign:
        return None
    return _EXECUTE_SIGN_TO_DIRECTION.get(execute_sign.strip().upper(), None) or \
           _EXECUTE_SIGN_TO_DIRECTION.get(execute_sign.strip(), None)


def broker_report_trade_from_proto(row: Any) -> BrokerReportTradeRow:
    """Одна запись `BrokerReport` (gRPC) → domain BrokerReportTradeRow.

    Поля по investAPI/operations.proto (BrokerReport message).
    Money fields конвертируются через money_to_decimal (с bounds check, T5).
    """
    execute_sign = getattr(row, "execute_sign", None) or None
    direction = _normalize_direction(execute_sign)

    # Money / Quotation поля
    price = money_to_decimal(getattr(row, "price", None))
    order_amount = money_to_decimal(getattr(row, "order_amount", None))
    total_order_amount = money_to_decimal(getattr(row, "total_order_amount", None))
    aci_value = money_to_decimal(getattr(row, "aci_value", None))
    broker_commission = money_to_decimal(getattr(row, "broker_commission", None))
    exchange_commission = money_to_decimal(getattr(row, "exchange_commission", None))
    exchange_clearing_commission = money_to_decimal(
        getattr(row, "exchange_clearing_commission", None)
    )
    repo_rate = quotation_to_decimal(getattr(row, "repo_rate", None))

    # Currency определяется по price.currency (если есть), иначе по order_amount
    currency = "rub"
    price_proto = getattr(row, "price", None)
    if price_proto is not None:
        cur = getattr(price_proto, "currency", None)
        if cur:
            currency = str(cur).lower()

    return BrokerReportTradeRow(
        trade_id=str(getattr(row, "trade_id", "") or ""),
        order_id=getattr(row, "order_id", None) or None,
        figi=getattr(row, "figi", None) or None,
        ticker=getattr(row, "ticker", None) or None,
        name=getattr(row, "name", None) or None,
        class_code=getattr(row, "class_code", None) or None,
        execute_sign=execute_sign,
        direction=direction,
        exchange=getattr(row, "exchange", None) or None,
        trade_datetime=_ensure_utc(getattr(row, "trade_datetime", None)),
        quantity=int(getattr(row, "quantity", 0) or 0),
        price=price,
        order_amount=order_amount,
        total_order_amount=total_order_amount,
        aci_value=aci_value,
        broker_commission=broker_commission,
        exchange_commission=exchange_commission,
        exchange_clearing_commission=exchange_clearing_commission,
        repo_rate=repo_rate,
        party=getattr(row, "party", None) or None,
        currency=currency,
    )

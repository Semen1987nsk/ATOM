"""
Тесты enum'ов: критичные группировки (trading, commission, varmargin)
используются в FIFO-движке и pnl-калькуляторах. Если кто-то добавит
новый OperationType.BUY_*, он должен попасть в `trading_types()`.
"""

from __future__ import annotations

from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDataSource,
    TradeDirection,
)


def test_operation_type_trading_types_complete() -> None:
    """Все BUY/SELL варианты попадают в trading_types."""
    trading = OperationType.trading_types()
    assert OperationType.BUY in trading
    assert OperationType.SELL in trading
    assert OperationType.BUY_CARD in trading
    assert OperationType.SELL_CARD in trading
    assert OperationType.BUY_MARGIN in trading
    assert OperationType.SELL_MARGIN in trading
    # Не должно быть случайных не-торговых типов.
    assert OperationType.DIVIDEND not in trading
    assert OperationType.COUPON not in trading
    assert OperationType.ACCRUING_VARMARGIN not in trading


def test_operation_type_commission_types() -> None:
    commissions = OperationType.commission_types()
    assert OperationType.BROKER_FEE in commissions
    assert OperationType.SERVICE_FEE in commissions
    assert OperationType.MARGIN_FEE in commissions
    # PR 24: EXCHANGE_FEE убран — этого типа НЕТ в SDK Tinkoff.
    # Биржевая комиссия приходит как BROKER_FEE или SERVICE_FEE.
    assert OperationType.BUY not in commissions


def test_operation_type_varmargin_types() -> None:
    varmargin = OperationType.varmargin_types()
    assert OperationType.ACCRUING_VARMARGIN in varmargin
    assert OperationType.WRITING_OFF_VARMARGIN in varmargin
    assert len(varmargin) == 2  # точно две операции


def test_instrument_type_values() -> None:
    """Значения совпадают с T-Invest API строками (lower-case)."""
    assert InstrumentType.SHARE.value == "share"
    assert InstrumentType.BOND.value == "bond"
    assert InstrumentType.FUTURES.value == "futures"
    assert InstrumentType.OPTION.value == "option"


def test_trade_direction_values() -> None:
    assert TradeDirection.LONG.value == "LONG"
    assert TradeDirection.SHORT.value == "SHORT"


def test_operation_state_executed_is_canonical() -> None:
    """В FIFO matching попадают только EXECUTED операции."""
    assert OperationState.EXECUTED.value == "executed"


def test_trade_data_source_legacy_default() -> None:
    """Старые сделки помечаются 'legacy' (см. миграцию 0003)."""
    assert TradeDataSource.LEGACY.value == "legacy"
    assert TradeDataSource.TINKOFF_V2.value == "tinkoff_v2"
    assert TradeDataSource.MANUAL.value == "manual"

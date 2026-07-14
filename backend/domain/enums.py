"""
Domain enums. Названия и значения соответствуют T-Invest API protobuf-enum'ам,
но без зависимости от protobuf — domain должен оставаться чистым.

Маппинг protobuf↔domain делается в `adapters/tinkoff/proto_to_domain.py`.
"""

from __future__ import annotations

from enum import Enum


class InstrumentType(str, Enum):
    """Типы инструментов из T-Invest API.

    Названия соответствуют `instrument_type` полю в InstrumentResponse:
    https://developer.tbank.ru/invest/intro/useful-info/instruments-mapping
    """

    SHARE = "share"
    BOND = "bond"
    ETF = "etf"
    FUTURES = "futures"
    OPTION = "option"
    CURRENCY = "currency"
    SP = "sp"  # structured product, редкий тип; видим в API, обрабатываем как акцию
    UNSPECIFIED = "unspecified"


class TradeDirection(str, Enum):
    """Направление сделки. LONG = купил, потом продал; SHORT = продал, потом купил."""

    LONG = "LONG"
    SHORT = "SHORT"


class OperationState(str, Enum):
    """Статус операции в T-Invest. Только EXECUTED попадает в FIFO matching."""

    EXECUTED = "executed"
    CANCELED = "canceled"
    PROGRESS = "progress"  # in progress (PROGRESS in proto)
    UNSPECIFIED = "unspecified"


class OperationType(str, Enum):
    """Полный enum типов операций T-Invest API.

    Источники:
    * https://developer.tbank.ru/invest/api/operations-service-get-operations-by-cursor
    * proto: src/docs/contracts/operations.proto

    Сгруппировано по смыслу для удобства чтения.
    """

    UNSPECIFIED = "unspecified"

    # ── Торговля ──
    BUY = "buy"
    SELL = "sell"
    BUY_CARD = "buy_card"
    SELL_CARD = "sell_card"
    BUY_MARGIN = "buy_margin"
    SELL_MARGIN = "sell_margin"

    # ── Дивиденды ──
    DIVIDEND = "dividend"
    DIVIDEND_TRANSFER = "dividend_transfer"
    DIVIDEND_TAX = "dividend_tax"
    DIVIDEND_TAX_PROGRESSIVE = "dividend_tax_progressive"
    DIV_EXT = "div_ext"  # перевод дивиденда

    # ── Облигации ──
    COUPON = "coupon"
    BOND_REPAYMENT = "bond_repayment"
    BOND_REPAYMENT_FULL = "bond_repayment_full"
    BOND_TAX = "bond_tax"
    BOND_TAX_PROGRESSIVE = "bond_tax_progressive"
    TAX_CORRECTION_COUPON = "tax_correction_coupon"

    # ── Фьючерсы (PR 24: SDK enum называется FUTURE_EXPIRATION без S) ──
    ACCRUING_VARMARGIN = "accruing_varmargin"
    WRITING_OFF_VARMARGIN = "writing_off_varmargin"
    FUTURE_EXPIRATION = "future_expiration"
    DELIVERY_BUY = "delivery_buy"
    DELIVERY_SELL = "delivery_sell"

    # ── Опционы ──
    OPTION_EXPIRATION = "option_expiration"

    # ── Комиссии ──
    BROKER_FEE = "broker_fee"
    SERVICE_FEE = "service_fee"
    MARGIN_FEE = "margin_fee"
    TRACK_MFEE = "track_mfee"
    TRACK_PFEE = "track_pfee"
    SUCCESS_FEE = "success_fee"

    # ── Налоги (PR 24: добавлены BENEFIT_TAX + REPO_HOLD/REFUND progressives) ──
    TAX = "tax"
    TAX_PROGRESSIVE = "tax_progressive"
    BENEFIT_TAX = "benefit_tax"
    BENEFIT_TAX_PROGRESSIVE = "benefit_tax_progressive"
    TAX_CORRECTION = "tax_correction"
    TAX_CORRECTION_PROGRESSIVE = "tax_correction_progressive"
    TAX_REPO = "tax_repo"
    TAX_REPO_PROGRESSIVE = "tax_repo_progressive"
    TAX_REPO_HOLD = "tax_repo_hold"
    TAX_REPO_HOLD_PROGRESSIVE = "tax_repo_hold_progressive"
    TAX_REPO_REFUND = "tax_repo_refund"
    TAX_REPO_REFUND_PROGRESSIVE = "tax_repo_refund_progressive"

    # ── Движение средств (PR 24: правильные имена INPUT_/OUTPUT_SECURITIES) ──
    INPUT = "input"
    OUTPUT = "output"
    INPUT_SWIFT = "input_swift"
    OUTPUT_SWIFT = "output_swift"
    INPUT_ACQUIRING = "input_acquiring"
    OUTPUT_ACQUIRING = "output_acquiring"
    INPUT_MULTI = "inp_multi"
    OUT_MULTI = "out_multi"
    INPUT_SECURITIES = "input_securities"
    OUTPUT_SECURITIES = "output_securities"

    # ── Переводы между счетами (IIS↔BS, BS↔BS) ──
    TRANS_IIS_BS = "trans_iis_bs"
    TRANS_BS_BS = "trans_bs_bs"

    # ── REPO / Overnight ──
    OVERNIGHT = "overnight"
    OVER_PLACEMENT = "over_placement"
    OVER_COM = "over_com"
    OVER_INCOME = "over_income"
    CASH_FEE = "cash_fee"
    OUT_FEE = "out_fee"
    OUT_STAMP_DUTY = "out_stamp_duty"
    OUTPUT_PENALTY = "output_penalty"
    ADVICE_FEE = "advice_fee"
    OTHER_FEE = "other_fee"
    OTHER = "other"
    DFA_REDEMPTION = "dfa_redemption"
    PRIMARY_ORDER = "primary_order"

    @classmethod
    def trading_types(cls) -> "frozenset[OperationType]":
        """Операции, которые формируют сделки (попадают в FIFO matching)."""
        return frozenset(
            {
                cls.BUY,
                cls.SELL,
                cls.BUY_CARD,
                cls.SELL_CARD,
                cls.BUY_MARGIN,
                cls.SELL_MARGIN,
            }
        )

    @classmethod
    def commission_types(cls) -> "frozenset[OperationType]":
        # PR 24: убран EXCHANGE_FEE (отсутствует в SDK; биржевая комиссия
        # приходит как BROKER_FEE или SERVICE_FEE).
        return frozenset(
            {
                cls.BROKER_FEE,
                cls.SERVICE_FEE,
                cls.MARGIN_FEE,
                cls.SUCCESS_FEE,
                cls.TRACK_MFEE,
                cls.TRACK_PFEE,
                cls.CASH_FEE,
                cls.OUT_FEE,
                cls.ADVICE_FEE,
            }
        )

    @classmethod
    def varmargin_types(cls) -> "frozenset[OperationType]":
        return frozenset({cls.ACCRUING_VARMARGIN, cls.WRITING_OFF_VARMARGIN})


class TradeDataSource(str, Enum):
    """Источник данных сделки (см. PR 0).

    На уровне БД это `String` (см. миграцию 0003), enum только в Python.
    """

    LEGACY = "legacy"  # старый tinkoff_service, удалён в PR 0
    TINKOFF_V2 = "tinkoff_v2"  # новый sync (PR 5+)
    MANUAL = "manual"  # ручной ввод / Excel-импорт

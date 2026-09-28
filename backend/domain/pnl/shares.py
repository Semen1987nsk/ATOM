"""
PnL для акций (payment-based).

Базовая формула: `pnl = exit_payment + entry_payment`. У BUY-операции
payment отрицательный (деньги ушли со счёта), у SELL — положительный.
Сумма = чистый gross PnL без учёта комиссий.

`net_pnl = pnl - entry_commissions - exit_commission`. У комиссий тоже
отрицательный знак (broker_fee приходит как payment<0), поэтому формально
их можно «прибавлять» к net_pnl. Мы храним `commission_total` отдельно
для отчётности.

Для SHORT-позиции (открыта SELL, закрыта BUY) знаки автоматически
правильные: вход даёт + (деньги пришли), выход — (потратились на выкуп).
Сумма всё равно даёт правильный знак PnL.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from domain.entities import Instrument
from domain.pnl.base import MatchedTrade, PnLCalculator


class SharesPnLCalculator:
    """Реализация PnLCalculator Protocol для акций."""

    def compute(
        self,
        matched: MatchedTrade,
        instrument: Instrument,
        extra_operations: Sequence[object] = (),
    ) -> tuple[Decimal, Decimal]:
        gross = matched.exit.payment_total + matched.entry_payment_total
        # Комиссии у Tinkoff приходят как payment<0 у BROKER_FEE-child-операций,
        # но в op.commission они уже передаются с правильным знаком (-0.05 за
        # сделку). entry_commission_total и exit.commission_total — обычно ≤ 0.
        commissions = matched.entry_commission_total + matched.exit.commission_total
        net = gross + commissions
        return gross, net

    def compute_unrealized(
        self,
        *,
        instrument,
        quantity_signed: int,
        avg_entry_price: Decimal,
        current_price: Decimal,
        extras: dict | None = None,
    ) -> Decimal:
        """
        Базовая формула unrealized PnL: `(current - entry) * qty_signed`.

        Для LONG (qty>0): прибыль когда current > entry.
        Для SHORT (qty<0): прибыль когда current < entry.

        Покрывает 95% случаев для shares/etfs/currencies. Для bonds и
        futures можно переопределить с учётом ACI / варм-маржи —
        но MVP-формула уже даёт корректный знак и порядок величины.
        """
        if quantity_signed == 0:
            return Decimal(0)
        return (current_price - avg_entry_price) * Decimal(quantity_signed)

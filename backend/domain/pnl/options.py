"""
PnL для опционов (PR 10).

Особенности относительно акций:

* `payment` в API уже включает премию × multiplier × qty, то есть body-PnL
  считается как для акций. Нам остаётся только корректно работать со
  знаками: BUY опциона → payment отрицательный (платим премию); SELL →
  положительный (получаем премию).

* `multiplier` — обычно 100 акций × 1 контракт. Хранится в
  `instrument.option_multiplier`, либо вычисляется из `basic_asset_size`.
  В body-PnL уже учтён через payment, отдельно умножать не нужно.

* `OPTION_EXPIRATION` — закрытие позиции принудительно при экспирации.
  Сейчас Tinkoff присылает его как non-trading с payment, отражающим
  intrinsic value (ITM) или 0 (OTM). Если позиция была открыта, и в окне
  пришёл `OPTION_EXPIRATION` по тому же инструменту, мы добавляем его
  payment к net_pnl как «реализованный результат экспирации».

* Греки (delta/gamma/...) — в Tinkoff API не предоставляются, считать
  ничего не нужно.

ОГРАНИЧЕНИЕ: если опцион ATM/ITM и Tinkoff списывает базовый актив (один
из вариантов settlement), это придёт как SECURITY_IN/SECURITY_OUT по
базовому активу. Это уже отдельные позиции — обрабатывает FIFO движок
обычным образом для базового актива.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from domain.entities import Instrument, Operation
from domain.enums import OperationType
from domain.pnl.base import MatchedTrade, PnLCalculator
from domain.pnl.shares import SharesPnLCalculator


_OPTION_SETTLEMENT_TYPES = frozenset({OperationType.OPTION_EXPIRATION})


class OptionsPnLCalculator(SharesPnLCalculator):
    """
    Реализация для опционов. Наследует базовый `compute_unrealized` от
    SharesPnLCalculator (premium-based).
    """

    def compute(
        self,
        matched: MatchedTrade,
        instrument: Instrument,
        extra_operations: Sequence[Operation] = (),
    ) -> tuple[Decimal, Decimal]:
        gross = matched.exit.payment_total + matched.entry_payment_total
        commissions = (
            matched.entry_commission_total + matched.exit.commission_total
        )

        # Если в окне есть OPTION_EXPIRATION по этому же uid — это
        # доп-доход/убыток от settlement'а.
        settlement = Decimal(0)
        for op in extra_operations:
            if op.operation_type not in _OPTION_SETTLEMENT_TYPES:
                continue
            if op.instrument_uid != matched.instrument_uid:
                continue
            if op.payment is None:
                continue
            settlement += op.payment.to_decimal()

        net = gross + commissions + settlement
        return gross, net

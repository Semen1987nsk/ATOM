"""
PnL для облигаций (PR 8).

Источник истины — официальная T-Bank doc:
https://developer.tbank.ru/invest/intro/useful-info/points

Особенности:

* В Tinkoff API `op.payment` для BUY/SELL облигации уже включает в себя
  и тело бонда (price × nominal × qty / 100), и НКД (ACI × qty), и
  комиссия отдельно. Поэтому body-PnL считается так же как для акций:
  `gross = exit_payment + entry_payment`.

* Купоны (`OPERATION_TYPE_COUPON`) и купонные налоги
  (`OPERATION_TYPE_BOND_TAX`, `OPERATION_TYPE_BOND_TAX_PROGRESSIVE`,
  `OPERATION_TYPE_TAX_COUPON` — если когда-то появится) — это РЕАЛИЗОВАННЫЕ
  во время удержания денежные потоки. Их добавляем к `net_pnl`.

* Амортизация (`OPERATION_TYPE_PARTIAL_BOND_REPAYMENT`) — часть номинала
  возвращена досрочно. Деньги пришли пользователю в этом окне → добавляем
  к net_pnl.

* Полное погашение (`OPERATION_TYPE_BOND_REPAYMENT` / `_FULL`) — позиция
  закрывается принудительно. В FIFO это будет отдельный SELL-эквивалент
  (если когда-нибудь Tinkoff начнёт его слать как trading op). Сейчас
  такие операции идут как non-trading, и их payment'ы попадают в net_pnl
  как «доход в окне».

Filter: учитываем только операции по ТОМУ ЖЕ instrument_uid.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from domain.entities import Instrument, Operation
from domain.enums import OperationType
from domain.pnl.base import MatchedTrade, PnLCalculator
from domain.pnl.shares import SharesPnLCalculator


_INCOME_TYPES = frozenset({
    OperationType.COUPON,
    OperationType.PARTIAL_BOND_REPAYMENT,
    OperationType.BOND_REPAYMENT,
    OperationType.BOND_REPAYMENT_FULL,
})

_TAX_TYPES = frozenset({
    OperationType.BOND_TAX,
    OperationType.BOND_TAX_PROGRESSIVE,
})


class BondsPnLCalculator(SharesPnLCalculator):
    """
    Реализация для облигаций. Наследует базовый `compute_unrealized` от
    SharesPnLCalculator (body-based). В будущем можно переопределить с
    учётом current_aci и remaining_nominal.
    """

    def compute(
        self,
        matched: MatchedTrade,
        instrument: Instrument,
        extra_operations: Sequence[Operation] = (),
    ) -> tuple[Decimal, Decimal]:
        # 1. Body PnL — как для акций.
        gross = matched.exit.payment_total + matched.entry_payment_total
        commissions = (
            matched.entry_commission_total + matched.exit.commission_total
        )

        # 2. Купоны и амортизация в окне трейда → realized income.
        income = Decimal(0)
        taxes = Decimal(0)
        for op in extra_operations:
            if op.instrument_uid != matched.instrument_uid:
                continue
            if op.payment is None:
                continue
            payment = op.payment.to_decimal()
            if op.operation_type in _INCOME_TYPES:
                income += payment
            elif op.operation_type in _TAX_TYPES:
                # Tinkoff отдаёт payment налога как отрицательный.
                taxes += payment

        net = gross + commissions + income + taxes
        return gross, net

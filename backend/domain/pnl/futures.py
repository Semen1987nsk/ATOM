"""
PnL для фьючерсов (PR 9).

Источник истины — официальная T-Bank doc:
https://developer.tbank.ru/invest/intro/useful-info/points

Особенность фьючерсов: реальный финансовый результат состоит из ДВУХ
компонент, не одной:

1. **Body PnL** — разница цен * качество вход/выход. На неё работает
   payment-based формула: `body = exit_payment + entry_payment`.
   У Tinkoff API BUY-фьючерса payment близок к 0 (списывается только
   гарантийное обеспечение), но не всегда — есть начальная маржа.

2. **Variation margin** — ежедневное переоценочное начисление/списание
   между клирингом дня. У Tinkoff приходит как отдельные операции:
   `ACCRUING_VARMARGIN` (положительная, payment > 0) и
   `WRITING_OFF_VARMARGIN` (отрицательная, payment < 0).

ВАЖНО: варм-маржа в API **не привязана к instrument_uid операции**:
`OperationItem.instrument_uid` у варм-маржи обычно null, потому что она
агрегирована по аккаунту. Однако Tinkoff в большинстве случаев ставит
attached `figi` или `position_uid` фьючерса, а иногда вообще ничего.

В payment-формуле мы суммируем все варм-маржевые операции в окне
`[entry_at; exit_at]` ПО ТОМУ ЖЕ instrument_uid если он есть, а иначе
без фильтра по инструменту (это даст ошибку перепутывания между разными
фьючерсами — но это лучше чем потерять варм-маржу вообще). PR 11 будет
делать point-value-based fallback для open positions.

ОГРАНИЧЕНИЯ ТЕКУЩЕЙ РЕАЛИЗАЦИИ:

* Если у пользователя одновременно открыты позиции по нескольким
  фьючерсам, варм-маржа per-instrument из API доступна по `figi` —
  мы фильтруем по нему.
* Если ни figi ни instrument_uid у варм-маржевой операции не указаны,
  она считается «общей по аккаунту» и в текущей реализации НЕ попадает
  в PnL конкретного трейда (чтобы не приписать её всем подряд). Это
  правильное consvtv по умолчанию: лучше показать body-PnL чем неверный
  «полный» PnL.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from domain.entities import Instrument, Operation
from domain.enums import OperationType
from domain.pnl.base import MatchedTrade, PnLCalculator
from domain.pnl.shares import SharesPnLCalculator


_VARMARGIN_TYPES = frozenset({
    OperationType.ACCRUING_VARMARGIN,
    OperationType.WRITING_OFF_VARMARGIN,
})


class FuturesPnLCalculator(SharesPnLCalculator):
    """
    Реализация для фьючерсов. Наследует базовый `compute_unrealized` от
    SharesPnLCalculator (body-based). Полная формула с
    `min_price_increment_amount` — улучшение для отдельного PR.
    """

    def compute(
        self,
        matched: MatchedTrade,
        instrument: Instrument,
        extra_operations: Sequence[Operation] = (),
    ) -> tuple[Decimal, Decimal]:
        # 1. Body — как у акций. Часто 0 (фьючерсы маржируются).
        body = matched.exit.payment_total + matched.entry_payment_total
        commissions = (
            matched.entry_commission_total + matched.exit.commission_total
        )

        # 2. Варм-маржа в окне трейда. Tinkoff может присылать её с
        # instrument_uid либо с figi. Берём те, что относятся к нашему
        # инструменту. Если ни то ни другое не задано — пропускаем
        # (см. docstring модуля).
        target_uid = matched.instrument_uid
        target_figi = instrument.figi

        varmargin = Decimal(0)
        for op in extra_operations:
            if op.operation_type not in _VARMARGIN_TYPES:
                continue
            if op.payment is None:
                continue
            # Match по uid либо figi.
            if op.instrument_uid:
                if op.instrument_uid != target_uid:
                    continue
            elif op.instrument_figi:
                if op.instrument_figi != target_figi:
                    continue
            else:
                # без идентификатора инструмента не приписываем
                continue
            varmargin += op.payment.to_decimal()

        # gross = только body (для прозрачности; UI может показывать
        # «движение цены» отдельно от варм-маржи).
        gross = body
        net = body + commissions + varmargin
        return gross, net

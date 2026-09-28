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
from domain.enums import OperationType, TradeDirection
from domain.pnl.base import MatchedTrade, PnLCalculator
from domain.pnl.shares import SharesPnLCalculator
from logger import get_logger

_log = get_logger("futures.pnl")


_VARMARGIN_TYPES = frozenset({
    OperationType.ACCRUING_VARMARGIN,
    OperationType.WRITING_OFF_VARMARGIN,
})


def _point_value(instrument: Instrument) -> Decimal:
    """Стоимость одного пункта цены фьючерса в РУБЛЯХ.

    Формула из T-Bank docs:
        point_value = min_price_increment_amount / min_price_increment

    Например для GAZRBF: шаг = 1 пункт = 1 ₽ → point_value = 1.
    Для SiH6 (USDRUB-фьючерс): шаг = 1 пункт, стоимость шага ≈ 100 ₽ →
    point_value = 100.

    PR 26 (Phase 3, T1 fix): раньше fallback был silent 1.0, что для
    SiH6/RTS/Si приводило к занижению P&L в 100x. Теперь log warning
    структурированно (поднимется в Sentry breadcrumb и обнаружится
    transformation_audit в reconciliation). Fallback всё ещё 1.0,
    чтобы не ломать legacy данные — но обнаруживаем громко.
    """
    step = instrument.min_price_increment
    step_amount = instrument.min_price_increment_amount
    if step is None or step == 0 or step_amount is None:
        _log.warning(
            "futures_point_value_fallback",
            extra={
                "transformation_warning": True,
                "kind": "T1_futures_point_value",
                "instrument_uid": instrument.uid,
                "ticker": instrument.ticker,
                "figi": instrument.figi,
                "has_step": step is not None and step != 0,
                "has_step_amount": step_amount is not None,
                "impact": "pnl_scale_may_be_100x_off",
            },
        )
        return Decimal("1")
    try:
        return Decimal(step_amount) / Decimal(step)
    except Exception as exc:
        _log.warning(
            "futures_point_value_compute_error",
            extra={
                "transformation_warning": True,
                "kind": "T1_futures_point_value",
                "instrument_uid": instrument.uid,
                "error": str(exc),
            },
        )
        return Decimal("1")


class FuturesPnLCalculator(SharesPnLCalculator):
    """
    Реализация для фьючерсов.

    PR 24: компьютер unrealized_pnl теперь использует `point_value`
    (`min_price_increment_amount / min_price_increment`) — раньше формула
    была наследована от Shares и давала результат В ПУНКТАХ, а не рублях.
    Это приводило к ошибке масштаба до 100x для контрактов вроде SiH6.
    """

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
        Unrealized PnL фьючерса в РУБЛЯХ:

            (current_price - avg_entry_price) * qty_signed * point_value

        Где цены в ПУНКТАХ (Tinkoff API), point_value переводит в ₽.
        """
        if quantity_signed == 0:
            return Decimal(0)
        pv = _point_value(instrument)
        delta_pt = current_price - avg_entry_price
        return delta_pt * Decimal(quantity_signed) * pv

    def compute(
        self,
        matched: MatchedTrade,
        instrument: Instrument,
        extra_operations: Sequence[Operation] = (),
    ) -> tuple[Decimal, Decimal]:
        """Phase 8 (2026-05-17): body = (exit_price − entry_avg_price) × qty × pv × sign.

        2026-05-19: pv resolution теперь mirror `_compute_point_value_snapshot`
        в FifoMatcher — prefer empirical pv когда cached drifts > 5%. Cached
        pv (min_pi_amt / min_pi) от Tinkoff metadata неправильное для **индексных
        фьючерсов** (DAX, Brent BBZ4, foreign futures), где Tinkoff пишет
        `min_pi_amt=1000` как metadata, но реальный payment не использует этот
        множитель. Это приводило к 1000x завышению body для таких контрактов.
        Empirical pv = |payment|/(qty×price) — truth от реальных Tinkoff payments.

        Прямой расчёт body P&L из цен сделки + point_value инструмента.
        Это математически тождественно сумме всех variation margin
        операций от entry до exit_at + последующего post-clearing
        settlement (MOEX telescoping sum: Σ (clearing_today − clearing_yesterday)
        × qty × pv = (exit − entry) × qty × pv).

        ПОЧЕМУ НЕ payment-based (как до Phase 6):
          Tinkoff API отправляет BUY/SELL payment для futures как
          full notional (qty × price × pv). Это offset margin record'ом,
          которого нет в OperationORM. Использование payments в body
          приводит к double-count с varmargin attribution.

        ПОЧЕМУ НЕ body=0 (как в Phase 6):
          orphan varmargin от MOEX post-clearing settlements (приходящих
          ПОСЛЕ exit_at) падал в account_level_adjustments вместо
          конкретного trade. Журнал терял per-trade точность.

        После Phase 8:
        - Trade.pnl = реальный body P&L каждой closed futures сделки
        - varmargin_attributed для closed trades = 0 (fee_attribution skip)
        - Trade.net_pnl = body − |commission| + margin_fee + service_fee
                          + other_fees_attributed
        - Каждая closed сделка self-contained в Journal ✓

        Verification (tools/verify_futures_body.py): Σ VARMARGIN ops в
        окне [entry_at, exit_at + 4h] per-instrument ≈ body (<5% diff).
        """
        pv = self._resolve_pv(matched, instrument)
        qty = Decimal(matched.quantity)
        entry_avg = matched.entry_avg_price
        exit_px = matched.exit.price_per_unit
        sign = Decimal(1) if matched.direction == TradeDirection.LONG else Decimal(-1)
        body = (exit_px - entry_avg) * qty * pv * sign
        commissions = (
            matched.entry_commission_total + matched.exit.commission_total
        )
        gross = body
        # net = body + commissions (signed; commission negative для outgoing)
        # varmargin для closed trades НЕ добавляется — она уже в body
        # (см. fee_attribution.py Phase 8.2 skip для closed).
        net = body + commissions
        return gross, net

    @staticmethod
    def _resolve_pv(matched: MatchedTrade, instrument: Instrument) -> Decimal:
        """Resolve point_value preferring empirical when cached drifts > 5%.

        Mirrors `FifoMatcher._compute_point_value_snapshot` (Phase 9) — для
        индексных фьючерсов cached pv (min_pi_amt / min_pi) ошибочно завышено
        от Tinkoff metadata. Empirical pv = |entry payment per unit| / price —
        truth от наблюдаемых transactions.
        """
        cached_pv = _point_value(instrument)
        # MATH-11: weighted-avg PV по всем entry_slices (а не first-slice).
        # Scaled-in трейды (несколько входов разного размера) делают
        # first-slice репрезентативно слабым: 1 lot @ price1 → pv1, потом
        # 9 lots @ price2 → pv2. Раньше брали только pv1, теперь — взвешенно
        # по matched_qty: Σ (pv_i × qty_i) / Σ qty_i. Для одного slice'а
        # результат идентичен старой формуле.
        empirical_pv: Decimal | None = None
        if matched.entry_slices:
            total_pv_weighted = Decimal(0)
            total_qty = Decimal(0)
            for slc in matched.entry_slices:
                price = slc.lot.price_per_unit
                qty = Decimal(slc.matched_qty)
                if price > 0 and qty > 0:
                    pay_per_unit = abs(slc.lot.payment_per_unit)
                    slice_pv = pay_per_unit / price
                    total_pv_weighted += slice_pv * qty
                    total_qty += qty
            if total_qty > 0:
                empirical_pv = total_pv_weighted / total_qty
        if empirical_pv is None:
            return cached_pv
        if cached_pv == 0:
            return empirical_pv
        drift = abs(empirical_pv - cached_pv) / cached_pv
        if drift > Decimal("0.05"):
            _log.warning(
                "futures_pv_empirical_chosen",
                extra={
                    "instrument_uid": instrument.uid,
                    "ticker": instrument.ticker,
                    "cached_pv": str(cached_pv),
                    "empirical_pv": str(empirical_pv),
                    "drift_pct": str(drift * 100),
                },
            )
            return empirical_pv
        return cached_pv

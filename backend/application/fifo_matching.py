"""
FIFOMatchingService — универсальный FIFO-движок для всех типов инструментов.

Алгоритм:

1. Берём операции по одному инструменту, отсортированные по `executed_at`.
2. Поддерживаем очередь открытых лотов с пометкой LONG/SHORT.
3. Если новая операция в том же направлении что текущие лоты — добавляем
   новый лот в хвост.
4. Если в обратном — потребляем лоты с головы, формируем `MatchedTrade`.
   При полном «развороте» (закрыли всё + остаток) — flip: открываем новые
   лоты противоположного направления.
5. Per-instrument формула PnL вызывается через реестр `PnLCalculator`.

Замечания:

* INPUT_SECURITIES / OUTPUT_SECURITIES и прочие корп-действия в FIFO
  **не идут** — они корректируют позицию напрямую (отдельная стадия,
  PR 8+ при необходимости).
* DIVIDEND / COUPON / VARMARGIN — не торговые, не порождают Trade, но
  передаются в PnLCalculator через `extra_operations` для коррекции net_pnl
  (PR 8/9).
* OPTION_EXPIRATION закрывает позицию принудительно — особая логика в PR 10.

Контракт: `match(...)` — pure-функция, без БД и сети. Загрузка существующих
лотов и сохранение результатов — забота вызывающего кода (pipeline в PR 5).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

from domain.entities import Instrument, Operation, Trade
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
    TradeDirection,
)
from domain.pnl.base import (
    ExitFill,
    FifoLot,
    FillSlice,
    MatchedTrade,
    PnLCalculator,
)
from domain.pnl.bonds import BondsPnLCalculator
from domain.pnl.currencies import CurrenciesPnLCalculator
from domain.pnl.etfs import EtfsPnLCalculator
from domain.pnl.fallback import FallbackPnLCalculator
from domain.pnl.futures import FuturesPnLCalculator
from domain.pnl.options import OptionsPnLCalculator
from domain.pnl.shares import SharesPnLCalculator
from logger import get_logger

log = get_logger("fifo_matching")


# Дефолтный реестр калькуляторов. PR 8 (bonds), PR 9 (futures), PR 10 (options).
DEFAULT_CALCULATORS: dict[InstrumentType, PnLCalculator] = {
    InstrumentType.SHARE: SharesPnLCalculator(),
    InstrumentType.ETF: EtfsPnLCalculator(),
    InstrumentType.CURRENCY: CurrenciesPnLCalculator(),
    InstrumentType.BOND: BondsPnLCalculator(),
    InstrumentType.FUTURES: FuturesPnLCalculator(),
    InstrumentType.OPTION: OptionsPnLCalculator(),
    InstrumentType.SP: FallbackPnLCalculator(),
}


# ── helpers ─────────────────────────────────────────────────────────


_BUY_TYPES = {OperationType.BUY, OperationType.BUY_CARD, OperationType.BUY_MARGIN}
_SELL_TYPES = {OperationType.SELL, OperationType.SELL_CARD, OperationType.SELL_MARGIN}

# AU11: OPTION_EXPIRATION закрывает открытую позицию принудительно — раньше
# она проходила мимо FIFO движка и open lot оставался в queue навсегда.
# Trade settlement = (entry_value - 0) для OTM или
#                   (entry_value - settlement_payment) для ITM.
# settlement_payment учитывается отдельно в OptionsPnLCalculator через
# extra_operations (см. domain/pnl/options.py). Здесь FIFO просто закрывает
# lot по price=0 и помечает Trade.
_FORCED_CLOSE_TYPES = {OperationType.OPTION_EXPIRATION}


def _as_decimal(money: Optional["object"]) -> Decimal:
    """MoneyValue.to_decimal() с graceful fallback на 0."""
    if money is None:
        return Decimal(0)
    return money.to_decimal()  # type: ignore[attr-defined]


def _per_unit_from_total(money: Optional["object"], qty: int) -> Decimal:
    """Total → per-unit. Используется для payment и commission в Tinkoff API."""
    if money is None or qty == 0:
        return Decimal(0)
    return money.to_decimal() / Decimal(qty)  # type: ignore[attr-defined]


@dataclass
class MatchResult:
    """Результат матчинга одного инструмента."""

    closed_trades: list[Trade] = field(default_factory=list)
    open_lots: list[FifoLot] = field(default_factory=list)
    # Сумма дельт от не-торговых операций (купоны, варм-маржа) — пока 0,
    # PR 8/9 будут начислять.
    realized_extras: Decimal = Decimal(0)


class _PositionIdCounter:
    """TR1: счётчик position_id внутри одного FIFO-runа.

    Увеличивается на 1 каждый раз когда позиция транзитит из quantity=0 в
    non-zero (включая flip long→short после полного close).

    Per (account_id, instrument_uid) счётчик. Один FIFO `match()` call работает
    с одним instrument, поэтому здесь — простой incrementing integer.
    """

    def __init__(self) -> None:
        self._counter = 0

    def next(self) -> int:
        self._counter += 1
        return self._counter


# ── основной движок ────────────────────────────────────────────────


class FIFOMatchingService:
    def __init__(
        self,
        *,
        calculators: Optional[dict[InstrumentType, PnLCalculator]] = None,
    ) -> None:
        self._calcs = calculators or DEFAULT_CALCULATORS

    def match(
        self,
        *,
        account_id: int,
        instrument: Instrument,
        operations: Sequence[Operation],
        existing_open_lots: Sequence[FifoLot] = (),
    ) -> MatchResult:
        """
        Пройтись по `operations` и `existing_open_lots`, вернуть закрытые
        Trade'ы и остаток открытых лотов.

        `account_id` — наш внутренний (FK на accounts.id). Идёт в Trade.account_id.
        """
        result = MatchResult(open_lots=list(existing_open_lots))
        queue: deque[FifoLot] = deque(result.open_lots)
        # TR1: position_id counter — round-trip group ID, инкрементится при
        # каждой транзиции quantity=0 → non-zero. Все trades/lots одного
        # lifecycle разделяют counter value.
        pos_counter = _PositionIdCounter()
        # Если переданы existing_open_lots с уже назначенными position_id —
        # стартуем счётчик с max, чтобы новые transition не коллидили.
        for lot in existing_open_lots:
            if lot.position_id is not None and lot.position_id > pos_counter._counter:
                pos_counter._counter = lot.position_id

        # Хронологический порядок — обязателен.
        sorted_ops = sorted(operations, key=lambda o: o.executed_at)
        # AU11: OPTION_EXPIRATION тоже идёт через FIFO как forced-close.
        _CLOSING_TYPES = _BUY_TYPES | _SELL_TYPES | _FORCED_CLOSE_TYPES
        trading_ops = [
            op
            for op in sorted_ops
            if op.state == OperationState.EXECUTED
            and op.operation_type in _CLOSING_TYPES
        ]
        # PR 8/9 используют non_trading ops в формулах (купоны, варм-маржа).
        # Передаём ВСЕ операции по инструменту в calculator — он сам
        # отфильтрует по типу и временному окну.
        non_trading_ops = tuple(
            op
            for op in sorted_ops
            if op.state == OperationState.EXECUTED
            and op.operation_type not in _CLOSING_TYPES
        )

        calculator = self._calcs.get(
            instrument.instrument_type, FallbackPnLCalculator()
        )

        for op in trading_ops:
            self._process_one_op(
                op=op,
                queue=queue,
                instrument=instrument,
                account_id=account_id,
                calculator=calculator,
                result=result,
                non_trading_ops=non_trading_ops,
                pos_counter=pos_counter,
            )

        result.open_lots = list(queue)
        return result

    # ── per-operation ───────────────────────────────────────────────

    def _process_one_op(
        self,
        *,
        op: Operation,
        queue: deque,
        instrument: Instrument,
        account_id: int,
        calculator: PnLCalculator,
        result: MatchResult,
        non_trading_ops: tuple[Operation, ...] = (),
        pos_counter: Optional[_PositionIdCounter] = None,
    ) -> None:
        # AU11: OPTION_EXPIRATION — forced close открытых лотов по этому
        # инструменту. Tinkoff присылает payment отдельно (через settlement);
        # FIFO просто закрывает quantity по price=0, а Settlement учитывается
        # в OptionsPnLCalculator.compute() через extra_operations.
        if op.operation_type in _FORCED_CLOSE_TYPES:
            self._process_forced_close(
                op=op,
                queue=queue,
                instrument=instrument,
                account_id=account_id,
                calculator=calculator,
                result=result,
                non_trading_ops=non_trading_ops,
            )
            return

        op_direction = (
            TradeDirection.LONG if op.operation_type in _BUY_TYPES else TradeDirection.SHORT
        )
        op_qty = op.quantity or 0
        if op_qty <= 0:
            return

        # Если очередь пуста или одного направления с op — это open/расширение.
        if not queue or queue[0].direction == op_direction:
            # TR1: position_id логика.
            # - queue пуста (0 → non-zero) → новый position_id
            # - queue с тем же направлением (scale-in) → reuse position_id
            if not queue:
                pid = pos_counter.next() if pos_counter is not None else None
            else:
                pid = queue[0].position_id
            queue.append(self._make_lot(op, direction=op_direction, position_id=pid))
            return

        # Иначе — closing: потребляем встречные лоты с головы.
        remaining_to_close = op_qty
        used_slices: list[FillSlice] = []
        while remaining_to_close > 0 and queue and queue[0].direction != op_direction:
            head = queue[0]
            take = min(head.quantity_remaining, remaining_to_close)
            used_slices.append(FillSlice(lot=head, matched_qty=take))
            if take == head.quantity_remaining:
                queue.popleft()
            else:
                queue[0] = head.consume(take)
            remaining_to_close -= take

        # Сформировать MatchedTrade и Trade-запись.
        if used_slices:
            matched = MatchedTrade(
                # Направление сделки — это направление открытия (=head'а
                # очереди до закрытия).
                direction=used_slices[0].lot.direction,
                entry_slices=tuple(used_slices),
                exit=self._make_exit_fill(op, qty=op_qty - remaining_to_close),
                instrument_uid=instrument.uid,
                currency=op.payment.currency if op.payment else "rub",
            )
            trade = self._build_trade(
                matched=matched,
                instrument=instrument,
                account_id=account_id,
                exit_at=op.executed_at,
                exit_operation_id=op.operation_id,
                calculator=calculator,
                non_trading_ops=non_trading_ops,
            )
            result.closed_trades.append(trade)

        # Если позиция полностью закрыта и осталось ещё что-то от op —
        # это flip: открываем новый лот в направлении op.
        if remaining_to_close > 0:
            # TR1: flip = новый position lifecycle → новый position_id.
            flip_pid = pos_counter.next() if pos_counter is not None else None
            flip_lot = self._make_lot(op, direction=op_direction, position_id=flip_pid)
            # quantity_remaining=remaining (мы уже закрыли часть встречной).
            # Создаём «частичный» лот: original = remaining_to_close (новый).
            queue.append(
                FifoLot(
                    operation_id=flip_lot.operation_id,
                    direction=flip_lot.direction,
                    quantity_remaining=remaining_to_close,
                    quantity_original=remaining_to_close,
                    price_per_unit=flip_lot.price_per_unit,
                    payment_per_unit=flip_lot.payment_per_unit,
                    commission_per_unit=flip_lot.commission_per_unit,
                    executed_at=flip_lot.executed_at,
                    currency=flip_lot.currency,
                    position_id=flip_pid,
                )
            )

    # ── factory методы ──────────────────────────────────────────────

    def _process_forced_close(
        self,
        *,
        op: Operation,
        queue: deque,
        instrument: Instrument,
        account_id: int,
        calculator: PnLCalculator,
        result: MatchResult,
        non_trading_ops: tuple[Operation, ...] = (),
    ) -> None:
        """AU11: закрывает все совпадающие open lots при OPTION_EXPIRATION.

        Закрытие идёт по price=0 (для OTM-опционов) / per-unit-payment=0.
        Settlement (intrinsic value для ITM) учитывается в
        `OptionsPnLCalculator` через `extra_operations` — мы передаём
        `OPTION_EXPIRATION` operation в non_trading_ops для следующих
        matched trades, и calculator добавит её payment к net_pnl.

        Если open lots нет — ничего не делаем (это означает что мы получили
        OPTION_EXPIRATION без предыдущего open position, что странно, но
        не должно ломать pipeline).
        """
        if not queue:
            return

        # Закрываем все встречные lots (для опционов FIFO обычно one-instrument)
        total_qty = sum(lot.quantity_remaining for lot in queue)
        if total_qty <= 0:
            return

        used_slices: list[FillSlice] = []
        while queue:
            head = queue[0]
            used_slices.append(FillSlice(lot=head, matched_qty=head.quantity_remaining))
            queue.popleft()

        # Создаём synthetic exit fill: price=0 (опцион expired), payment=0.
        # Реальный intrinsic value придёт через extra_operations (OPTION_EXPIRATION
        # сам присутствует в non_trading_ops для OptionsPnLCalculator).
        from domain.value_objects import MoneyValue
        currency = op.payment.currency if op.payment else "rub"
        exit_fill = ExitFill(
            operation_id=op.operation_id,
            quantity=total_qty,
            price_per_unit=Decimal(0),
            payment_per_unit=Decimal(0),
            commission_per_unit=Decimal(0),
            executed_at=op.executed_at,
            currency=currency,
        )
        matched = MatchedTrade(
            direction=used_slices[0].lot.direction,
            entry_slices=tuple(used_slices),
            exit=exit_fill,
            instrument_uid=instrument.uid,
            currency=currency,
        )
        # Передаём OPTION_EXPIRATION в non_trading_ops чтобы OptionsPnLCalculator
        # увидел его и добавил settlement payment в net_pnl.
        non_trading_with_op = non_trading_ops + (op,)
        trade = self._build_trade(
            matched=matched,
            instrument=instrument,
            account_id=account_id,
            exit_at=op.executed_at,
            exit_operation_id=op.operation_id,
            calculator=calculator,
            non_trading_ops=non_trading_with_op,
        )
        result.closed_trades.append(trade)
        log.info(
            "fifo.option_expiration_forced_close",
            extra={
                "instrument_uid": instrument.uid,
                "qty_closed": total_qty,
                "settlement_payment": str(op.payment.to_decimal()) if op.payment else "0",
            },
        )

    @staticmethod
    def _make_lot(
        op: Operation,
        *,
        direction: TradeDirection,
        position_id: Optional[int] = None,
    ) -> FifoLot:
        qty = op.quantity or 0
        # В Tinkoff API:
        # * `price` — цена за единицу (1 акция / 1 контракт / 1 единица валюты);
        # * `payment` — суммарная сумма за всю операцию;
        # * `commission` — суммарная комиссия за всю операцию.
        price = _as_decimal(op.price)
        payment_per_unit = _per_unit_from_total(op.payment, qty)
        commission_per_unit = _per_unit_from_total(op.commission, qty)
        currency = op.payment.currency if op.payment else "rub"
        return FifoLot(
            operation_id=op.operation_id,
            direction=direction,
            quantity_remaining=qty,
            quantity_original=qty,
            price_per_unit=price,
            payment_per_unit=payment_per_unit,
            commission_per_unit=commission_per_unit,
            executed_at=op.executed_at,
            currency=currency,
            position_id=position_id,
        )

    @staticmethod
    def _make_exit_fill(op: Operation, *, qty: int) -> ExitFill:
        qty_full = op.quantity or 0
        price = _as_decimal(op.price)
        payment_per_unit = _per_unit_from_total(op.payment, qty_full)
        commission_per_unit = _per_unit_from_total(op.commission, qty_full)
        currency = op.payment.currency if op.payment else "rub"
        return ExitFill(
            operation_id=op.operation_id,
            quantity=qty,
            price_per_unit=price,
            payment_per_unit=payment_per_unit,
            commission_per_unit=commission_per_unit,
            executed_at=op.executed_at,
            currency=currency,
        )

    @staticmethod
    def open_trades_from_lots(
        *,
        lots: Sequence[FifoLot],
        instrument: Instrument,
        account_id: int,
    ) -> list[Trade]:
        """T7 fix: построить open Trade записи из несматченных FIFO лотов.

        Раньше open_lots жили только в-памяти `MatchResult` и не попадали в
        Trade table — UI "Open positions" был пустым для futures. После
        этого fix:
          - каждый open lot → Trade с `exit_at=None`, `exit_price=None`
          - quantity_remaining (не original) — реально открытое кол-во
          - net_pnl/pnl = None (unrealized считается отдельно через mark-to-market)
          - entry_value = price × quantity_remaining (для процент-метрик)

        UPSERT-стратегия `replace_for_instrument` корректно обрабатывает
        смесь closed + open trades.
        """
        open_trades: list[Trade] = []
        for lot in lots:
            if lot.quantity_remaining <= 0:
                continue
            entry_value = abs(lot.payment_per_unit) * Decimal(lot.quantity_remaining)
            commission_total = abs(lot.commission_per_unit) * Decimal(lot.quantity_remaining)
            open_trades.append(
                Trade(
                    account_id=str(account_id),
                    instrument_uid=instrument.uid,
                    instrument_figi=instrument.figi,
                    instrument_type=instrument.instrument_type,
                    direction=lot.direction,
                    quantity=lot.quantity_remaining,
                    entry_price=lot.price_per_unit,
                    exit_price=None,
                    entry_at=lot.executed_at,
                    exit_at=None,
                    pnl=None,
                    net_pnl=None,
                    commission_total=commission_total,
                    entry_value=entry_value,
                    exit_value=None,
                    tax_total=Decimal(0),
                    currency=lot.currency,
                    entry_operation_ids=(lot.operation_id,),
                    exit_operation_ids=(),
                    position_id=lot.position_id,
                )
            )
        return open_trades

    def _build_trade(
        self,
        *,
        matched: MatchedTrade,
        instrument: Instrument,
        account_id: int,
        exit_at: datetime,
        exit_operation_id: str,
        calculator: PnLCalculator,
        non_trading_ops: tuple[Operation, ...] = (),
    ) -> Trade:
        # Окно для extras: от первой entry до exit. Calculator сам
        # отфильтрует по типу (купоны/варм-маржа/налоги).
        entry_at = matched.entry_at
        relevant_extras = tuple(
            o
            for o in non_trading_ops
            if entry_at <= o.executed_at <= exit_at
        )
        gross_pnl, net_pnl = calculator.compute(
            matched, instrument, extra_operations=relevant_extras
        )
        # Phase 9 (2026-05-17): для futures сохраняем point_value snapshot.
        # Сначала пробуем empirical = |payment|/(qty×price) (truth для expired
        # контрактов где Tinkoff API не отдаёт specs). Если empirical seems off
        # vs cache — берём cache (доверяем live API для active контрактов).
        pv_snapshot: Optional[Decimal] = None
        pv_source: Optional[str] = None
        if instrument.instrument_type == InstrumentType.FUTURES:
            pv_snapshot, pv_source = self._compute_point_value_snapshot(
                matched, instrument
            )
        return Trade(
            account_id=str(account_id),
            instrument_uid=instrument.uid,
            instrument_figi=instrument.figi,
            instrument_type=instrument.instrument_type,
            direction=matched.direction,
            quantity=matched.quantity,
            entry_price=matched.entry_avg_price,
            exit_price=matched.exit.price_per_unit,
            entry_at=matched.entry_at,
            exit_at=exit_at,
            pnl=gross_pnl,
            net_pnl=net_pnl,
            commission_total=abs(
                matched.entry_commission_total + matched.exit.commission_total
            ),
            # Cost-basis в валюте (рубли). Для фьючерсов entry_price в пунктах,
            # а payment в рублях с учётом point_value — поэтому именно payment
            # является правильной базой для процента. PR 18.
            entry_value=abs(matched.entry_payment_total),
            exit_value=abs(matched.exit.payment_total),
            tax_total=Decimal(0),
            currency=matched.currency,
            entry_operation_ids=matched.entry_operation_ids,
            exit_operation_ids=(exit_operation_id,),
            position_id=matched.position_id,
            point_value=pv_snapshot,
            point_value_source=pv_source,
        )

    @staticmethod
    def _compute_point_value_snapshot(
        matched: MatchedTrade, instrument: Instrument
    ) -> tuple[Optional[Decimal], Optional[str]]:
        """Phase 9: вычислить snapshot point_value для futures trade.

        Логика:
        1. Empirical pv = |entry_payment_per_unit| / entry_avg_price
           (формула Tinkoff: payment ≈ qty × price × pv для futures BUY/SELL).
        2. Cached pv = min_pi_amt / min_pi из InstrumentORM.
        3. Если оба есть и расходятся > 5% → use empirical (truth от payments).
        4. Если cached OK или empirical отсутствует → use cached.
        5. Если ничего нет → return (None, None).
        """
        cached_pv: Optional[Decimal] = None
        if instrument.min_price_increment and instrument.min_price_increment != 0 \
                and instrument.min_price_increment_amount is not None:
            cached_pv = (
                instrument.min_price_increment_amount / instrument.min_price_increment
            )

        # Empirical: берём первый entry slice как репрезентативную операцию
        empirical_pv: Optional[Decimal] = None
        if matched.entry_slices and matched.entry_avg_price > 0:
            first_slice = matched.entry_slices[0]
            # payment_per_unit с правильным знаком (BUY: negative). Берём abs.
            pay_per_unit = abs(first_slice.lot.payment_per_unit)
            price = first_slice.lot.price_per_unit
            if price > 0:
                empirical_pv = pay_per_unit / price

        if empirical_pv is None and cached_pv is None:
            return None, None
        if empirical_pv is None:
            return cached_pv, "cache"
        if cached_pv is None or cached_pv == 0:
            return empirical_pv, "empirical_payment"
        drift = abs(empirical_pv - cached_pv) / cached_pv
        if drift <= Decimal("0.05"):
            return cached_pv, "cache"
        return empirical_pv, "empirical_payment"

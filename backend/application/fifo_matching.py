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

* SECURITY_IN / SECURITY_OUT и прочие корп-действия в FIFO **не идут** —
  они корректируют позицию напрямую (отдельная стадия, PR 8+ при
  необходимости).
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

        # Хронологический порядок — обязателен.
        sorted_ops = sorted(operations, key=lambda o: o.executed_at)
        trading_ops = [
            op
            for op in sorted_ops
            if op.state == OperationState.EXECUTED
            and op.operation_type in (_BUY_TYPES | _SELL_TYPES)
        ]
        # PR 8/9 используют non_trading ops в формулах (купоны, варм-маржа).
        # Передаём ВСЕ операции по инструменту в calculator — он сам
        # отфильтрует по типу и временному окну.
        non_trading_ops = tuple(
            op
            for op in sorted_ops
            if op.state == OperationState.EXECUTED
            and op.operation_type not in (_BUY_TYPES | _SELL_TYPES)
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
    ) -> None:
        op_direction = (
            TradeDirection.LONG if op.operation_type in _BUY_TYPES else TradeDirection.SHORT
        )
        op_qty = op.quantity or 0
        if op_qty <= 0:
            return

        # Если очередь пуста или одного направления с op — это open/расширение.
        if not queue or queue[0].direction == op_direction:
            queue.append(self._make_lot(op, direction=op_direction))
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
            flip_lot = self._make_lot(op, direction=op_direction)
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
                )
            )

    # ── factory методы ──────────────────────────────────────────────

    @staticmethod
    def _make_lot(op: Operation, *, direction: TradeDirection) -> FifoLot:
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
            tax_total=Decimal(0),
            currency=matched.currency,
            entry_operation_ids=matched.entry_operation_ids,
            exit_operation_ids=(exit_operation_id,),
        )

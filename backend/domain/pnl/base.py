"""
Базовые DTO для FIFO-движка и Protocol для per-instrument PnL-калькуляторов.

FifoLot — единица в очереди FIFO. Один лот = одно «открытое» событие
(BUY если позиция LONG, SELL если SHORT). При обратной операции (close)
эти лоты потребляются с головы очереди.

MatchedTrade — промежуточный результат матчинга, из которого FIFO-движок
строит запись `Trade` для журнала.

PnLCalculator — Protocol с одним методом `compute(matched, instrument)`.
Реализации:

* `domain/pnl/shares.py` — payment-based (gain = sell_payment + buy_payment;
  у BUY payment отрицательный, поэтому простое суммирование даёт чистый PnL).
* `domain/pnl/etfs.py`, `currencies.py` — те же формулы (повторное использование).
* `domain/pnl/bonds.py` (PR 8) — добавит купоны/НКД/амортизацию.
* `domain/pnl/futures.py` (PR 9) — добавит варм-маржу.
* `domain/pnl/options.py` (PR 10) — премии × multiplier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, Sequence

from domain.entities import Instrument
from domain.enums import TradeDirection


@dataclass(frozen=True, slots=True)
class FifoLot:
    """
    Один открытый лот в FIFO-очереди инструмента.

    `direction` — какое движение открыло этот лот:
    * LONG  — BUY (ждём SELL чтобы закрыть);
    * SHORT — SELL (ждём BUY чтобы покрыть).

    `quantity_remaining` — сколько ещё единиц осталось закрыть. Уменьшается
    при partial fill в обратную сторону. Полностью обнулённые лоты убираются
    из очереди.

    `payment_per_unit` — payment / quantity_original. Сохраняем уже посчитанным,
    чтобы при partial-fill брать `matched_qty * payment_per_unit` без накопления
    ошибки округления.
    """

    operation_id: str
    direction: TradeDirection
    quantity_remaining: int
    quantity_original: int
    price_per_unit: Decimal
    payment_per_unit: Decimal
    commission_per_unit: Decimal
    executed_at: datetime
    currency: str = "rub"

    def consume(self, qty: int) -> "FifoLot":
        """Вернуть новую FifoLot с уменьшенным `quantity_remaining`."""
        if qty > self.quantity_remaining:
            raise ValueError(f"cannot consume {qty} from lot with {self.quantity_remaining} remaining")
        return FifoLot(
            operation_id=self.operation_id,
            direction=self.direction,
            quantity_remaining=self.quantity_remaining - qty,
            quantity_original=self.quantity_original,
            price_per_unit=self.price_per_unit,
            payment_per_unit=self.payment_per_unit,
            commission_per_unit=self.commission_per_unit,
            executed_at=self.executed_at,
            currency=self.currency,
        )


@dataclass(frozen=True, slots=True)
class FillSlice:
    """
    Сколько единиц закрыто из конкретного лота. Используется как
    «фрагмент» MatchedTrade, чтобы корректно считать proportional payment'ы.
    """

    lot: FifoLot
    matched_qty: int

    @property
    def payment_share(self) -> Decimal:
        """Доля payment'а лота, относящаяся к закрытым `matched_qty` единицам."""
        return self.lot.payment_per_unit * Decimal(self.matched_qty)

    @property
    def commission_share(self) -> Decimal:
        return self.lot.commission_per_unit * Decimal(self.matched_qty)


@dataclass(frozen=True, slots=True)
class ExitFill:
    """
    Информация о закрывающей операции (sell для long, buy для short).
    """

    operation_id: str
    quantity: int
    price_per_unit: Decimal
    payment_per_unit: Decimal
    commission_per_unit: Decimal
    executed_at: datetime
    currency: str = "rub"

    @property
    def payment_total(self) -> Decimal:
        return self.payment_per_unit * Decimal(self.quantity)

    @property
    def commission_total(self) -> Decimal:
        return self.commission_per_unit * Decimal(self.quantity)


@dataclass(frozen=True)
class MatchedTrade:
    """
    Результат FIFO-матчинга одной закрытой сделки.

    Несколько `entry_slices` ↔ один `exit` — типичная история партиальных
    наборов: купил 10+10+10, продал 25 → MatchedTrade соберёт 3 slice'а
    (10, 10, 5) и один exit на 25.
    """

    direction: TradeDirection
    entry_slices: tuple[FillSlice, ...]
    exit: ExitFill
    instrument_uid: str
    currency: str

    @property
    def quantity(self) -> int:
        return sum(s.matched_qty for s in self.entry_slices)

    @property
    def entry_payment_total(self) -> Decimal:
        return sum((s.payment_share for s in self.entry_slices), Decimal(0))

    @property
    def entry_commission_total(self) -> Decimal:
        return sum((s.commission_share for s in self.entry_slices), Decimal(0))

    @property
    def entry_avg_price(self) -> Decimal:
        """Взвешенная средняя цена входа."""
        if self.quantity == 0:
            return Decimal(0)
        total = sum(
            (s.lot.price_per_unit * Decimal(s.matched_qty) for s in self.entry_slices),
            Decimal(0),
        )
        return total / Decimal(self.quantity)

    @property
    def entry_at(self) -> datetime:
        """Дата самой ранней входной операции."""
        return min(s.lot.executed_at for s in self.entry_slices)

    @property
    def entry_operation_ids(self) -> tuple[str, ...]:
        return tuple(s.lot.operation_id for s in self.entry_slices)


class PnLCalculator(Protocol):
    """
    Контракт для per-instrument формул PnL.

    Реализация должна вернуть `(pnl, net_pnl)`:
    * `pnl` — gross (без комиссий, без налогов, без купонов/маржи);
    * `net_pnl` — после всех специфичных для типа корректировок
      (комиссии, налоги, варм-маржа, купоны, и т.д.).

    `extra_operations` — дополнительные операции по инструменту в окне
    `[entry_at; exit_at]` (купоны, варм-маржа). Передаются движком из
    общего набора, чтобы calculator мог их учесть. Для shares — пустой.
    """

    def compute(
        self,
        matched: MatchedTrade,
        instrument: Instrument,
        extra_operations: Sequence[object] = (),
    ) -> tuple[Decimal, Decimal]:
        ...

    def compute_unrealized(
        self,
        *,
        instrument: Instrument,
        quantity_signed: int,
        avg_entry_price: Decimal,
        current_price: Decimal,
        extras: dict[str, object] | None = None,
    ) -> Decimal:
        """
        Mark-to-market PnL для открытой позиции (PR 11).

        * `quantity_signed` — положительное для LONG, отрицательное для SHORT.
        * `avg_entry_price` — взвешенная средняя цена входа из FIFO-очереди.
        * `current_price` — текущая цена из `get_last_prices()`.
        * `extras` — type-specific данные из `Position.extra` (например,
          `accumulated_varmargin` для фьючерсов, `current_aci` для облигаций).

        Базовая реализация (см. `domain/pnl/shares.py`): простая разница
        цен × signed qty. Для bonds/futures/options — accumulated extras.
        """
        ...

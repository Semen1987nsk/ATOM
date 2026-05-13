# mypy: disable-error-code="arg-type,assignment"

"""
TradeRepository — запись закрытых сделок журнала.

В PR 5 pipeline вызывает `FIFOMatchingService.match()` для каждого инструмента
и получает `list[Trade]` (закрытые). Этот репозиторий сохраняет их в БД
(таблица `trades`, см. models.py).

Стратегия: `replace_for_instrument()` удаляет все trade'ы с
`data_source='tinkoff_v2'` по инструменту и вставляет новые. Это
обеспечивает идемпотентность при повторном запуске FIFO на пересекающемся
наборе операций (например, после full_sync с самого начала).

Старые `data_source='legacy'` (импортированные старым tinkoff_service) и
'manual' (ручной ввод) остаются нетронутыми.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from domain.entities import Trade
from domain.enums import TradeDataSource, TradeDirection
from logger import get_logger
from models import Trade as TradeORM
from models import TradeDirection as TradeDirectionORM
from utils.datetime_utils import utc_now_naive

log = get_logger("trade_repo")


def _domain_to_orm_direction(d: TradeDirection):
    """domain TradeDirection -> ORM enum (значения совпадают по str, но
    мы используем разные enum-классы для domain/ORM)."""
    if d == TradeDirection.LONG:
        return TradeDirectionORM.LONG
    if d == TradeDirection.SHORT:
        return TradeDirectionORM.SHORT
    raise ValueError(f"unknown direction: {d}")


class TradeRepository:
    def replace_for_instrument(
        self,
        session: Session,
        *,
        account_id: int,
        instrument_uid: str,
        trades: Sequence[Trade],
        data_source: str = TradeDataSource.TINKOFF_V2.value,
    ) -> int:
        """
        Удалить все trade'ы по этому инструменту с `data_source` и вставить
        новые. Возвращает кол-во вставленных.

        Транзакция управляется снаружи — здесь только session.add()/flush(),
        commit делает вызывающий код.
        """
        # 1) Удалить старые записи (только своего data_source!).
        session.query(TradeORM).filter(
            TradeORM.account_id == account_id,
            TradeORM.instrument_uid == instrument_uid,
            TradeORM.data_source == data_source,
        ).delete(synchronize_session=False)

        # 2) Вставить новые.
        now = utc_now_naive()
        for trade in trades:
            session.add(self._trade_to_orm(trade, account_id, data_source, now))
        session.flush()
        return len(trades)

    def replace_for_account(
        self,
        session: Session,
        *,
        account_id: int,
        trades_by_instrument: dict[str, Sequence[Trade]],
        data_source: str = TradeDataSource.TINKOFF_V2.value,
    ) -> int:
        """Удобный batch-помощник: разом перезаписать trades по нескольким инструментам."""
        total = 0
        for uid, trades in trades_by_instrument.items():
            total += self.replace_for_instrument(
                session,
                account_id=account_id,
                instrument_uid=uid,
                trades=trades,
                data_source=data_source,
            )
        return total

    def count_for_account(
        self,
        session: Session,
        *,
        account_id: int,
        data_source: str | None = None,
    ) -> int:
        q = session.query(TradeORM).filter(TradeORM.account_id == account_id)
        if data_source is not None:
            q = q.filter(TradeORM.data_source == data_source)
        return q.count()

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _trade_to_orm(
        trade: Trade,
        account_id: int,
        data_source: str,
        synced_at,
    ) -> TradeORM:
        # У ORM-Trade много обязательных полей из старых требований
        # (symbol, entry_at, direction, entry_price, quantity).
        # Symbol для нового sync = instrument_figi или uid (для опционов).
        symbol = trade.instrument_figi or trade.instrument_uid

        # naive UTC для БД.
        entry_at = (
            trade.entry_at.replace(tzinfo=None)
            if trade.entry_at.tzinfo
            else trade.entry_at
        )
        exit_at = None
        if trade.exit_at is not None:
            exit_at = (
                trade.exit_at.replace(tzinfo=None)
                if trade.exit_at.tzinfo
                else trade.exit_at
            )

        return TradeORM(
            account_id=account_id,
            symbol=symbol,
            asset_type=(
                trade.instrument_type.value if trade.instrument_type else None
            ),
            direction=_domain_to_orm_direction(trade.direction),
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=Decimal(trade.quantity),
            entry_at=entry_at,
            exit_at=exit_at,
            pnl=trade.pnl,
            net_pnl=trade.net_pnl,
            commission=trade.commission_total,
            currency=trade.currency or "RUB",
            data_source=data_source,
            instrument_uid=trade.instrument_uid,
            instrument_figi=trade.instrument_figi,
            instrument_type_v2=(
                trade.instrument_type.value if trade.instrument_type else None
            ),
            operations=[
                {"role": "entry", "operation_id": op_id}
                for op_id in trade.entry_operation_ids
            ]
            + [
                {"role": "exit", "operation_id": op_id}
                for op_id in trade.exit_operation_ids
            ],
        )

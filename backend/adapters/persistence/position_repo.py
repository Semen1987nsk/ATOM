# mypy: disable-error-code="arg-type,assignment"

"""
PositionRepository — открытые позиции с FIFO-лотами в `Position.extra`.

В `extra` JSON храним массив открытых лотов FIFO-очереди для конкретного
(account_id, instrument_uid). Это нужно для инкрементального матчинга
без сохранения «снимков» в отдельной таблице.

Формат `extra["lots"]`:

```json
[
  {
    "operation_id": "op-123",
    "direction": "LONG",
    "quantity_remaining": 50,
    "quantity_original": 100,
    "price_per_unit": "270.50",
    "payment_per_unit": "-271.50",
    "commission_per_unit": "-0.50",
    "executed_at": "2026-05-09T10:00:00Z",
    "currency": "rub"
  },
  ...
]
```

PR 11 (mark-to-market) будет дополнительно класть в extra текущую цену и
PnL — это не конфликтует, разные ключи.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from domain.enums import InstrumentType, TradeDirection
from domain.pnl.base import FifoLot
from logger import get_logger
from models import PositionORM
from utils.datetime_utils import utc_now_naive

log = get_logger("position_repo")


def _lot_to_dict(lot: FifoLot) -> dict:
    return {
        "operation_id": lot.operation_id,
        "direction": lot.direction.value,
        "quantity_remaining": lot.quantity_remaining,
        "quantity_original": lot.quantity_original,
        "price_per_unit": str(lot.price_per_unit),
        "payment_per_unit": str(lot.payment_per_unit),
        "commission_per_unit": str(lot.commission_per_unit),
        "executed_at": (lot.executed_at.isoformat() if lot.executed_at else None),
        "currency": lot.currency,
    }


def _dict_to_lot(raw: dict) -> FifoLot:
    executed_at_raw = raw.get("executed_at")
    if executed_at_raw is None:
        executed_at = utc_now_naive()
    else:
        executed_at = datetime.fromisoformat(executed_at_raw)
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)
    return FifoLot(
        operation_id=raw["operation_id"],
        direction=TradeDirection(raw["direction"]),
        quantity_remaining=int(raw["quantity_remaining"]),
        quantity_original=int(raw["quantity_original"]),
        price_per_unit=Decimal(raw["price_per_unit"]),
        payment_per_unit=Decimal(raw["payment_per_unit"]),
        commission_per_unit=Decimal(raw["commission_per_unit"]),
        executed_at=executed_at,
        currency=raw.get("currency", "rub"),
    )


class PositionRepository:
    def get_open_lots(
        self,
        session: Session,
        *,
        account_id: int,
        instrument_uid: str,
    ) -> list[FifoLot]:
        row = (
            session.query(PositionORM)
            .filter_by(account_id=account_id, instrument_uid=instrument_uid)
            .first()
        )
        if row is None or not row.extra:
            return []
        try:
            raw_lots = row.extra.get("lots", [])
        except AttributeError:
            # Если extra хранится как строка (старый формат?), парсим JSON.
            raw_lots = json.loads(row.extra).get("lots", [])
        return [_dict_to_lot(r) for r in raw_lots]

    def save(
        self,
        session: Session,
        *,
        account_id: int,
        instrument_uid: str,
        instrument_type: InstrumentType,
        open_lots: Sequence[FifoLot],
        currency: str = "rub",
    ) -> None:
        """
        UPSERT позиции. `quantity` считается из лотов: положительное для
        LONG-позиции, отрицательное для SHORT (если есть SHORT-лоты, они
        все должны быть одного направления — иначе очередь была бы flip'ом).

        avg_entry_price — взвешенное среднее по `quantity_remaining`.
        """
        if not open_lots:
            # Удалить запись если позиция полностью закрыта.
            session.query(PositionORM).filter_by(
                account_id=account_id, instrument_uid=instrument_uid
            ).delete(synchronize_session=False)
            return

        # Все лоты в очереди должны быть одного направления (по инварианту
        # FIFO движка: если приходит обратное движение, лоты сначала
        # потребляются, затем при flip создаются новые противоположного).
        first_dir = open_lots[0].direction
        if not all(l.direction == first_dir for l in open_lots):
            raise ValueError("inconsistent lot directions in position queue")

        total_qty = sum(l.quantity_remaining for l in open_lots)
        if total_qty == 0:
            session.query(PositionORM).filter_by(
                account_id=account_id, instrument_uid=instrument_uid
            ).delete(synchronize_session=False)
            return

        weighted_sum = sum(
            l.price_per_unit * Decimal(l.quantity_remaining) for l in open_lots
        )
        avg_entry = weighted_sum / Decimal(total_qty)
        # signed для UI/расчёта позиции
        signed_qty = total_qty if first_dir == TradeDirection.LONG else -total_qty

        existing: Optional[PositionORM] = (
            session.query(PositionORM)
            .filter_by(account_id=account_id, instrument_uid=instrument_uid)
            .first()
        )

        now = utc_now_naive()
        payload_extra = {
            "lots": [_lot_to_dict(l) for l in open_lots],
        }

        if existing is None:
            session.add(
                PositionORM(
                    account_id=account_id,
                    instrument_uid=instrument_uid,
                    instrument_type=instrument_type.value,
                    quantity=signed_qty,
                    avg_entry_price=avg_entry,
                    current_price=None,
                    unrealized_pnl=None,
                    last_priced_at=None,
                    currency=currency,
                    extra=payload_extra,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.instrument_type = instrument_type.value
            existing.quantity = signed_qty
            existing.avg_entry_price = avg_entry
            existing.currency = currency
            # MTM-данные затирать НЕ нужно — PR 11 их обновит отдельно.
            # Если позиция была закрыта-и-открыта, MTM пересчитается на
            # следующем sync.
            old_extra = existing.extra or {}
            old_extra["lots"] = payload_extra["lots"]
            existing.extra = old_extra
            existing.updated_at = now

    def list_for_account(
        self, session: Session, *, account_id: int
    ) -> list[PositionORM]:
        return (
            session.query(PositionORM)
            .filter_by(account_id=account_id)
            .all()
        )

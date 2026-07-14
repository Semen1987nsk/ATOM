"""
Diagnose T7 FIFO qty vs API qty mismatch — для каждой расходящейся позиции
показать ВСЕ операции по этому инструменту и matched/unmatched trades.

Помогает понять:
1. Сплит / spin-off — недостающие операции корпоративного типа
2. Дублирующиеся БД operations
3. Bug в FIFO-matching (например wrong direction inference)
4. Tinkoff API portfolio показывает legacy позицию которой нет в operations
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from collections import defaultdict
from decimal import Decimal

import models
from database import SessionLocal


def main(account_id: int) -> int:
    db = SessionLocal()
    try:
        positions = db.query(models.PositionORM).filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        ).all()
        print(f"Active positions for account #{account_id}: {len(positions)}")

        mismatches = []
        for pos in positions:
            open_trades = db.query(models.Trade).filter(
                models.Trade.account_id == account_id,
                models.Trade.instrument_uid == pos.instrument_uid,
                models.Trade.exit_at.is_(None),
            ).all()
            fifo_qty = 0
            for t in open_trades:
                sign = 1 if (t.direction or "").lower() == "long" else -1
                fifo_qty += sign * (t.quantity or 0)
            if abs(fifo_qty - pos.quantity) > 1:
                mismatches.append((pos, open_trades, fifo_qty))

        print(f"Mismatched positions: {len(mismatches)}\n")

        for pos, open_trades, fifo_qty in mismatches:
            inst = db.query(models.InstrumentORM).filter_by(uid=pos.instrument_uid).first()
            tk = inst.ticker if inst else "?"
            name = inst.name if inst else "?"
            print("=" * 75)
            print(f"INSTRUMENT  uid={pos.instrument_uid}  ticker={tk}  name={name}")
            print(f"  position.quantity = {pos.quantity}  (Tinkoff portfolio)")
            print(f"  fifo_qty          = {fifo_qty}      (sum of open Trade.quantity)")
            print(f"  delta             = {pos.quantity - fifo_qty}")
            print()
            print(f"  Open Trades ({len(open_trades)}):")
            for t in open_trades:
                print(
                    f"    id={t.id:>5}  dir={t.direction:<5}  qty={t.quantity:>6}  "
                    f"entry={t.entry_at}"
                )

            # Все операции для этого инструмента
            ops = db.query(models.OperationORM).filter(
                models.OperationORM.account_id == account_id,
                models.OperationORM.instrument_uid == pos.instrument_uid,
            ).order_by(models.OperationORM.executed_at.asc()).all()
            print(f"\n  All operations ({len(ops)}):")
            agg_by_type = defaultdict(lambda: {"count": 0, "qty": 0})
            for op in ops:
                t = (op.operation_type or "").lower()
                agg_by_type[t]["count"] += 1
                agg_by_type[t]["qty"] += int(op.quantity or 0)
            for t, d in sorted(agg_by_type.items()):
                print(f"    {t:30}  count={d['count']:>4}  Sum_qty={d['qty']:>6}")
            # Net qty по операциям (если только buy/sell)
            buys = sum(int(o.quantity or 0) for o in ops if (o.operation_type or "").lower() in {"buy", "buy_card", "buy_margin"} and o.state != "canceled")
            sells = sum(int(o.quantity or 0) for o in ops if (o.operation_type or "").lower() in {"sell", "sell_card", "sell_margin"} and o.state != "canceled")
            net = buys - sells
            print(f"    {'NET (buy - sell)':30}  buys={buys:>6}  sells={sells:>6}  net={net:>6}")
            print()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    args = parser.parse_args()
    sys.exit(main(args.account_id))

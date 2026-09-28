"""
Diagnose T3 — найти operations где исходный API quantity был дробным,
но мы сохранили в БД как Integer (потерянная точность).
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import models
from database import SessionLocal


def main(account_id: int, limit: int = 50) -> int:
    db = SessionLocal()
    try:
        ops = db.query(models.OperationORM).filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.operation_type.in_(["buy", "sell"]),
            models.OperationORM.quantity > 0,
            models.OperationORM.price_units.isnot(None),
            models.OperationORM.payment_units.isnot(None),
        ).all()
        print(f"Loaded {len(ops)} buy/sell ops for account #{account_id}\n")

        rows = []
        for op in ops:
            price = Decimal(op.price_units or 0) + Decimal(op.price_nano or 0) / Decimal(1_000_000_000)
            payment = Decimal(op.payment_units or 0) + Decimal(op.payment_nano or 0) / Decimal(1_000_000_000)
            if price <= 0 or payment == 0:
                continue
            expected = abs(payment) / price
            diff = abs(expected - Decimal(op.quantity))
            if diff > Decimal("0.5") and expected > 0 and abs(expected - int(expected)) > Decimal("0.01"):
                inst = db.query(models.InstrumentORM).filter_by(uid=op.instrument_uid).first()
                rows.append({
                    "op_id": op.operation_id,
                    "type": op.operation_type,
                    "instr_type": op.instrument_type,
                    "ticker": (inst.ticker if inst else None),
                    "saved_qty": op.quantity,
                    "expected_qty": float(expected),
                    "delta": float(expected - Decimal(op.quantity)),
                    "price": float(price),
                    "payment": float(payment),
                    "executed_at": op.executed_at,
                })
        print(f"Found {len(rows)} ops with fractional drift (>0.5 unit):\n")
        for r in rows[:limit]:
            print(
                f"  {r['executed_at']}  {r['op_id'][:24]:24}  type={r['type']:5}  "
                f"itype={r['instr_type']:8}  tkr={r['ticker'] or '?':6}"
            )
            print(
                f"    saved_qty={r['saved_qty']:>6}  expected={r['expected_qty']:>12.4f}  "
                f"delta={r['delta']:>+10.4f}  price={r['price']}  payment={r['payment']}"
            )
        # Group by instrument
        print("\nBy ticker:")
        from collections import Counter
        c = Counter(r['ticker'] or '?' for r in rows)
        for tk, n in c.most_common():
            print(f"  {tk:10}  {n} ops")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    sys.exit(main(args.account_id, args.limit))

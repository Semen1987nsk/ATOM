"""
Diagnose Commissions -- AU15 проверка childOperations vs flat BROKER_FEE.

Plain ASCII output for Windows cp1251 console.

ИСПОЛЬЗОВАНИЕ:

    cd backend
    python -m tools.diagnose_commissions --account-id 4
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from database import SessionLocal
from models import OperationORM


def _money(units, nano) -> Decimal:
    return Decimal(units or 0) + Decimal(nano or 0) / Decimal(1_000_000_000)


def diagnose(account_id: int, limit_examples: int = 5) -> None:
    session = SessionLocal()
    try:
        ops = (
            session.query(OperationORM)
            .filter(OperationORM.account_id == account_id)
            .order_by(OperationORM.executed_at.asc())
            .all()
        )
        print(f"Loaded {len(ops)} ops for account_id={account_id}")

        trade_types = {"buy", "buy_card", "buy_margin", "sell", "sell_card", "sell_margin"}
        fee_types = {"broker_fee", "broker_commission"}

        trades = [o for o in ops if (o.operation_type or "").lower() in trade_types]
        fees = [o for o in ops if (o.operation_type or "").lower() in fee_types]

        sum_trade_commission = sum(
            (_money(o.commission_units, o.commission_nano) for o in trades),
            Decimal(0),
        )
        sum_fee_payment = sum(
            (abs(_money(o.payment_units, o.payment_nano)) for o in fees),
            Decimal(0),
        )

        print("=" * 60)
        print("TOTALS")
        print("=" * 60)
        print(f"Sum |op.commission| on BUY/SELL ({len(trades)} ops): {sum_trade_commission:,.4f} RUB")
        print(f"Sum |payment| on BROKER_FEE ({len(fees)} ops):       {sum_fee_payment:,.4f} RUB")
        abs_tc = abs(sum_trade_commission)
        abs_fp = abs(sum_fee_payment)
        if abs_tc == 0 and abs_fp > 0:
            print("=> VARIANT B: BUY/SELL.commission is always 0, broker fee is a separate op.")
            print("   Trade.net_pnl does NOT include broker_fee. UNDERESTIMATED net_pnl.")
        elif abs_tc > 0 and abs_fp == 0:
            print("=> VARIANT A1: all commission in op.commission on trades. No BROKER_FEE ops.")
            print("   Clean structure, no double-count possible.")
        elif abs_tc > 0 and abs_fp > 0:
            ratio = abs_fp / abs_tc if abs_tc != 0 else None
            print(f"ratio |BROKER_FEE| / |op.commission| = {ratio}")
            if ratio and Decimal("0.95") < ratio < Decimal("1.05"):
                print("=> CONFIRMED A: BROKER_FEE DUPLICATES op.commission on trade.")
                print("   reconciliation_service DOUBLE-COUNTS commission!")
                print("   Fix: in reconciliation, take ONE of the two, not both.")
            elif ratio and Decimal("0.5") < ratio < Decimal("1.5"):
                print("=> SUSPECT A (partial): BROKER_FEE close to op.commission.")
                print("   Likely double-counting in some subset.")
            else:
                print("=> VARIANT B': different commissions (exchange vs broker), not duplicates.")
                print("   reconciliation: split is correct.")
                print("   FIFO net_pnl: only op.commission accounted, broker_fee lost.")
        else:
            print("=> Not enough data to classify.")

        print()
        print("=" * 60)
        print("LINK via parent_operation_id")
        print("=" * 60)
        trades_by_broker_id = {o.operation_id: o for o in trades if o.operation_id}
        linked_fees = [
            o
            for o in fees
            if o.parent_operation_id and o.parent_operation_id in trades_by_broker_id
        ]
        unlinked_fees = [
            o
            for o in fees
            if not o.parent_operation_id or o.parent_operation_id not in trades_by_broker_id
        ]
        print(f"  BROKER_FEE with parent found: {len(linked_fees)}")
        print(f"  BROKER_FEE without parent:    {len(unlinked_fees)}")

        if linked_fees:
            matches = []
            for fee in linked_fees[:limit_examples]:
                parent = trades_by_broker_id.get(fee.parent_operation_id)
                if not parent:
                    continue
                parent_comm = _money(parent.commission_units, parent.commission_nano)
                fee_pmt = abs(_money(fee.payment_units, fee.payment_nano))
                matches.append((parent, fee, parent_comm, fee_pmt))

            print()
            print(f"  EXAMPLES (first {len(matches)}):")
            print(f"  {'parent_op_id':36}  {'parent.commission':>18}  {'fee.payment':>14}  verdict")
            for parent, fee, pc, fp in matches:
                diff = abs(pc - fp) / max(pc, fp, Decimal("0.01"))
                verdict = "DUPLICATE" if diff < Decimal("0.05") else "DIFFERENT"
                print(
                    f"  {parent.operation_id[:36]:36}  {pc:>18,.4f}  {fp:>14,.4f}  {verdict}"
                )

        # Also: show distribution of op_types
        print()
        print("=" * 60)
        print("OPERATION TYPE DISTRIBUTION")
        print("=" * 60)
        from collections import Counter
        type_counts = Counter((o.operation_type or "").lower() for o in ops)
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  {t:30} {c:>6}")

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose AU15: childOperations vs flat BROKER_FEE")
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--examples", type=int, default=5)
    args = parser.parse_args()
    diagnose(args.account_id, limit_examples=args.examples)


if __name__ == "__main__":
    main()

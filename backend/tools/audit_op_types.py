"""One-off audit: вывести структуру OperationORM по operation_type для acc#4.

Цель — найти все cash flows не учтённые в reconcile_journal_vs_cash.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

import database
import models
from sqlalchemy import func


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    args = parser.parse_args()

    session = database.SessionLocal()
    try:
        rows = (
            session.query(
                models.OperationORM.operation_type,
                func.count(models.OperationORM.id).label("cnt"),
                func.coalesce(func.sum(models.OperationORM.payment_units), 0).label("sum_units"),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0).label("sum_nano"),
            )
            .filter(
                models.OperationORM.account_id == args.account_id,
                models.OperationORM.state == "executed",
            )
            .group_by(models.OperationORM.operation_type)
            .order_by(models.OperationORM.operation_type)
            .all()
        )

        print(f"=== OperationORM по типам для account_id={args.account_id} (state=executed) ===\n")
        print(f"{'operation_type':<32} {'count':>8} {'total ₽':>16}")
        print("-" * 60)
        total_in = Decimal(0)
        total_out = Decimal(0)
        for r in rows:
            amount = Decimal(int(r.sum_units or 0)) + Decimal(int(r.sum_nano or 0)) / Decimal(1_000_000_000)
            print(f"{r.operation_type:<32} {r.cnt:>8} {amount:>16,.2f}")
            if amount > 0:
                total_in += amount
            else:
                total_out += amount

        print("-" * 60)
        print(f"{'TOTAL inflows':<32} {'':>8} {total_in:>16,.2f}")
        print(f"{'TOTAL outflows':<32} {'':>8} {total_out:>16,.2f}")
        print(f"{'NET':<32} {'':>8} {(total_in + total_out):>16,.2f}")

        # Sanity: Account.last_portfolio_value
        acc = session.query(models.Account).get(args.account_id)
        if acc:
            lpv = float(acc.last_portfolio_value or 0)
            print(f"\nAccount.last_portfolio_value: {lpv:,.2f} ₽")
            print(f"NET ops + last_portfolio (если NET=net_deposit, должно быть P&L): "
                  f"{lpv - float(total_in + total_out):,.2f} ₽")

        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())

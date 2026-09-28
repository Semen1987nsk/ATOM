"""Симулировать stats.py логику для проверки total_pnl_with_unrealized.

Должен вернуть -248,552.57 для acc#4 (matches T-Bank broker number).
"""
from __future__ import annotations
import argparse
import sys

import database
import models
from sqlalchemy import func


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    args = p.parse_args()

    s = database.SessionLocal()
    try:
        # 1. Σ Trade.net_pnl closed
        total_pnl = float(
            s.query(func.coalesce(func.sum(models.Trade.net_pnl), 0))
            .filter(
                models.Trade.account_id == args.account_id,
                models.Trade.pnl.isnot(None),
                models.Trade.exit_at.isnot(None),
            )
            .scalar()
            or 0
        )

        # 2. Position.unrealized_pnl
        unrealized_pos = float(
            s.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0))
            .filter(models.PositionORM.account_id == args.account_id)
            .scalar()
            or 0
        )

        # 3. net_deposits via classifier
        from domain.pnl.cash_flow_classification import (
            CashFlowCategory,
            operation_types_in,
        )
        deposit_types = tuple(operation_types_in(CashFlowCategory.NET_DEPOSIT))
        dep_row = (
            s.query(
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            )
            .filter(
                models.OperationORM.account_id == args.account_id,
                models.OperationORM.operation_type.in_(deposit_types),
                models.OperationORM.state == "executed",
            )
            .one()
        )
        net_deposits = float(dep_row[0] or 0) + float(dep_row[1] or 0) / 1e9

        # 4. last_portfolio_value
        acc = s.get(models.Account, args.account_id)
        last_portfolio = float(acc.last_portfolio_value or 0)

        # 5. cash_pnl_truth (Phase 6 формула)
        cash_pnl_truth = last_portfolio - net_deposits
        unrealized_phase6 = cash_pnl_truth - total_pnl

        print(f"=== Stats simulation для acc#{args.account_id} (Phase 6) ===\n")
        print(f"total_pnl (Σ closed Trade.net_pnl):       {total_pnl:>16,.2f} ₽")
        print(f"unrealized_pnl_position_based:           {unrealized_pos:>16,.2f} ₽")
        print()
        print(f"last_portfolio_value:                    {last_portfolio:>16,.2f} ₽")
        print(f"net_deposits (via classifier):           {net_deposits:>16,.2f} ₽")
        print(f"cash_pnl_truth = portfolio - deposits:   {cash_pnl_truth:>16,.2f} ₽")
        print()
        print(f"--- Phase 6 dashboard values ---")
        print(f"total_pnl_with_unrealized (= cash truth): {cash_pnl_truth:>16,.2f} ₽")
        print(f"unrealized_pnl (= truth - realized):     {unrealized_phase6:>16,.2f} ₽")
        print(f"total_pnl (realized closed):             {total_pnl:>16,.2f} ₽")
        print()
        print(f"Sanity check vs T-Bank broker (-248,552.57):")
        diff_vs_broker = cash_pnl_truth - (-248552.57)
        print(f"  Diff: {diff_vs_broker:,.2f} ₽")
        if abs(diff_vs_broker) < 1.0:
            print(f"  ✅ MATCH (< 1 ₽)")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

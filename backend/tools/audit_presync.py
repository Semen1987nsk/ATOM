"""Проверка возможного pre-sync gap для acc#4."""
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
    aid = args.account_id

    s = database.SessionLocal()
    try:
        acc = s.get(models.Account, aid)
        conn = s.query(models.BrokerConnection).filter(
            models.BrokerConnection.account_id == aid
        ).first()
        first_op = s.query(models.OperationORM).filter(
            models.OperationORM.account_id == aid,
            models.OperationORM.state == "executed",
        ).order_by(models.OperationORM.executed_at.asc()).first()
        last_op = s.query(models.OperationORM).filter(
            models.OperationORM.account_id == aid,
            models.OperationORM.state == "executed",
        ).order_by(models.OperationORM.executed_at.desc()).first()
        print(f"Account #{aid}: {acc.name}")
        print(f"  last_portfolio_value: {acc.last_portfolio_value}")
        print(f"  last_portfolio_at:    {acc.last_portfolio_at}")
        print(f"  initial_balance:      {acc.initial_balance}")
        print(f"  initial_balance_source: {acc.initial_balance_source}")
        if conn:
            print(f"  BrokerConnection.sync_from_date: {conn.sync_from_date}")
            print(f"  BrokerConnection.sync_cursor:    {conn.sync_cursor}")
            print(f"  BrokerConnection.broker_account_id: {conn.broker_account_id}")
        if first_op:
            print(f"  Earliest operation: {first_op.executed_at}  type={first_op.operation_type}")
        if last_op:
            print(f"  Latest operation:   {last_op.executed_at}  type={last_op.operation_type}")
        first_trade = s.query(models.Trade).filter(
            models.Trade.account_id == aid
        ).order_by(models.Trade.entry_at.asc()).first()
        if first_trade:
            print(f"  Earliest trade entry: {first_trade.entry_at}")

        # Check BalanceSnapshot
        snap = s.query(models.BalanceSnapshot).filter(
            models.BalanceSnapshot.account_id == aid
        ).order_by(models.BalanceSnapshot.date.asc()).first()
        if snap:
            print(f"  First BalanceSnapshot: date={snap.date} balance={snap.balance}")
        else:
            print(f"  No BalanceSnapshot records")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

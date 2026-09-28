"""Phase 7 final verification: симулировать stats.py логику для acc#4.

Проверяет что новая формула dashboard:
  total_pnl_with_unrealized = total_pnl + unrealized_pnl_position + account_adjustments

натурально совпадает с broker'ом -248,552.57 ₽.
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
    aid = args.account_id

    s = database.SessionLocal()
    try:
        from domain.pnl.cash_flow_classification import CashFlowCategory, operation_types_in

        def sum_cat(cat: CashFlowCategory) -> float:
            types = tuple(operation_types_in(cat))
            if not types:
                return 0.0
            row = s.query(
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            ).filter(
                models.OperationORM.account_id == aid,
                models.OperationORM.state == "executed",
                models.OperationORM.operation_type.in_(types),
            ).one()
            return float(row[0] or 0) + float(row[1] or 0) / 1e9

        total_pnl = float(s.query(func.coalesce(func.sum(models.Trade.net_pnl), 0))
            .filter(models.Trade.account_id == aid, models.Trade.pnl.isnot(None),
                    models.Trade.exit_at.isnot(None)).scalar() or 0)

        unrealized_pos = float(s.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0))
            .filter(models.PositionORM.account_id == aid).scalar() or 0)

        # Account-level adjustments (orphans)
        raw_vm = sum_cat(CashFlowCategory.VARMARGIN)
        raw_attr = sum_cat(CashFlowCategory.ATTRIBUTABLE_FEE)
        raw_tax = sum_cat(CashFlowCategory.TAX)
        raw_income = sum_cat(CashFlowCategory.INCOME)
        raw_broker = sum_cat(CashFlowCategory.BROKER_COMMISSION)

        attr_vm = float(s.query(func.coalesce(func.sum(models.Trade.varmargin_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        attr_mf = float(s.query(func.coalesce(func.sum(models.Trade.margin_fee_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        attr_sf = float(s.query(func.coalesce(func.sum(models.Trade.service_fee_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        attr_o = float(s.query(func.coalesce(func.sum(models.Trade.other_fees_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        sum_comm = float(s.query(func.coalesce(func.sum(models.Trade.commission), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0)

        account_adjustments = (
            (raw_vm - attr_vm) + (raw_attr - (attr_mf + attr_sf))
            + (raw_tax - attr_o) + raw_income + (raw_broker + sum_comm)
        )
        unrealized_pnl_ui = unrealized_pos + account_adjustments
        total_pnl_with_unrealized = total_pnl + unrealized_pnl_ui

        # Compare to broker cash truth
        acc = s.get(models.Account, aid)
        net_dep = sum_cat(CashFlowCategory.NET_DEPOSIT)
        cash_truth = float(acc.last_portfolio_value or 0) - net_dep

        print(f"=== Phase 7 Dashboard simulation for acc#{aid} ===\n")
        print(f"--- Dashboard fields (stats.py new formula) ---")
        print(f"  total_pnl (closed):              {total_pnl:>15,.2f} ₽")
        print(f"  unrealized_pnl_position_based:   {unrealized_pos:>15,.2f} ₽")
        print(f"  account_level_adjustments:       {account_adjustments:>15,.2f} ₽")
        print(f"  unrealized_pnl (UI):             {unrealized_pnl_ui:>15,.2f} ₽")
        print(f"  total_pnl_with_unrealized:       {total_pnl_with_unrealized:>15,.2f} ₽")
        print()
        print(f"--- Positions page (same data) ---")
        print(f"  Σ Position.unrealized_pnl:       {unrealized_pos:>15,.2f} ₽")
        print()
        print(f"--- Reference: T-Bank broker ---")
        print(f"  «Доход с учётом налогов/комиссий»: {cash_truth:>15,.2f} ₽")
        print()
        diff = total_pnl_with_unrealized - cash_truth
        pct = abs(diff) / abs(cash_truth) * 100 if abs(cash_truth) > 1 else 0
        print(f"--- Convergence (без podgonki) ---")
        print(f"  Dashboard − broker:              {diff:>15,.2f} ₽  ({pct:.2f}%)")
        if pct < 1.0:
            print(f"\n  ✅ NATURAL MATCH (< 1%)")
        elif pct < 5.0:
            print(f"\n  ⚠️  WARN — diff {pct:.2f}% (acceptable, см. residual)")
        else:
            print(f"\n  ❌ MISMATCH — diff {pct:.2f}%")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

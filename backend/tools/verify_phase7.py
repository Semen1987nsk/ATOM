"""Phase 7 verification: Position.unrealized_pnl matches Tinkoff expected_yield."""
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
        positions = (
            s.query(models.PositionORM)
            .filter(models.PositionORM.account_id == aid, models.PositionORM.quantity != 0)
            .all()
        )
        print(f"=== Phase 7 Position sync verification for acc#{aid} ===\n")
        print(f"{'uid':<40} {'type':<10} {'qty':>6} {'unrealized_pnl':>15} {'expected_yield':>15} {'var_margin':>10}")
        print("-" * 110)
        sum_unr = 0.0
        sum_ey = 0.0
        sum_vm = 0.0
        for pos in positions:
            instr = s.query(models.InstrumentORM).filter(
                models.InstrumentORM.uid == pos.instrument_uid
            ).first()
            ticker = instr.ticker if instr else pos.instrument_uid[:12]
            unr = float(pos.unrealized_pnl or 0)
            ey = float(pos.expected_yield_rub or 0)
            vm = float(pos.var_margin_rub or 0)
            print(f"{ticker:<40} {pos.instrument_type:<10} {pos.quantity:>6} "
                  f"{unr:>15,.2f} {ey:>15,.2f} {vm:>10,.2f}")
            sum_unr += unr
            sum_ey += ey
            sum_vm += vm
        print("-" * 110)
        print(f"{'Σ':<40} {'':10} {'':6} {sum_unr:>15,.2f} {sum_ey:>15,.2f} {sum_vm:>10,.2f}")

        # Trade aggregations
        closed_net_pnl = float(s.query(func.coalesce(func.sum(models.Trade.net_pnl), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0)

        # Orphans calculation
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

        net_deposits = sum_cat(CashFlowCategory.NET_DEPOSIT)
        raw_varmargin = sum_cat(CashFlowCategory.VARMARGIN)
        raw_attr_fee = sum_cat(CashFlowCategory.ATTRIBUTABLE_FEE)
        raw_tax = sum_cat(CashFlowCategory.TAX)
        raw_income = sum_cat(CashFlowCategory.INCOME)
        raw_broker = sum_cat(CashFlowCategory.BROKER_COMMISSION)

        # Attributed sums
        attr_varmargin = float(s.query(func.coalesce(func.sum(models.Trade.varmargin_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        attr_margin_fee = float(s.query(func.coalesce(func.sum(models.Trade.margin_fee_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        attr_service_fee = float(s.query(func.coalesce(func.sum(models.Trade.service_fee_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        attr_other = float(s.query(func.coalesce(func.sum(models.Trade.other_fees_attributed), 0))
            .filter(models.Trade.account_id == aid).scalar() or 0)
        # Commission (closed only, stored as abs)
        sum_commission_closed = float(s.query(func.coalesce(func.sum(models.Trade.commission), 0))
            .filter(models.Trade.account_id == aid, models.Trade.exit_at.isnot(None))
            .scalar() or 0)

        orphan_varmargin = raw_varmargin - attr_varmargin
        orphan_attr_fee = raw_attr_fee - (attr_margin_fee + attr_service_fee)
        orphan_tax = raw_tax - attr_other  # other_fees_attributed includes tax
        orphan_income = raw_income  # not yet attributed
        orphan_broker = raw_broker + sum_commission_closed  # raw is negative, commission stored positive

        account_adjustments = orphan_varmargin + orphan_attr_fee + orphan_tax + orphan_income + orphan_broker

        acc = s.get(models.Account, aid)
        cash_pnl = float(acc.last_portfolio_value or 0) - net_deposits

        print(f"\n=== Journal vs cash_truth (Phase 7) ===")
        print(f"  closed Trade.net_pnl:             {closed_net_pnl:>15,.2f} ₽")
        print(f"  Σ Position.unrealized_pnl:        {sum_unr:>15,.2f} ₽")
        print(f"  + account-level adjustments:      {account_adjustments:>15,.2f} ₽")
        print(f"    orphan varmargin:               {orphan_varmargin:>15,.2f} ₽")
        print(f"    orphan attributable_fee:        {orphan_attr_fee:>15,.2f} ₽")
        print(f"    orphan tax:                     {orphan_tax:>15,.2f} ₽")
        print(f"    orphan income:                  {orphan_income:>15,.2f} ₽")
        print(f"    orphan broker_commission:       {orphan_broker:>15,.2f} ₽")
        journal = closed_net_pnl + sum_unr + account_adjustments
        print(f"  Σ journal:                        {journal:>15,.2f} ₽")
        print(f"\n  cash_pnl_truth:                   {cash_pnl:>15,.2f} ₽")
        print(f"  diff:                             {journal - cash_pnl:>15,.2f} ₽")
        pct = abs(journal - cash_pnl) / abs(cash_pnl) * 100 if abs(cash_pnl) > 1 else 0
        print(f"  diff %:                           {pct:>14,.2f}%")
        if pct < 1.0:
            print(f"\n  ✅ NATURAL MATCH (< 1%)")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

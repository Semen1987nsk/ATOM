"""Гипотеза: varmargin attribut'ится на closed SHARES (phantom loss).

Подсчёт: Σ Trade.varmargin_attributed по instrument_type.
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
        # JOIN Trade с InstrumentORM чтобы получить instrument_type
        from sqlalchemy import case
        rows = (
            s.query(
                models.InstrumentORM.instrument_type,
                models.Trade.exit_at.isnot(None).label("is_closed"),
                func.count(models.Trade.id).label("cnt"),
                func.coalesce(func.sum(models.Trade.varmargin_attributed), 0).label("sum_varmargin"),
                func.coalesce(func.sum(models.Trade.margin_fee_attributed), 0).label("sum_margin"),
                func.coalesce(func.sum(models.Trade.service_fee_attributed), 0).label("sum_service"),
                func.coalesce(func.sum(models.Trade.pnl), 0).label("sum_pnl"),
                func.coalesce(func.sum(models.Trade.net_pnl), 0).label("sum_net_pnl"),
            )
            .join(models.InstrumentORM, models.InstrumentORM.uid == models.Trade.instrument_uid)
            .filter(models.Trade.account_id == aid)
            .group_by(models.InstrumentORM.instrument_type, models.Trade.exit_at.isnot(None))
            .order_by(models.InstrumentORM.instrument_type, models.Trade.exit_at.isnot(None))
            .all()
        )

        print(f"=== Varmargin attribution split by instrument_type / closed для acc#{aid} ===\n")
        print(f"{'type':<12} {'closed?':<8} {'cnt':>6} {'pnl(body)':>14} {'net_pnl':>14} "
              f"{'varmargin':>14} {'margin_fee':>14} {'service_fee':>14}")
        print("-" * 110)
        total_vm = 0.0
        total_vm_shares = 0.0
        total_vm_futures = 0.0
        for r in rows:
            st = "closed" if r.is_closed else "open"
            print(f"{r.instrument_type:<12} {st:<8} {r.cnt:>6} "
                  f"{float(r.sum_pnl):>14,.2f} {float(r.sum_net_pnl):>14,.2f} "
                  f"{float(r.sum_varmargin):>14,.2f} {float(r.sum_margin):>14,.2f} "
                  f"{float(r.sum_service):>14,.2f}")
            total_vm += float(r.sum_varmargin)
            if (r.instrument_type or "").lower() == "share":
                total_vm_shares += float(r.sum_varmargin)
            elif (r.instrument_type or "").lower() == "futures":
                total_vm_futures += float(r.sum_varmargin)
        print("-" * 110)
        print(f"\nTotal varmargin attributed: {total_vm:,.2f} ₽")
        print(f"  to shares (PHANTOM):       {total_vm_shares:,.2f} ₽")
        print(f"  to futures (correct):      {total_vm_futures:,.2f} ₽")
        print(f"  to other (etf/bond/etc):   {total_vm - total_vm_shares - total_vm_futures:,.2f} ₽")
        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

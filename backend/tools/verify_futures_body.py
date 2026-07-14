"""Phase 8 verification (observability): для каждого closed futures trade
проверяет что Trade.pnl ≈ Σ VARMARGIN ops в окне [entry_at, exit_at + 4h]
per-instrument.

Это **observability tool**, не gate. Помогает обнаружить:
  - Tinkoff API edge cases (varmargin attached к figi отличающемуся от trade)
  - Account-level varmargin без instrument_uid
  - Pre-trade history varmargin (не относится ни к одному trade)
  - Регрессии после изменений в FuturesPnLCalculator

Тождество MOEX (доказательство body = Σ varmargin):
  Σ daily_varmargin = Σ (clearing_today − clearing_yesterday) × qty × pv
                    = (last_clearing − entry_clearing) × qty × pv
  плюс финальный post-clearing settlement:
                    + (exit_price − last_clearing) × qty × pv
  ИТОГО:           = (exit_price − entry_price) × qty × pv
                    = Trade.pnl (по Phase 8 formula)

Usage:
    python -X utf8 -m tools.verify_futures_body --account-id 4
"""
from __future__ import annotations
import argparse
import sys
from datetime import timedelta
from decimal import Decimal

import database
import models
from sqlalchemy import and_, or_

from domain.entities import Instrument
from domain.enums import InstrumentType
from domain.pnl.futures import _point_value as futures_point_value


# Окно после exit_at, в котором ловим post-clearing settlement.
# MOEX evening clearing 19:00 МСК → если exit 16:00, settlement через 3h.
POST_CLOSE_CLEARING_WINDOW = timedelta(hours=4)

VARMARGIN_TYPES = ("accruing_varmargin", "writing_off_varmargin")

# Tolerance для матча body vs Σ varmargin.
TOLERANCE_PCT = Decimal("5.0")
TOLERANCE_ABS_RUB = Decimal("100")


def op_amount(op) -> Decimal:
    u = op.payment_units or 0
    n = op.payment_nano or 0
    return Decimal(int(u)) + Decimal(int(n)) / Decimal(1_000_000_000)


def get_point_value(instr_orm) -> Decimal:
    """Compute point_value для futures из ORM record."""
    if not instr_orm:
        return Decimal(1)
    if (instr_orm.instrument_type or "").lower() != "futures":
        return Decimal(1)
    try:
        entity = Instrument(
            uid=instr_orm.uid,
            figi=instr_orm.figi,
            ticker=instr_orm.ticker,
            instrument_type=InstrumentType.FUTURES,
            lot=instr_orm.lot or 1,
            min_price_increment=Decimal(instr_orm.min_price_increment)
            if instr_orm.min_price_increment
            else None,
            min_price_increment_amount=Decimal(instr_orm.min_price_increment_amount)
            if instr_orm.min_price_increment_amount
            else None,
        )
        return futures_point_value(entity)
    except Exception:
        return Decimal(1)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    p.add_argument("--show-all", action="store_true",
                   help="Show all trades, not just outliers")
    args = p.parse_args()
    aid = args.account_id

    s = database.SessionLocal()
    try:
        instruments = {i.uid: i for i in s.query(models.InstrumentORM).all()}

        # Все closed futures trades.
        trades = (
            s.query(models.Trade)
            .filter(
                models.Trade.account_id == aid,
                models.Trade.exit_at.isnot(None),
                models.Trade.instrument_type_v2 == "futures",
            )
            .order_by(models.Trade.entry_at)
            .all()
        )

        if not trades:
            # Fallback: попробовать asset_type column
            trades = (
                s.query(models.Trade)
                .filter(
                    models.Trade.account_id == aid,
                    models.Trade.exit_at.isnot(None),
                    models.Trade.asset_type == "futures",
                )
                .order_by(models.Trade.entry_at)
                .all()
            )

        if not trades:
            print(f"!! Нет closed futures trades для account {aid}")
            return 0

        print(f"=== Phase 8 verify: closed futures body vs Σ varmargin (acc#{aid}) ===")
        print(f"  Tolerance: |diff| <= max({TOLERANCE_ABS_RUB} ₽, {TOLERANCE_PCT}%)")
        print(f"  Post-close window: {POST_CLOSE_CLEARING_WINDOW}")
        print()
        print(f"  {'Ticker':<10} {'Entry':<12} {'Exit':<12} {'Qty':>5} "
              f"{'PV':>6} {'Trade.pnl':>12} {'Σ varmargin':>13} {'Diff ₽':>10} {'%':>6} {'Status':<8}")
        print(f"  {'-'*120}")

        total_body = Decimal(0)
        total_observed = Decimal(0)
        outliers = []

        for tr in trades:
            uid = tr.instrument_uid
            instr = instruments.get(uid) if uid else None
            pv = get_point_value(instr)
            ticker = instr.ticker if instr else (uid or "—")[:10]

            body = Decimal(tr.pnl or 0)
            total_body += body

            # Найти varmargin ops для этого инструмента в окне.
            window_end = tr.exit_at + POST_CLOSE_CLEARING_WINDOW
            window_start = tr.entry_at

            # Match по instrument_uid OR figi (varmargin часто без uid).
            cond = and_(
                models.OperationORM.account_id == aid,
                models.OperationORM.state == "executed",
                models.OperationORM.operation_type.in_(VARMARGIN_TYPES),
                models.OperationORM.executed_at >= window_start,
                models.OperationORM.executed_at <= window_end,
            )
            uid_cond = []
            if uid:
                uid_cond.append(models.OperationORM.instrument_uid == uid)
            if tr.instrument_figi:
                uid_cond.append(models.OperationORM.instrument_figi == tr.instrument_figi)
            if uid_cond:
                cond = and_(cond, or_(*uid_cond))

            vm_ops = (
                s.query(models.OperationORM).filter(cond).all()
            )
            observed = sum((op_amount(o) for o in vm_ops), Decimal(0))
            total_observed += observed

            diff = body - observed
            diff_pct = (
                (abs(diff) / abs(body) * 100) if abs(body) > 1 else Decimal(0)
            )
            status_ok = (
                abs(diff) <= TOLERANCE_ABS_RUB
                or diff_pct <= TOLERANCE_PCT
            )
            status = "OK" if status_ok else "WARN"

            if not status_ok:
                outliers.append((tr, body, observed, diff))

            if args.show_all or not status_ok:
                entry_str = (
                    tr.entry_at.strftime("%Y-%m-%d %H:%M")
                    if tr.entry_at else "—"
                )
                exit_str = (
                    tr.exit_at.strftime("%Y-%m-%d %H:%M")
                    if tr.exit_at else "—"
                )
                print(f"  {ticker:<10} {entry_str:<12} {exit_str:<12} "
                      f"{float(tr.quantity or 0):>5,.0f} {float(pv):>6,.0f} "
                      f"{float(body):>12,.2f} {float(observed):>13,.2f} "
                      f"{float(diff):>10,.2f} {float(diff_pct):>6,.2f} {status:<8}")

        total_diff = total_body - total_observed
        total_pct = (
            abs(total_diff) / abs(total_body) * 100
            if abs(total_body) > 1 else Decimal(0)
        )

        print(f"  {'-'*120}")
        print(f"  {'TOTAL':<10} {'':12} {'':12} {'':>5} {'':>6} "
              f"{float(total_body):>12,.2f} {float(total_observed):>13,.2f} "
              f"{float(total_diff):>10,.2f} {float(total_pct):>6,.2f}")

        print(f"\n  Trades: {len(trades)}, outliers: {len(outliers)}")
        if outliers:
            print(f"  ⚠️  {len(outliers)} closed futures trades с расхождением > tolerance.")
            print(f"      (см. detail выше)")
        else:
            print(f"  ✅ Все closed futures trades within tolerance.")

        # Также покажем varmargin ops, которые НЕ попали ни в одно окно.
        all_vm_ops = (
            s.query(models.OperationORM)
            .filter(
                models.OperationORM.account_id == aid,
                models.OperationORM.state == "executed",
                models.OperationORM.operation_type.in_(VARMARGIN_TYPES),
            )
            .all()
        )
        sum_all_vm = sum((op_amount(o) for o in all_vm_ops), Decimal(0))
        residual = sum_all_vm - total_observed
        print(f"\n  Σ ВСЕХ varmargin ops в БД:         {float(sum_all_vm):>13,.2f} ₽")
        print(f"  Σ matched к closed futures:        {float(total_observed):>13,.2f} ₽")
        print(f"  Residual (open + pre/post-history): {float(residual):>13,.2f} ₽")
        print(f"  ↑ это должно совпасть с (open varmargin_attributed + account_adjustments)")

        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

"""Per-position drill для открытых futures: BUY ops payment, avg_entry, current, Position.unrealized_pnl vs raw cash."""
from __future__ import annotations
import argparse
import sys
from decimal import Decimal

import database
import models
from sqlalchemy import func


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    args = p.parse_args()
    aid = args.account_id

    session = database.SessionLocal()
    try:
        positions = (
            session.query(models.PositionORM)
            .filter(models.PositionORM.account_id == aid, models.PositionORM.quantity != 0)
            .all()
        )
        print(f"=== Open positions ({len(positions)}) для acc#{aid} ===\n")
        for pos in positions:
            instr_info = session.query(models.InstrumentORM).filter(
                models.InstrumentORM.uid == pos.instrument_uid
            ).first()
            ticker = instr_info.ticker if instr_info else pos.instrument_uid[:12]
            print(f"--- {ticker} ({pos.instrument_type}) qty={pos.quantity}")
            print(f"    avg_entry={pos.avg_entry_price}  current={pos.current_price}  unrealized_pnl={pos.unrealized_pnl}")
            # Look up instrument
            instr = session.query(models.InstrumentORM).filter(
                models.InstrumentORM.uid == pos.instrument_uid
            ).first()
            if instr:
                pv_step = instr.min_price_increment
                pv_step_amt = instr.min_price_increment_amount
                pv = "n/a"
                if pv_step and pv_step_amt and float(pv_step) != 0:
                    pv = float(pv_step_amt) / float(pv_step)
                print(f"    instrument.min_price_increment={pv_step}  amount={pv_step_amt}  pv={pv}")
            # BUY operations for this instrument
            buy_ops = (
                session.query(models.OperationORM)
                .filter(
                    models.OperationORM.account_id == aid,
                    models.OperationORM.state == "executed",
                    models.OperationORM.operation_type.in_(["buy", "buy_card", "buy_margin"]),
                    models.OperationORM.instrument_uid == pos.instrument_uid,
                )
                .all()
            )
            sell_ops = (
                session.query(models.OperationORM)
                .filter(
                    models.OperationORM.account_id == aid,
                    models.OperationORM.state == "executed",
                    models.OperationORM.operation_type.in_(["sell", "sell_card", "sell_margin"]),
                    models.OperationORM.instrument_uid == pos.instrument_uid,
                )
                .all()
            )
            def op_total(ops):
                total = Decimal(0)
                qty_total = 0
                for op in ops:
                    u = op.payment_units or 0
                    n = op.payment_nano or 0
                    total += Decimal(int(u)) + Decimal(int(n)) / Decimal(1_000_000_000)
                    qty_total += op.quantity or 0
                return total, qty_total
            buy_pay, buy_qty = op_total(buy_ops)
            sell_pay, sell_qty = op_total(sell_ops)
            print(f"    raw BUYs:  cnt={len(buy_ops):>4}  qty_sum={buy_qty:>6}  payment_sum={float(buy_pay):>16,.2f}")
            print(f"    raw SELLs: cnt={len(sell_ops):>4}  qty_sum={sell_qty:>6}  payment_sum={float(sell_pay):>16,.2f}")
            net_buy_sell = float(buy_pay + sell_pay)
            print(f"    raw net BUY+SELL ops = {net_buy_sell:>14,.2f}")
            # Trade entries for this instrument
            trades = (
                session.query(models.Trade)
                .filter(
                    models.Trade.account_id == aid,
                    models.Trade.instrument_uid == pos.instrument_uid,
                )
                .all()
            )
            open_trades = [t for t in trades if t.exit_at is None]
            closed_trades = [t for t in trades if t.exit_at is not None]
            print(f"    Trade records: total={len(trades)}, open={len(open_trades)}, closed={len(closed_trades)}")
            for t in open_trades:
                print(f"      open trade id={t.id}  qty={t.quantity}  entry={t.entry_price}  varmargin_attr={t.varmargin_attributed}")
            # Position-specific varmargin from ops
            vm_ops = (
                session.query(models.OperationORM)
                .filter(
                    models.OperationORM.account_id == aid,
                    models.OperationORM.state == "executed",
                    models.OperationORM.operation_type.in_(["accruing_varmargin", "writing_off_varmargin"]),
                    models.OperationORM.instrument_uid == pos.instrument_uid,
                )
                .all()
            )
            vm_total, _ = op_total(vm_ops)
            print(f"    varmargin ops with this instrument_uid: cnt={len(vm_ops)}, total={float(vm_total):,.2f}")
            print()
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())

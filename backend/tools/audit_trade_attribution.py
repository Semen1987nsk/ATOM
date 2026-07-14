"""Drill-down: Trade.* attribution разделённый по closed/open + raw operation ops.

Цель — точно понять структуру 91k gap'а на acc#4.
"""
from __future__ import annotations
import argparse
import sys
from decimal import Decimal

import database
import models
from sqlalchemy import func, case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", type=int, required=True)
    args = parser.parse_args()

    aid = args.account_id
    session = database.SessionLocal()
    try:
        # Trade aggregation closed vs open
        is_open = (models.Trade.exit_at.is_(None))
        is_closed = (models.Trade.exit_at.isnot(None))

        def sum_col(col, mask):
            return session.query(
                func.coalesce(func.sum(col), 0)
            ).filter(
                models.Trade.account_id == aid,
                mask,
            ).scalar()

        print(f"=== Trade-level fee attribution для acc#{aid} ===\n")
        print(f"{'Field':<28} {'Closed':>16} {'Open':>16} {'Total':>16}")
        print("-" * 80)
        fields = [
            ("pnl (gross body)", models.Trade.pnl),
            ("commission", models.Trade.commission),
            ("net_pnl", models.Trade.net_pnl),
            ("varmargin_attributed", models.Trade.varmargin_attributed),
            ("margin_fee_attributed", models.Trade.margin_fee_attributed),
            ("service_fee_attributed", models.Trade.service_fee_attributed),
            ("other_fees_attributed", models.Trade.other_fees_attributed),
        ]
        for name, col in fields:
            closed = float(sum_col(col, is_closed))
            opn = float(sum_col(col, is_open))
            total = closed + opn
            print(f"{name:<28} {closed:>16,.2f} {opn:>16,.2f} {total:>16,.2f}")

        # Trades count
        cnt_closed = session.query(func.count(models.Trade.id)).filter(
            models.Trade.account_id == aid, is_closed
        ).scalar()
        cnt_open = session.query(func.count(models.Trade.id)).filter(
            models.Trade.account_id == aid, is_open
        ).scalar()
        print(f"\nTrades count: closed={cnt_closed}, open={cnt_open}")

        # Position aggregation
        unrealized_sum = session.query(
            func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0)
        ).filter(
            models.PositionORM.account_id == aid,
            models.PositionORM.quantity != 0,
        ).scalar()
        pos_count = session.query(func.count(models.PositionORM.id)).filter(
            models.PositionORM.account_id == aid,
            models.PositionORM.quantity != 0,
        ).scalar()
        print(f"\nPositionORM (qty!=0): count={pos_count}, sum(unrealized_pnl)={float(unrealized_sum):,.2f}")

        # Operations: raw payment sums per fee category (sign-preserved)
        print(f"\n=== Raw operations per category ===")
        op_categories = {
            "varmargin (raw)": ["accruing_varmargin", "writing_off_varmargin"],
            "broker_fee (raw)": ["broker_fee"],
            "margin_fee (raw)": ["margin_fee"],
            "service_fee (raw)": ["service_fee"],
            "tax_all (raw)": [
                "tax", "tax_progressive", "benefit_tax", "benefit_tax_progressive",
                "tax_correction", "tax_correction_progressive",
                "tax_repo", "tax_repo_progressive", "tax_repo_hold",
                "tax_repo_hold_progressive", "tax_repo_refund", "tax_repo_refund_progressive",
            ],
            "div_coupon (raw)": [
                "dividend", "dividend_transfer", "dividend_tax", "dividend_tax_progressive",
                "div_ext", "coupon", "bond_repayment", "bond_repayment_full",
                "bond_tax", "bond_tax_progressive", "tax_correction_coupon",
            ],
            "expiration (raw)": ["future_expiration", "option_expiration", "delivery_buy", "delivery_sell"],
            "tracker_fees (raw)": ["track_mfee", "track_pfee", "success_fee", "advice_fee"],
            "cash_fees (raw)": ["cash_fee", "out_fee", "out_stamp_duty", "output_penalty"],
            "overnight (raw)": ["overnight", "over_com", "over_placement", "over_income"],
            "deposits (raw)": [
                "input", "output", "input_swift", "output_swift",
                "input_acquiring", "output_acquiring", "inp_multi", "out_multi",
            ],
            "securities_transfer (raw)": ["input_securities", "output_securities"],
            "internal_transfer (raw)": ["trans_iis_bs", "trans_bs_bs"],
            "trades (raw)": ["buy", "sell", "buy_card", "sell_card", "buy_margin", "sell_margin"],
        }
        for label, types in op_categories.items():
            row = session.query(
                func.count(models.OperationORM.id),
                func.coalesce(func.sum(models.OperationORM.payment_units), 0),
                func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
            ).filter(
                models.OperationORM.account_id == aid,
                models.OperationORM.state == "executed",
                models.OperationORM.operation_type.in_(types),
            ).one()
            cnt, u, n = row
            amount = float(Decimal(int(u or 0)) + Decimal(int(n or 0)) / Decimal(1_000_000_000))
            if cnt > 0:
                print(f"  {label:<32} cnt={cnt:>5}  Σ={amount:>14,.2f} ₽")

        # Acc.last_portfolio_value
        acc = session.get(models.Account, aid)
        print(f"\nAccount.last_portfolio_value = {float(acc.last_portfolio_value or 0):,.2f} ₽")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())

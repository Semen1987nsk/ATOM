"""Sanity-check: Σ journal P&L vs cash truth.

Формула:
    Journal P&L = Σ Trade.net_pnl (closed)
                + Σ PositionORM.unrealized_pnl (open positions)
                + Σ open Trade.{margin_fee, service_fee, other}_attributed

    Cash truth  = current_portfolio_value − net_deposits
                  где net_deposits = Σ payment ∀ ops в категории NET_DEPOSIT.

    Diff = Journal − Cash → должен быть ~0.

Diff > 1% или > 1000₽ обычно означает:
- Pre-sync account state (был открытый портфель ДО подключения Tinkoff) →
  использовать --baseline-date + --initial-portfolio-value
- Missing operations в sync (cursor пропустил period) → re-sync
- Bug в attribution → drill в orphans report

В отличие от первой версии (2026-05-15):
- Использует `domain.pnl.cash_flow_classification.CASH_FLOW_MAP` —
  единый source-of-truth, ВСЕ deposit channels включая SWIFT/acquiring/multi.
- Journal_pnl расширен на open trade attribution для шарных позиций
  (closed trades' net_pnl уже включает attribution; для open varmargin
  не суммируется т.к. он уже в Position.unrealized_pnl).
- Per-category breakdown (видно структуру cash flow).
- Orphans report — какие cash flows не попали ни в одну Trade/Position.
- Flags --baseline-date, --initial-portfolio-value — для аккаунтов
  с pre-sync state.

Usage:
    python -X utf8 -m tools.reconcile_journal_vs_cash --user-id 2
    python -X utf8 -m tools.reconcile_journal_vs_cash --account-id 4
    python -X utf8 -m tools.reconcile_journal_vs_cash --account-id 4 \
        --baseline-date 2025-12-01 --initial-portfolio-value 50000

Exit codes: 0 = match (diff < 5%, см. THRESHOLD_OK_PCT), 1 = significant diff, 2 = error
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from decimal import Decimal

import database
import models
from sqlalchemy import func
from sqlalchemy.orm import Session

from domain.pnl.cash_flow_classification import (
    CASH_FLOW_MAP,
    CashFlowCategory,
    operation_types_in,
)

# MATH-09: единый источник правды по порогам — pnl_health_service.
# Re-export под локальными именами (THRESHOLD_WARN_PCT — псевдоним сервисного
# THRESHOLD_WARNING_PCT) чтобы CLI tool и API возвращали одинаковые статусы.
from services.pnl_health_service import (
    THRESHOLD_OK_PCT,
    THRESHOLD_WARNING_PCT as THRESHOLD_WARN_PCT,
)

log = logging.getLogger("reconcile_journal_vs_cash")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")


def _payment_sum_for(
    session,
    *,
    account_id: int,
    op_types: set[str],
    from_dt: datetime | None,
) -> Decimal:
    """SUM(payment) по списку operation_types с опциональным after-cursor."""
    if not op_types:
        return Decimal(0)
    q = session.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.in_(tuple(op_types)),
    )
    if from_dt is not None:
        q = q.filter(models.OperationORM.executed_at >= from_dt)
    u, n = q.one()
    return Decimal(int(u or 0)) + Decimal(int(n or 0)) / Decimal(1_000_000_000)


def _category_breakdown(session, *, account_id: int, from_dt: datetime | None) -> dict[CashFlowCategory, Decimal]:
    """Возвращает Σ payment по каждой категории."""
    result: dict[CashFlowCategory, Decimal] = {}
    for category in CashFlowCategory:
        op_types = operation_types_in(category)
        if not op_types:
            continue
        result[category] = _payment_sum_for(
            session, account_id=account_id, op_types=op_types, from_dt=from_dt,
        )
    return result


def reconcile_account(
    account_id: int,
    *,
    baseline_date: datetime | None = None,
    initial_portfolio_value: Decimal | None = None,
    session: Session | None = None,
) -> dict:
    """Сверка одного аккаунта. Returns dict с metrics + diff."""
    _owned = session is None
    if _owned:
        session = database.SessionLocal()
    try:
        account = session.get(models.Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")

        # 1. Journal-side: closed Trade.net_pnl + Position.unrealized_pnl
        #    + open Trade attribution (margin/service/other; НЕ varmargin —
        #    он уже в Position.unrealized_pnl для futures).
        realized_q = (
            session.query(func.coalesce(func.sum(models.Trade.net_pnl), 0))
            .filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.isnot(None),
            )
        )
        if baseline_date is not None:
            realized_q = realized_q.filter(models.Trade.exit_at >= baseline_date)
        realized = Decimal(realized_q.scalar() or 0)

        unrealized_sum = (
            session.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0))
            .filter(
                models.PositionORM.account_id == account_id,
                models.PositionORM.quantity != 0,
            )
            .scalar()
        )
        unrealized = Decimal(unrealized_sum or 0)

        # Open trade attribution: margin/service/other (not varmargin which
        # is captured via Position.unrealized_pnl for futures).
        open_margin_fee = Decimal(
            session.query(func.coalesce(func.sum(models.Trade.margin_fee_attributed), 0))
            .filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.is_(None),
            )
            .scalar() or 0
        )
        open_service_fee = Decimal(
            session.query(func.coalesce(func.sum(models.Trade.service_fee_attributed), 0))
            .filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.is_(None),
            )
            .scalar() or 0
        )
        open_other_fees = Decimal(
            session.query(func.coalesce(func.sum(models.Trade.other_fees_attributed), 0))
            .filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.is_(None),
            )
            .scalar() or 0
        )
        open_attribution = open_margin_fee + open_service_fee + open_other_fees

        journal_pnl = realized + unrealized + open_attribution

        # 2. Cash truth: current_portfolio - net_deposits (− pre-sync baseline if any)
        current_portfolio = Decimal(account.last_portfolio_value or 0)

        net_deposit_types = operation_types_in(CashFlowCategory.NET_DEPOSIT)
        net_deposits = _payment_sum_for(
            session,
            account_id=account_id,
            op_types=net_deposit_types,
            from_dt=baseline_date,
        )

        # При --baseline-date считаем cash_pnl как
        # current_portfolio - net_deposits_since_baseline - initial_portfolio_value
        # т.е. дельта portfolio за период минус приход денег за период.
        baseline_offset = Decimal(0)
        if baseline_date is not None and initial_portfolio_value is not None:
            baseline_offset = Decimal(initial_portfolio_value)

        # ADR-0010: opening-balance anchor — эффективная база депозитов в all-time режиме.
        # В baseline-режиме (--baseline-date) НЕ применяем, чтобы не двоить с baseline_offset.
        anchor = Decimal(account.initial_balance or 0) if baseline_date is None else Decimal(0)
        cash_pnl = current_portfolio - net_deposits - anchor - baseline_offset

        # 3. Diff
        diff = journal_pnl - cash_pnl
        if abs(cash_pnl) > 1:
            diff_pct = abs(diff) / abs(cash_pnl) * 100
        else:
            diff_pct = Decimal(0) if abs(diff) < 1 else Decimal(100)

        # 4. Category breakdown (для понимания структуры cash flow)
        breakdown = _category_breakdown(session, account_id=account_id, from_dt=baseline_date)

        # 5. Fees breakdown (attributed, closed + open)
        def trade_sum(col, only_closed: bool = False) -> Decimal:
            q = session.query(func.coalesce(func.sum(col), 0)).filter(
                models.Trade.account_id == account_id
            )
            if only_closed:
                q = q.filter(models.Trade.exit_at.isnot(None))
            return Decimal(q.scalar() or 0)

        fees = {
            "commission_closed": trade_sum(models.Trade.commission, only_closed=True),
            "varmargin_all": trade_sum(models.Trade.varmargin_attributed),
            "varmargin_closed": Decimal(
                session.query(func.coalesce(func.sum(models.Trade.varmargin_attributed), 0))
                .filter(
                    models.Trade.account_id == account_id,
                    models.Trade.exit_at.isnot(None),
                ).scalar() or 0
            ),
            "margin_fee_all": trade_sum(models.Trade.margin_fee_attributed),
            "service_fee_all": trade_sum(models.Trade.service_fee_attributed),
            "other_fees_all": trade_sum(models.Trade.other_fees_attributed),
        }

        # 6. Orphans: для VARMARGIN/ATTRIBUTABLE_FEE/TAX/INCOME сравниваем
        # raw category sum vs attributed sum. Разница = orphan (не попал в trade).
        raw_varmargin = breakdown.get(CashFlowCategory.VARMARGIN, Decimal(0))
        raw_attr_fee = breakdown.get(CashFlowCategory.ATTRIBUTABLE_FEE, Decimal(0))
        raw_tax = breakdown.get(CashFlowCategory.TAX, Decimal(0))
        raw_income = breakdown.get(CashFlowCategory.INCOME, Decimal(0))
        raw_income_tax = breakdown.get(CashFlowCategory.INCOME_TAX, Decimal(0))

        # Attribution categories sum: margin_fee + service_fee + part of other
        # (other_fees_attributed агрегирует tax). Income не attributed (orphan
        # пока не введём income_attributed column; см. plan Phase 3c).
        attributed_attr_fee = fees["margin_fee_all"] + fees["service_fee_all"]
        attributed_tax = fees["other_fees_all"]

        orphans = {
            "varmargin": raw_varmargin - fees["varmargin_all"],
            "attributable_fee": raw_attr_fee - attributed_attr_fee,
            "tax": raw_tax - attributed_tax,
            "income": raw_income,  # пока полностью orphan
            "income_tax": raw_income_tax,  # пока полностью orphan
            "broker_commission_extra": breakdown.get(CashFlowCategory.BROKER_COMMISSION, Decimal(0))
                                       + fees["commission_closed"],
            # Trade.commission stored as positive abs; raw broker_fee is negative.
            # Sum = orphan-ish (если 0 → совпадают).
            "unknown_category": breakdown.get(CashFlowCategory.UNKNOWN, Decimal(0)),
        }

        return {
            "account_id": account_id,
            "account_name": account.name,
            "baseline_date": baseline_date.isoformat() if baseline_date else None,
            "initial_portfolio_value": float(baseline_offset),
            "journal": {
                "realized": float(realized),
                "unrealized": float(unrealized),
                "open_attribution": float(open_attribution),
                "total": float(journal_pnl),
            },
            "cash": {
                "current_portfolio": float(current_portfolio),
                "net_deposits": float(net_deposits),
                "initial_balance": float(anchor),
                "baseline_offset": float(baseline_offset),
                "total": float(cash_pnl),
            },
            "diff": {
                "abs": float(diff),
                "pct": float(diff_pct),
            },
            "fees_breakdown": {k: float(v) for k, v in fees.items()},
            "category_breakdown": {cat.value: float(amt) for cat, amt in breakdown.items()},
            "orphans": {k: float(v) for k, v in orphans.items()},
        }
    finally:
        if _owned:
            session.close()


def print_result(result: dict) -> int:
    print()
    name = result["account_name"]
    print(f"=== Reconciliation: account #{result['account_id']} ({name}) ===")
    if result.get("baseline_date"):
        print(f"Baseline: {result['baseline_date']}  initial_portfolio={result['initial_portfolio_value']:,.2f} ₽")

    j = result["journal"]
    c = result["cash"]
    d = result["diff"]
    f = result["fees_breakdown"]
    cat = result["category_breakdown"]
    orph = result["orphans"]

    print(f"\n[Journal P&L]")
    print(f"  Σ Trade.net_pnl закрытых:       {j['realized']:>16,.2f} ₽")
    print(f"  Σ unrealized_pnl открытых:      {j['unrealized']:>16,.2f} ₽")
    print(f"  Σ open attribution (mg/sv/ot):  {j['open_attribution']:>16,.2f} ₽")
    print(f"  Total journal:                  {j['total']:>16,.2f} ₽")

    print(f"\n[Cash truth]")
    print(f"  current_portfolio:              {c['current_portfolio']:>16,.2f} ₽")
    print(f"  − net deposits:                 {c['net_deposits']:>16,.2f} ₽")
    if c.get("initial_balance"):
        print(f"  − opening anchor (ADR-0010):    {c['initial_balance']:>16,.2f} ₽")
    if c["baseline_offset"]:
        print(f"  − initial_portfolio_value:      {c['baseline_offset']:>16,.2f} ₽")
    print(f"  = cash P&L:                     {c['total']:>16,.2f} ₽")

    print(f"\n[Diff]")
    print(f"  journal - cash:                 {d['abs']:>16,.2f} ₽  ({d['pct']:.2f}%)")
    print(f"  clearing_adjustment (cash-journal): {-d['abs']:>16,.2f} ₽  ← неразложимая фьюч. вармаржа")

    print(f"\n[Fees breakdown (attributed)]")
    print(f"  Commission (closed, abs):       {f['commission_closed']:>16,.2f} ₽")
    print(f"  Varmargin all (closed+open):    {f['varmargin_all']:>16,.2f} ₽")
    print(f"  Varmargin closed (in net_pnl):  {f['varmargin_closed']:>16,.2f} ₽")
    print(f"  Margin fee all:                 {f['margin_fee_all']:>16,.2f} ₽")
    print(f"  Service fee all:                {f['service_fee_all']:>16,.2f} ₽")
    print(f"  Other (tax) all:                {f['other_fees_all']:>16,.2f} ₽")

    print(f"\n[Cash flow categories]")
    for cat_name, amt in cat.items():
        if abs(amt) > 0.01:
            print(f"  {cat_name:<24} {amt:>16,.2f} ₽")

    print(f"\n[Orphans (cash flows не попавшие в Trade attribution)]")
    has_orphan = False
    for k, v in orph.items():
        if abs(v) > 1.0:
            has_orphan = True
            print(f"  {k:<24} {v:>16,.2f} ₽")
    if not has_orphan:
        print(f"  (нет значимых orphans)")

    # Status — пороги синхронизированы с pnl_health_service (MATH-09).
    ok_pct = float(THRESHOLD_OK_PCT)
    warn_pct = float(THRESHOLD_WARN_PCT)
    if abs(d["abs"]) < 100 or d["pct"] < ok_pct:
        print(f"\n✅ MATCH (diff < 100₽ или < {ok_pct:g}%)")
        return 0
    elif d["pct"] < warn_pct:
        print(f"\n⚠️  WARN — diff {d['pct']:.1f}% / {d['abs']:,.0f}₽ "
              f"(в полосе {ok_pct:g}–{warn_pct:g}%, проверь pre-sync state)")
        return 1
    else:
        print(f"\n❌ MISMATCH — diff {d['pct']:.1f}% / {d['abs']:,.0f}₽ "
              f"(≥{warn_pct:g}%, требует investigation)")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile journal P&L vs cash truth")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account-id", type=int, help="Single account")
    group.add_argument("--user-id", type=int, help="All accounts of user")
    parser.add_argument(
        "--baseline-date",
        type=str,
        help="ISO date (YYYY-MM-DD) с которой считается P&L. Используй для аккаунтов "
             "с pre-sync state. Все ops до этой даты исключаются из journal/cash.",
    )
    parser.add_argument(
        "--initial-portfolio-value",
        type=float,
        help="Portfolio value на baseline-date (если известен из broker_report). "
             "Учитывается в cash_pnl как 'starting capital'.",
    )
    args = parser.parse_args()

    baseline_date: datetime | None = None
    if args.baseline_date:
        baseline_date = datetime.strptime(args.baseline_date, "%Y-%m-%d")
    initial_pv = Decimal(args.initial_portfolio_value) if args.initial_portfolio_value else None

    session = database.SessionLocal()
    try:
        if args.account_id is not None:
            account_ids = [args.account_id]
        else:
            account_ids = [
                a.id for a in
                session.query(models.Account).filter(models.Account.user_id == args.user_id).all()
            ]
            if not account_ids:
                log.error(f"No accounts for user_id={args.user_id}")
                return 2
    finally:
        session.close()

    overall_exit = 0
    for aid in account_ids:
        try:
            result = reconcile_account(
                aid,
                baseline_date=baseline_date,
                initial_portfolio_value=initial_pv,
            )
            exit_code = print_result(result)
            if exit_code > overall_exit:
                overall_exit = exit_code
        except Exception:
            log.exception(f"Failed to reconcile account_id={aid}")
            overall_exit = 2

    return overall_exit


if __name__ == "__main__":
    sys.exit(main())

"""Detailed list of orphan cash flows — operations not attributed to any Trade.

Цель: показать пользователю прозрачно ОТКУДА в его P&L взялись orphan
cash flows (варм-маржа без active futures, лишние комиссии, options и т.п.).
По каждой операции — дата, инструмент, сумма, причина почему orphan.

Usage:
    python -X utf8 -m tools.audit_orphans_detail --account-id 4
"""
from __future__ import annotations
import argparse
import sys
from decimal import Decimal
from datetime import datetime, timedelta

import database
import models
from sqlalchemy import func, and_, or_

from domain.pnl.cash_flow_classification import (
    CashFlowCategory,
    classify,
    operation_types_in,
)


def fetch_ops_in_category(s, account_id: int, category: CashFlowCategory):
    types = tuple(operation_types_in(category))
    if not types:
        return []
    return (
        s.query(models.OperationORM)
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.state == "executed",
            models.OperationORM.operation_type.in_(types),
        )
        .order_by(models.OperationORM.executed_at)
        .all()
    )


def has_active_trade_at(s, account_id: int, at: datetime, *, instrument_type: str = None) -> int:
    """Сколько active trades было у юзера в момент `at`."""
    q = s.query(func.count(models.Trade.id)).filter(
        models.Trade.account_id == account_id,
        models.Trade.entry_at <= at,
        or_(
            models.Trade.exit_at.is_(None),
            models.Trade.exit_at >= at,
        ),
    )
    if instrument_type:
        q = q.join(
            models.InstrumentORM,
            models.InstrumentORM.uid == models.Trade.instrument_uid,
        ).filter(models.InstrumentORM.instrument_type == instrument_type)
    return q.scalar() or 0


def find_nearest_trade(s, account_id: int, at: datetime, *, instrument_type: str = None):
    """Найти ближайший trade (по времени entry_at или exit_at) для контекста."""
    q = s.query(models.Trade).filter(models.Trade.account_id == account_id)
    if instrument_type:
        q = q.join(
            models.InstrumentORM,
            models.InstrumentORM.uid == models.Trade.instrument_uid,
        ).filter(models.InstrumentORM.instrument_type == instrument_type)
    trades = q.all()
    if not trades:
        return None
    nearest = None
    nearest_delta = timedelta(days=365 * 10)
    for t in trades:
        if t.entry_at:
            d = abs(at - t.entry_at)
            if d < nearest_delta:
                nearest_delta = d
                nearest = ("entry", t, d)
        if t.exit_at:
            d = abs(at - t.exit_at)
            if d < nearest_delta:
                nearest_delta = d
                nearest = ("exit", t, d)
    return nearest


def op_amount(op) -> Decimal:
    u = op.payment_units or 0
    n = op.payment_nano or 0
    return Decimal(int(u)) + Decimal(int(n)) / Decimal(1_000_000_000)


def is_op_attributed(s, op) -> bool:
    """Грубая проверка: попала ли операция в attribution.

    Не идеальная — точное соответствие надо смотреть в pipeline.
    Здесь возвращаем True если был active trade подходящего типа.
    """
    if classify(op.operation_type) == CashFlowCategory.VARMARGIN:
        # Varmargin attribute только к futures (Phase 3c)
        return has_active_trade_at(
            s, op.account_id, op.executed_at, instrument_type="futures"
        ) > 0
    return has_active_trade_at(s, op.account_id, op.executed_at) > 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    p.add_argument("--category", type=str, default="all",
                   help="all | varmargin | attributable_fee | tax | income | broker_commission")
    args = p.parse_args()
    aid = args.account_id

    s = database.SessionLocal()
    try:
        instruments = {i.uid: i for i in s.query(models.InstrumentORM).all()}

        categories = (
            [args.category.upper()]
            if args.category != "all"
            else ["VARMARGIN", "ATTRIBUTABLE_FEE", "INCOME", "BROKER_COMMISSION"]
        )

        for cat_name in categories:
            cat = CashFlowCategory[cat_name] if hasattr(CashFlowCategory, cat_name) else None
            if cat is None:
                print(f"!! Unknown category {cat_name}")
                continue

            ops = fetch_ops_in_category(s, aid, cat)
            if not ops:
                continue

            print(f"\n{'='*100}")
            print(f"=== {cat.value.upper()} ({len(ops)} операций) ===")
            print(f"{'='*100}")

            orphans = []
            attributed = []
            total_raw = Decimal(0)
            total_orphan = Decimal(0)

            for op in ops:
                amt = op_amount(op)
                total_raw += amt
                if not is_op_attributed(s, op):
                    orphans.append((op, amt))
                    total_orphan += amt
                else:
                    attributed.append((op, amt))

            print(f"\nВсего по категории: {len(ops)} ops, Σ = {float(total_raw):,.2f} ₽")
            print(f"  Attributed (привязано к trade): {len(attributed)} ops")
            print(f"  Orphan (НЕ привязано):          {len(orphans)} ops, Σ = {float(total_orphan):,.2f} ₽")

            if not orphans:
                print(f"\n  Все операции этой категории успешно привязаны к trades.")
                continue

            # Группируем orphans по дате (день)
            by_day = {}
            for op, amt in orphans:
                day = op.executed_at.date() if op.executed_at else "unknown"
                if day not in by_day:
                    by_day[day] = []
                by_day[day].append((op, amt))

            print(f"\n  Orphan операции (top-30 по сумме):")
            print(f"  {'Дата':<12} {'Время':<10} {'Тип':<25} {'Тикер':<10} {'Сумма ₽':>12}  Причина")
            print(f"  {'-'*120}")

            # Сортируем по абсолютной сумме (top losers/gainers первыми)
            sorted_orphans = sorted(orphans, key=lambda x: abs(x[1]), reverse=True)[:30]
            for op, amt in sorted_orphans:
                date = op.executed_at.date().isoformat() if op.executed_at else "—"
                time = op.executed_at.strftime("%H:%M:%S") if op.executed_at else "—"
                ticker = "—"
                if op.instrument_uid:
                    instr = instruments.get(op.instrument_uid)
                    if instr:
                        ticker = instr.ticker or instr.uid[:8]
                    else:
                        ticker = op.instrument_uid[:8]

                # Reason: найдём ближайший trade
                nearest = None
                if cat == CashFlowCategory.VARMARGIN:
                    nearest = find_nearest_trade(s, aid, op.executed_at, instrument_type="futures")
                else:
                    nearest = find_nearest_trade(s, aid, op.executed_at)

                if nearest:
                    side, t, delta = nearest
                    delta_str = (
                        f"{delta.total_seconds()/3600:.1f}ч" if delta < timedelta(days=1)
                        else f"{delta.days}д"
                    )
                    near_instr = instruments.get(t.instrument_uid)
                    near_tk = near_instr.ticker if near_instr else t.instrument_uid[:8]
                    reason = f"нет active trade; ближайший {side} {near_tk} за {delta_str} до/после"
                else:
                    reason = "нет ни одного trade в системе"

                print(f"  {date:<12} {time:<10} {op.operation_type:<25} {ticker:<10} "
                      f"{float(amt):>12,.2f}  {reason}")

            # Сводка по дням
            print(f"\n  Сводка по дням ({len(by_day)} дней с orphan-операциями):")
            print(f"  {'Дата':<12} {'Ops':>5} {'Σ ₽':>14}")
            for day in sorted(by_day.keys(), key=lambda d: sum(abs(a) for _, a in by_day[d]), reverse=True)[:15]:
                day_ops = by_day[day]
                day_sum = sum(amt for _, amt in day_ops)
                print(f"  {str(day):<12} {len(day_ops):>5} {float(day_sum):>14,.2f}")

        return 0
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

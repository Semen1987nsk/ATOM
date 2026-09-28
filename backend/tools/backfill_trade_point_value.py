"""Phase 9.4 (2026-05-17): backfill Trade.point_value для existing closed futures.

Algorithm per closed futures trade:
  1. Найти первую BUY или SELL OperationORM для trade.instrument_uid (matched
     to trade by op time being within [entry_at, exit_at]).
  2. Empirical pv = |payment_value| / (qty × price_value) per Tinkoff convention
     для futures: payment ≈ qty × price × point_value.
  3. Сравнить с InstrumentORM.min_price_increment_amount/min_price_increment
     (cached pv):
     - Если совпадают в пределах 5% → use cache, source='cache' (trust API)
     - Если расходятся > 5% AND empirical seems reasonable → use empirical,
       source='empirical_payment'
     - Если qty или price = 0 → skip + log warning, source=None
  4. UPDATE Trade.point_value, Trade.point_value_source.

Validated on acc#4 (live API discovery, Phase 9.0):
  - PSU5/GLM6/S0M6/TIZ4: empirical ≈ cache pv ✓
  - BBZ4/DXH5/ETU5/BBH5: empirical correctly расходится с cache, гораздо меньше
  - Active XIM6/ETM6: empirical ≈ cache pv ✓

Usage:
    python -X utf8 -m tools.backfill_trade_point_value --account-id 4
    python -X utf8 -m tools.backfill_trade_point_value --account-id 4 --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal

import database
import models
from sqlalchemy import and_

log = logging.getLogger("backfill_point_value")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)

EMPIRICAL_VS_CACHE_TOLERANCE = Decimal("0.05")  # 5%


def op_payment(op) -> Decimal:
    units = op.payment_units or 0
    nano = op.payment_nano or 0
    return Decimal(int(units)) + Decimal(int(nano)) / Decimal(1_000_000_000)


def op_price(op) -> Decimal:
    units = op.price_units or 0
    nano = op.price_nano or 0
    return Decimal(int(units)) + Decimal(int(nano)) / Decimal(1_000_000_000)


def cached_pv(instr: models.InstrumentORM) -> Decimal | None:
    if not instr:
        return None
    if not instr.min_price_increment or instr.min_price_increment == 0:
        return None
    if instr.min_price_increment_amount is None:
        return None
    return Decimal(instr.min_price_increment_amount) / Decimal(instr.min_price_increment)


def find_representative_op(
    session, account_id: int, instrument_uid: str, entry_at, exit_at
) -> models.OperationORM | None:
    """Найти BUY или SELL op в окне [entry_at, exit_at] для данного uid.

    Берём ПЕРВУЮ операцию в окне — обычно это entry side. Empirical pv
    инвариантен относительно entry vs exit (price ratio с payment).
    """
    q = session.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.instrument_uid == instrument_uid,
        models.OperationORM.operation_type.in_(("buy", "sell")),
        models.OperationORM.state == "executed",
    )
    if entry_at:
        q = q.filter(models.OperationORM.executed_at >= entry_at)
    if exit_at:
        q = q.filter(models.OperationORM.executed_at <= exit_at)
    return q.order_by(models.OperationORM.executed_at).first()


def empirical_pv(op: models.OperationORM) -> Decimal | None:
    """pv = |payment| / (qty × price). Для futures BUY/SELL это эквивалентно
    point_value по соглашению Tinkoff (payment = qty × price × pv)."""
    if not op:
        return None
    qty = Decimal(int(op.quantity or 0))
    price = op_price(op)
    payment = op_payment(op)
    if qty == 0 or price == 0:
        return None
    return abs(payment) / (qty * price)


def decide_pv(
    cache_pv: Decimal | None, emp_pv: Decimal | None
) -> tuple[Decimal | None, str | None]:
    """Decision tree:
    - empirical нет → use cache
    - empirical есть и совпадает с cache (±5%) → use cache (API truth)
    - empirical есть и расходится с cache → use empirical
    - empirical есть, cache нет → use empirical
    """
    if emp_pv is None:
        if cache_pv is None:
            return None, None
        return cache_pv, "cache"
    if cache_pv is None or cache_pv == 0:
        return emp_pv, "empirical_payment"
    drift = abs(emp_pv - cache_pv) / cache_pv
    if drift <= EMPIRICAL_VS_CACHE_TOLERANCE:
        return cache_pv, "cache"
    return emp_pv, "empirical_payment"


def backfill_account(account_id: int, dry_run: bool = False) -> dict:
    """Возвращает stats dict."""
    session = database.SessionLocal()
    try:
        rows = (
            session.query(models.Trade)
            .join(
                models.InstrumentORM,
                models.InstrumentORM.uid == models.Trade.instrument_uid,
            )
            .filter(
                models.Trade.account_id == account_id,
                models.InstrumentORM.instrument_type == "futures",
            )
            .all()
        )

        instr_cache = {
            i.uid: i
            for i in session.query(models.InstrumentORM)
            .filter(
                models.InstrumentORM.uid.in_({r.instrument_uid for r in rows if r.instrument_uid})
            )
            .all()
        }

        stats = {
            "total_futures_trades": len(rows),
            "updated": 0,
            "skipped_no_op": 0,
            "skipped_zero_price_or_qty": 0,
            "source_cache": 0,
            "source_empirical": 0,
            "source_none": 0,
            "drift_examples": [],
        }

        for tr in rows:
            instr = instr_cache.get(tr.instrument_uid)
            cache_pv = cached_pv(instr)
            op = find_representative_op(
                session, account_id, tr.instrument_uid, tr.entry_at, tr.exit_at
            )
            if not op:
                stats["skipped_no_op"] += 1
                continue
            emp = empirical_pv(op)
            if emp is None:
                stats["skipped_zero_price_or_qty"] += 1
                continue

            new_pv, source = decide_pv(cache_pv, emp)
            if new_pv is None or source is None:
                stats["source_none"] += 1
                continue

            # Track examples of significant drift
            if cache_pv and cache_pv > 0:
                drift = abs(emp - cache_pv) / cache_pv
                if drift > Decimal("0.2") and len(stats["drift_examples"]) < 10:
                    stats["drift_examples"].append({
                        "ticker": instr.ticker if instr else "?",
                        "trade_id": tr.id,
                        "cache_pv": float(cache_pv),
                        "empirical_pv": float(emp),
                        "chosen_pv": float(new_pv),
                        "chosen_source": source,
                    })

            if not dry_run:
                tr.point_value = new_pv
                tr.point_value_source = source

            stats["updated"] += 1
            if source == "cache":
                stats["source_cache"] += 1
            elif source == "empirical_payment":
                stats["source_empirical"] += 1

        if not dry_run:
            session.commit()
        return stats
    finally:
        session.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="Show stats без UPDATE в БД")
    args = p.parse_args()

    log.info(f"Phase 9.4 backfill для account_id={args.account_id} dry_run={args.dry_run}")
    stats = backfill_account(args.account_id, dry_run=args.dry_run)

    log.info(f"  Total futures trades:     {stats['total_futures_trades']}")
    log.info(f"  Updated:                  {stats['updated']}")
    log.info(f"  Skipped (no buy/sell op): {stats['skipped_no_op']}")
    log.info(f"  Skipped (zero qty/price): {stats['skipped_zero_price_or_qty']}")
    log.info(f"  Source = cache (trust):   {stats['source_cache']}")
    log.info(f"  Source = empirical:       {stats['source_empirical']}")
    if stats["drift_examples"]:
        log.info(f"  Drift examples (cache vs empirical, top 10):")
        for ex in stats["drift_examples"]:
            log.info(
                f"    {ex['ticker']:<10} trade#{ex['trade_id']}: cache={ex['cache_pv']:>10.3f} "
                f"empirical={ex['empirical_pv']:>10.3f} → chosen={ex['chosen_pv']:>10.3f} "
                f"({ex['chosen_source']})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

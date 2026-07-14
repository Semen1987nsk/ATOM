"""Phase 6 cleanup (2026-05-17): обнулить Trade.pnl для closed futures.

После изменения FuturesPnLCalculator.compute() → body=0 существующие
Trade rows в БД содержат старый body (full-notional payment) — это
double-count с varmargin_attributed. Этот скрипт обновляет существующие
row's Trade.pnl=0 для closed futures + вызывает attribution stage
для пересчёта Trade.net_pnl с правильной формулой.

Usage:
    python -X utf8 -m tools.reset_closed_futures_body --account-id 4
    python -X utf8 -m tools.reset_closed_futures_body --user-id 2

Idempotent: повторный запуск не меняет числа (Trade.pnl уже = 0).

Опция --preserve-old-pnl сохраняет старые значения в Trade.extra['pnl_pre_phase6']
для пользователей которые уже выгрузили P&L tax-отчёт со старыми числами.
"""
from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal

import database
import models

log = logging.getLogger("reset_closed_futures_body")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")


def reset_account(account_id: int, *, preserve_old: bool = False) -> int:
    """Возвращает количество обновлённых Trade rows."""
    session = database.SessionLocal()
    try:
        # Find closed futures Trade rows. JOIN InstrumentORM для filter по type.
        rows = (
            session.query(models.Trade)
            .join(
                models.InstrumentORM,
                models.InstrumentORM.uid == models.Trade.instrument_uid,
            )
            .filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.isnot(None),
                models.InstrumentORM.instrument_type == "futures",
            )
            .all()
        )

        log.info(f"acc#{account_id}: найдено {len(rows)} closed futures trades")
        if not rows:
            return 0

        # Sanity: считаем суммарный pnl до сброса
        old_pnl_sum = sum((Decimal(r.pnl or 0) for r in rows), Decimal(0))
        log.info(f"  Σ Trade.pnl (closed futures, ДО): {old_pnl_sum:,.2f} ₽")

        updated = 0
        for r in rows:
            if preserve_old and r.pnl is not None and r.pnl != Decimal(0):
                extra = dict(r.extra or {})
                extra.setdefault("pnl_pre_phase6", str(r.pnl))
                r.extra = extra
            r.pnl = Decimal(0)
            updated += 1
        session.commit()
        log.info(f"  Updated {updated} rows: Trade.pnl=0")
        return updated
    finally:
        session.close()


def reattribute_account(account_id: int) -> None:
    """Запускает _stage_attribute_fees для пересчёта Trade.net_pnl."""
    from application.sync.pipeline import SyncPipeline

    pipeline = SyncPipeline.__new__(SyncPipeline)
    pipeline._account_id = account_id
    pipeline._session_factory = database.SessionLocal
    pipeline._stage_attribute_fees()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset closed futures Trade.pnl=0 (Phase 6)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account-id", type=int, help="Single account")
    group.add_argument("--user-id", type=int, help="All accounts of user")
    parser.add_argument(
        "--preserve-old-pnl",
        action="store_true",
        help="Сохранить старые Trade.pnl в Trade.extra['pnl_pre_phase6'] "
             "для P&L tax-отчётов уже выгруженных в прошлом.",
    )
    args = parser.parse_args()

    session = database.SessionLocal()
    try:
        if args.account_id is not None:
            account_ids = [args.account_id]
        else:
            account_ids = [
                a.id
                for a in session.query(models.Account)
                .filter(models.Account.user_id == args.user_id)
                .all()
            ]
            if not account_ids:
                log.error(f"No accounts for user_id={args.user_id}")
                return 2
    finally:
        session.close()

    total_updated = 0
    for aid in account_ids:
        try:
            n = reset_account(aid, preserve_old=args.preserve_old_pnl)
            total_updated += n
            if n > 0:
                log.info(f"acc#{aid}: запускаю re-attribution stage...")
                reattribute_account(aid)
                log.info(f"acc#{aid}: re-attribution done")
        except Exception:
            log.exception(f"Failed acc#{aid}")
            return 2

    log.info(f"Phase 6 cleanup done. Total trades updated: {total_updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

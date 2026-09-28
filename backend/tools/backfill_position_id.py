"""TR1: Backfill position_id + TR1.3: fee attribution для existing trades.

Forced-sync обрабатывает только delta инструментов из текущего cursor batch.
Чтобы position_id попал на ВСЕ existing trades (374 row'ов в БД на acc#4),
нужно прогнать FIFO matcher по каждому уникальному (account_id, instrument_uid)
с полным набором операций — replace strategy сама уберёт старые и положит
новые с position_id.

Также запускает TR1.3 fee attribution stage (varmargin, margin_fee, etc.)
после FIFO replay — закрывает gap «journal P&L vs cash truth».

Usage:
    python -X utf8 -m tools.backfill_position_id --account-id 4

Idempotent: повторный запуск ничего не сломает (replace-стратегия)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

import database
import models
from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.persistence.operation_repo import OperationRepository
from adapters.persistence.position_repo import PositionRepository
from adapters.persistence.trade_repo import TradeRepository
from application.fifo_matching import FIFOMatchingService

log = logging.getLogger("backfill_position_id")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)


def backfill_account(account_id: int) -> dict:
    """Прогнать FIFO matcher по всем instruments аккаунта.

    Returns: dict с counters {instruments_processed, trades_replaced}.
    """
    fifo = FIFOMatchingService()
    instrument_repo = InstrumentRepository()
    operation_repo = OperationRepository()
    trade_repo = TradeRepository()

    instruments_processed = 0
    trades_replaced = 0

    # Получаем все уникальные instrument_uid из operations для аккаунта.
    session = database.SessionLocal()
    try:
        uids = (
            session.query(models.OperationORM.instrument_uid)
            .filter(models.OperationORM.account_id == account_id)
            .filter(models.OperationORM.instrument_uid.isnot(None))
            .distinct()
            .all()
        )
        unique_uids = [u[0] for u in uids if u[0]]
        log.info(f"acc#{account_id}: found {len(unique_uids)} unique instruments")
    finally:
        session.close()

    # Для каждого instrument: load ops → FIFO match → replace.
    for uid in unique_uids:
        session = database.SessionLocal()
        try:
            instrument = instrument_repo.get_by_uid(session, uid)
            if instrument is None:
                log.warning(f"  skip {uid}: instrument not in cache")
                continue

            all_ops = operation_repo.fetch_for_instrument(
                session,
                account_id=account_id,
                instrument_uid=uid,
            )
            if not all_ops:
                continue

            result = fifo.match(
                account_id=account_id,
                instrument=instrument,
                operations=all_ops,
                existing_open_lots=(),
            )
            open_trades = FIFOMatchingService.open_trades_from_lots(
                lots=result.open_lots,
                instrument=instrument,
                account_id=account_id,
            )
            n = trade_repo.replace_for_instrument(
                session,
                account_id=account_id,
                instrument_uid=uid,
                trades=list(result.closed_trades) + open_trades,
                instrument=instrument,
            )
            session.commit()
            instruments_processed += 1
            trades_replaced += n
            log.info(
                f"  {instrument.ticker or uid[:12]:15s} "
                f"closed={len(result.closed_trades):3d}  "
                f"open={len(open_trades):2d}  total={n}"
            )
        except Exception:
            session.rollback()
            log.exception(f"  FAIL {uid}")
        finally:
            session.close()

    return {
        "instruments_processed": instruments_processed,
        "trades_replaced": trades_replaced,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill position_id via FIFO replay")
    parser.add_argument("--account-id", type=int, required=True)
    args = parser.parse_args()

    log.info(f"Starting backfill for account_id={args.account_id}")
    stats = backfill_account(args.account_id)
    log.info(f"Done: {stats}")

    # TR1.3: запуск fee attribution stage после FIFO replay.
    log.info("Running TR1.3 fee attribution stage...")
    from application.sync.pipeline import SyncPipeline
    # Создаём минимальный pipeline только для _stage_attribute_fees.
    # Нужны session_factory + account_id; остальные deps не используются.
    pipeline = SyncPipeline.__new__(SyncPipeline)
    pipeline._session_factory = database.SessionLocal
    pipeline._account_id = args.account_id
    pipeline._stage_attribute_fees()
    log.info("Fee attribution done.")

    # Verify final state
    session = database.SessionLocal()
    try:
        total = (
            session.query(models.Trade)
            .filter(models.Trade.account_id == args.account_id)
            .count()
        )
        with_pid = (
            session.query(models.Trade)
            .filter(
                models.Trade.account_id == args.account_id,
                models.Trade.position_id.isnot(None),
            )
            .count()
        )
        log.info(f"Final: {with_pid}/{total} trades have position_id")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

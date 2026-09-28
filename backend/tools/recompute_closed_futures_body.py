"""Phase 8 one-off (2026-05-17): пересчитать Trade.pnl и Trade.net_pnl
для closed futures одного аккаунта используя formula:

    Trade.pnl = (exit_price − entry_price) × quantity_signed × point_value

Это math identity с MOEX variation margin telescoping sum (включая
post-clearing settlements ПОСЛЕ exit_at). После recompute orphan
varmargin от MOEX post-exit settlements исчезает архитектурно —
он уже учтён в Trade.pnl.

Scope: ОДИН account_id (по решению user 2026-05-17 — точечный rollout
до verify, multi-account rollout отдельно).

Алгоритм:
  1. Find все closed futures Trade rows для account_id
  2. Для каждого:
     - point_value = min_price_increment_amount / min_price_increment
     - sign = +1 для LONG, −1 для SHORT
     - body = (exit_price − entry_price) × quantity × point_value × sign
     - Trade.pnl = body
     - Trade.varmargin_attributed = 0 (теперь в body)
  3. Запустить _stage_attribute_fees для пересчёта Trade.net_pnl
     по правильной формуле (Phase 8.2 skip-VARMARGIN-for-closed).

Usage:
    python -X utf8 -m tools.recompute_closed_futures_body --account-id 4

Idempotent: повторный запуск даёт те же числа.
"""
from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal

import database
import models
from domain.entities import Instrument
from domain.enums import InstrumentType
from domain.pnl.futures import _point_value as futures_point_value

log = logging.getLogger("recompute_closed_futures_body")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)


def _point_value_for_orm(instr_orm) -> Decimal:
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


def recompute_account(account_id: int) -> int:
    """Возвращает количество обновлённых Trade rows."""
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
                models.Trade.exit_at.isnot(None),
                models.InstrumentORM.instrument_type == "futures",
            )
            .all()
        )

        log.info(f"acc#{account_id}: найдено {len(rows)} closed futures trades")
        if not rows:
            return 0

        # Build instrument cache (uid → ORM).
        uids = {r.instrument_uid for r in rows if r.instrument_uid}
        instruments = {
            i.uid: i
            for i in session.query(models.InstrumentORM)
            .filter(models.InstrumentORM.uid.in_(uids))
            .all()
        }

        old_pnl_sum = sum((Decimal(r.pnl or 0) for r in rows), Decimal(0))
        log.info(f"  Σ Trade.pnl (closed futures, ДО): {old_pnl_sum:,.2f} ₽")

        updated = 0
        skipped_no_pv = 0
        new_pnl_sum = Decimal(0)
        for r in rows:
            instr = instruments.get(r.instrument_uid) if r.instrument_uid else None
            # Phase 9: prefer Trade.point_value snapshot (backfilled by
            # tools.backfill_trade_point_value); fallback to InstrumentORM cache.
            if r.point_value is not None and Decimal(r.point_value) > 0:
                pv = Decimal(r.point_value)
            else:
                pv = _point_value_for_orm(instr)
                if pv == 0 or pv is None:
                    skipped_no_pv += 1
                    continue
            qty = Decimal(r.quantity or 0)
            entry_price = Decimal(r.entry_price or 0)
            exit_price = Decimal(r.exit_price or 0)
            direction = (
                r.direction.value if hasattr(r.direction, "value") else str(r.direction)
            ).lower()
            sign = Decimal(1) if direction == "long" else Decimal(-1)

            body = (exit_price - entry_price) * qty * pv * sign
            r.pnl = body
            # Phase 8: varmargin для closed с pnl != 0 будет skip'нута в
            # fee_attribution.py (Phase 8.2 conditional). Reset существующую
            # attribution; rerun_attribution_only stage ниже её не вернёт.
            r.varmargin_attributed = Decimal(0)
            new_pnl_sum += body
            updated += 1
        if skipped_no_pv:
            log.warning(f"  Skipped {skipped_no_pv} trades без надёжного pv (NULL Trade.point_value AND NULL cache)")

        session.commit()
        log.info(f"  Σ Trade.pnl (closed futures, ПОСЛЕ): {new_pnl_sum:,.2f} ₽")
        log.info(f"  Updated {updated} rows")
        return updated
    finally:
        session.close()


def reattribute_account(account_id: int) -> None:
    """Запускает _stage_attribute_fees для пересчёта Trade.net_pnl
    (Phase 8.2 теперь skip VARMARGIN для closed → margin_fee/service_fee/other
    re-applied поверх нового pnl)."""
    from application.sync.pipeline import SyncPipeline

    pipeline = SyncPipeline.__new__(SyncPipeline)
    pipeline._account_id = account_id
    pipeline._session_factory = database.SessionLocal
    pipeline._stage_attribute_fees()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 8 one-off recompute Trade.pnl=(exit−entry)×qty×pv "
                    "for closed futures of ONE account"
    )
    parser.add_argument(
        "--account-id",
        type=int,
        required=True,
        help="Account ID для recompute. Multi-account rollout — отдельно "
             "после verify на pilot account.",
    )
    args = parser.parse_args()

    aid = args.account_id

    try:
        n = recompute_account(aid)
        if n > 0:
            log.info(f"acc#{aid}: запускаю re-attribution stage...")
            reattribute_account(aid)
            log.info(f"acc#{aid}: re-attribution done")
        log.info(f"Phase 8 recompute done. Trades updated: {n}")
        return 0
    except Exception:
        log.exception(f"Failed acc#{aid}")
        return 2


if __name__ == "__main__":
    sys.exit(main())

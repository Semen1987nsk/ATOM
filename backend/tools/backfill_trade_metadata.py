"""
Backfill Trade metadata — заполняет asset_name и holding_time_minutes у
существующих sync-сделок одной командой, без re-sync.

ЦЕЛЬ: после введения колонок в `_trade_to_orm` (PR 19), все сделки
синхронизированные ДО фикса остаются с asset_name=NULL и
holding_time_minutes=NULL. Полный re-sync долгий (~12 сек), а тут чисто
точечное обновление двух полей — JOIN с instruments + расчёт дельты дат.

ИСПОЛЬЗОВАНИЕ:

    cd backend
    python -m tools.backfill_trade_metadata --account-id 4

    # или для всех аккаунтов
    python -m tools.backfill_trade_metadata --all

ЧТО ДЕЛАЕТ:
1. Находит все Trade с data_source='tinkoff_v2' где asset_name IS NULL ИЛИ
   holding_time_minutes IS NULL.
2. Для каждой: JOIN-loop с InstrumentORM по instrument_uid; берёт
   InstrumentORM.name.
3. Если есть exit_at и entry_at: holding_time_minutes = int((exit-entry)/60).
4. UPDATE.
"""

from __future__ import annotations

import argparse
import sys

from database import SessionLocal
from logger import get_logger
from models import InstrumentORM, Trade

log = get_logger("backfill_trade_metadata")


def backfill_account(account_id: int | None) -> dict[str, int]:
    """
    account_id=None → все аккаунты.
    Возвращает счётчики обновлённых полей.
    """
    session = SessionLocal()
    try:
        query = session.query(Trade).filter(Trade.data_source == "tinkoff_v2")
        if account_id is not None:
            query = query.filter(Trade.account_id == account_id)
        # Только те где хотя бы одно поле NULL — экономим работу.
        query = query.filter(
            (Trade.asset_name.is_(None)) | (Trade.holding_time_minutes.is_(None))
        )
        rows = query.all()

        # Закэшируем InstrumentORM в dict per uid — один запрос вместо N.
        uids = list({r.instrument_uid for r in rows if r.instrument_uid})
        instruments: dict[str, str | None] = {}
        if uids:
            instr_rows = (
                session.query(InstrumentORM.uid, InstrumentORM.name)
                .filter(InstrumentORM.uid.in_(uids))
                .all()
            )
            instruments = {uid: name for uid, name in instr_rows}

        names_filled = 0
        holdings_filled = 0
        for t in rows:
            # asset_name
            if t.asset_name is None and t.instrument_uid in instruments:
                name = instruments[t.instrument_uid]
                if name:
                    t.asset_name = name
                    names_filled += 1
            # holding_time_minutes
            if t.holding_time_minutes is None and t.exit_at and t.entry_at:
                delta_sec = (t.exit_at - t.entry_at).total_seconds()
                if delta_sec >= 0:
                    t.holding_time_minutes = int(delta_sec / 60)
                    holdings_filled += 1

        session.commit()
        result = {
            "rows_examined": len(rows),
            "asset_names_filled": names_filled,
            "holding_times_filled": holdings_filled,
        }
        log.info("Backfill: %s", result)
        return result
    except Exception:
        session.rollback()
        log.exception("Backfill failed")
        raise
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill asset_name + holding_time_minutes in trades."
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--account-id", type=int, help="Account ID to backfill")
    g.add_argument("--all", action="store_true", help="Backfill all accounts")
    args = parser.parse_args()

    aid = None if args.all else args.account_id
    result = backfill_account(aid)
    print(
        f"OK: backfill done.\n"
        f"  rows examined: {result['rows_examined']}\n"
        f"  asset_names filled: {result['asset_names_filled']}\n"
        f"  holding_times filled: {result['holding_times_filled']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

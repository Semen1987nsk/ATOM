"""
One-off cleanup for stale autosync trades.

По умолчанию запускается в dry-run режиме и только печатает stale autosync-записи,
которые больше не соответствуют канонической перегруппировке операций брокера.

Использование:
    cd backend
    python cleanup_stale_autosync.py
    python cleanup_stale_autosync.py --apply
    python cleanup_stale_autosync.py --from-date 2025-10-20
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from crypto_utils import decrypt_token
from database import SessionLocal
from models import BrokerConnection, Trade
from tinkoff_service import TinkoffService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run/apply cleanup for stale autosync trades")
    parser.add_argument("--apply", action="store_true", help="Delete stale autosync trades instead of dry-run")
    parser.add_argument(
        "--from-date",
        type=str,
        help="History start date in YYYY-MM-DD format. Default: earliest autosync entry_at - 1 day",
    )
    return parser.parse_args()


def _resolve_from_date(session, arg_value: str | None) -> datetime:
    if arg_value:
        return datetime.fromisoformat(arg_value)

    autosync_trades = session.query(Trade).all()
    autosync_dates = [
        trade.entry_at
        for trade in autosync_trades
        if "#autosync" in (trade.tags or []) and trade.entry_at is not None
    ]
    if not autosync_dates:
        return datetime(2020, 1, 1)
    return min(autosync_dates) - timedelta(days=1)


def main() -> int:
    args = _parse_args()
    db = SessionLocal()

    try:
        connection = db.query(BrokerConnection).filter(BrokerConnection.is_active == True).first()
        if connection is None:
            print("No active broker connection found")
            return 1

        from_date = _resolve_from_date(db, args.from_date)
        service = TinkoffService(decrypt_token(connection.api_token))
        operations = service.get_operations(connection.broker_account_id, from_date, datetime.utcnow())
        closed_trades, open_positions = service._build_trades_fifo(operations)

        try:
            portfolio = service.get_portfolio(connection.broker_account_id)
            broker_open_symbols = service._extract_broker_open_symbols(portfolio)
            open_positions = service._filter_open_positions_by_broker_portfolio(open_positions, broker_open_symbols)
        except Exception as exc:
            print(f"Warning: portfolio reconciliation skipped: {exc}")

        canonical_signatures = service._build_canonical_trade_signatures(closed_trades, open_positions)

        touched_symbols = sorted(canonical_signatures.keys())
        candidates = db.query(Trade).filter(
            Trade.account_id == connection.account_id,
            Trade.symbol.in_(touched_symbols),
            Trade.entry_at != None,  # noqa: E711
            Trade.entry_at >= from_date,
        ).all()

        stale_trades = []
        for trade in candidates:
            if "#autosync" not in (trade.tags or []):
                continue

            signature = (
                "LONG" if trade.direction.value == "long" else "SHORT",
                trade.exit_at is not None,
                service._normalize_operation_signature(trade.operations),
            )
            if signature in canonical_signatures.get(trade.symbol, set()):
                continue
            stale_trades.append(trade)

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[{mode}] from_date={from_date.isoformat()} canonical_symbols={len(canonical_signatures)} stale={len(stale_trades)}")
        for trade in stale_trades:
            print(
                f"STALE id={trade.id} symbol={trade.symbol} dir={trade.direction.value} "
                f"entry={trade.entry_at} exit={trade.exit_at} qty={trade.quantity} pnl={trade.pnl}"
            )

        if args.apply and stale_trades:
            for trade in stale_trades:
                db.delete(trade)
            db.commit()
            print(f"Deleted {len(stale_trades)} stale autosync trades")
        elif not args.apply:
            print("Dry-run only; no DB changes applied")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
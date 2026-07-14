"""
Diagnose Account — CLI для саппорта и dev'а.

ЦЕЛЬ: пользователь жалуется «у меня не сошлось», админ запускает одну
команду и за 5 секунд видит:
  - последний health-status (ok/warning/error)
  - историю health-чеков за 7 дней
  - сверку DB-позиций с live Tinkoff
  - последние операции (24ч)
  - top trades по абсолютному pnl_pct (аномалии)

ИСПОЛЬЗОВАНИЕ:

    cd backend
    python -m tools.diagnose_account --account-id 4
    python -m tools.diagnose_account --account-id 4 --history-days 14
    python -m tools.diagnose_account --account-id 4 --no-live  # без вызова Tinkoff API
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from typing import Optional

from database import SessionLocal
from models import (
    BrokerConnection,
    InstrumentORM,
    OperationORM,
    PositionORM,
    SyncHealthCheckORM,
    Trade,
)
from utils.datetime_utils import utc_now_naive

STATUS_ICON = {"ok": "🟢", "warning": "🟡", "error": "🔴"}


def _print_header(title: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}\n{title}\n{bar}")


def _print_last_sync(session, account_id: int) -> Optional[BrokerConnection]:
    conn = (
        session.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account_id)
        .first()
    )
    if not conn:
        print("  ❌ No BrokerConnection")
        return None
    print(f"  broker_account_id: {conn.broker_account_id}")
    print(f"  last_sync_at:      {conn.last_sync_at}")
    print(f"  last_sync_status:  {conn.last_sync_status}")
    print(f"  consecutive_failures: {conn.consecutive_failures}")
    print(f"  circuit_open_until: {conn.circuit_open_until}")
    print(f"  ops_count: {conn.last_sync_operations_count}  trades: {conn.last_sync_trades_count}  positions: {conn.last_sync_positions_count}  dur: {conn.last_sync_duration_ms}ms")
    return conn


def _print_health_history(session, account_id: int, days: int) -> None:
    threshold = utc_now_naive() - timedelta(days=days)
    rows = (
        session.query(SyncHealthCheckORM)
        .filter(
            SyncHealthCheckORM.account_id == account_id,
            SyncHealthCheckORM.checked_at >= threshold,
        )
        .order_by(SyncHealthCheckORM.checked_at.desc())
        .limit(20)
        .all()
    )
    if not rows:
        print(f"  Нет health-проверок за {days} дней.")
        return
    for r in rows:
        icon = STATUS_ICON.get(r.status, "•")
        issues = r.issues_json or []
        issue_str = ""
        if issues:
            top = issues[0]
            issue_str = f" — {top['check_id']} ({top['severity']}, ×{top['count']})"
        print(
            f"  {icon} {r.checked_at}  status={r.status}  "
            f"trades={r.total_trades_checked}  with_issues={r.trades_with_issues}{issue_str}"
        )


def _print_latest_issues_detail(session, account_id: int) -> None:
    latest = (
        session.query(SyncHealthCheckORM)
        .filter(SyncHealthCheckORM.account_id == account_id)
        .order_by(SyncHealthCheckORM.checked_at.desc())
        .first()
    )
    if not latest or not latest.issues_json:
        print("  ✅ Нет проблем в последнем audit'е.")
        return
    for i in latest.issues_json:
        print(f"  [{i['severity']:7}] {i['check_id']:38} ×{i['count']:>4}  {i.get('description','')}")
        if i.get("sample_ids"):
            print(f"            sample_ids: {i['sample_ids'][:5]}")


def _print_db_positions(session, account_id: int) -> list[tuple[str, int]]:
    rows = (
        session.query(PositionORM, InstrumentORM)
        .outerjoin(InstrumentORM, InstrumentORM.uid == PositionORM.instrument_uid)
        .filter(PositionORM.account_id == account_id)
        .all()
    )
    pairs: list[tuple[str, int]] = []
    for pos, instr in rows:
        ticker = (instr.ticker if instr else pos.instrument_uid[:8]) or "?"
        pairs.append((ticker, pos.quantity))
    pairs.sort()
    for ticker, qty in pairs:
        print(f"  {ticker:10}  qty={qty:>6}")
    return pairs


async def _print_live_positions(token: str, broker_account_id: str, session) -> list[tuple[str, int]]:
    from adapters.tinkoff.client_factory import client_factory
    from adapters.tinkoff.operations_client import TinkoffOperationsClient

    async with client_factory.async_client(token) as services:
        ops = TinkoffOperationsClient(services)
        raw = await ops.get_portfolio_raw(broker_account_id)

    pairs: list[tuple[str, int]] = []
    for p in getattr(raw, "positions", []):
        qty_obj = getattr(p, "quantity", None)
        if qty_obj is None:
            continue
        q = (qty_obj.units or 0)
        if q == 0:
            continue
        itype = getattr(p, "instrument_type", "")
        if itype == "currency":
            continue  # cash-баланс не считаем позицией
        uid = getattr(p, "instrument_uid", None)
        instr = (
            session.query(InstrumentORM)
            .filter(InstrumentORM.uid == uid)
            .first()
            if uid
            else None
        )
        ticker = (instr.ticker if instr else (uid or "?")[:8]) or "?"
        pairs.append((ticker, q))
    pairs.sort()
    for ticker, qty in pairs:
        print(f"  {ticker:10}  qty={qty:>6}")
    return pairs


def _print_position_diff(db: list[tuple[str, int]], live: list[tuple[str, int]]) -> None:
    db_map = dict(db)
    live_map = dict(live)
    all_tickers = sorted(set(db_map) | set(live_map))
    diffs = []
    for tk in all_tickers:
        d = db_map.get(tk, 0)
        l = live_map.get(tk, 0)
        if d != l:
            diffs.append((tk, d, l))
    if not diffs:
        print("  ✅ MATCH: локальные позиции совпадают с Tinkoff live")
    else:
        print(f"  ❌ DIFF в {len(diffs)} тикерах:")
        for tk, d, l in diffs:
            print(f"     {tk:10}  DB={d}  Live={l}")


def _print_recent_operations(session, account_id: int, hours: int = 24) -> None:
    threshold = utc_now_naive() - timedelta(hours=hours)
    rows = (
        session.query(OperationORM, InstrumentORM)
        .outerjoin(InstrumentORM, InstrumentORM.uid == OperationORM.instrument_uid)
        .filter(
            OperationORM.account_id == account_id,
            OperationORM.executed_at >= threshold,
        )
        .order_by(OperationORM.executed_at.desc())
        .limit(15)
        .all()
    )
    if not rows:
        print(f"  Нет операций за последние {hours}ч.")
        return
    for op, instr in rows:
        ticker = (instr.ticker if instr else "—") or "—"
        pay = (op.payment_units or 0) + (op.payment_nano or 0) / 1e9
        print(
            f"  {op.executed_at}  {op.operation_type:25}  {ticker:10}  "
            f"qty={op.quantity:>4}  payment={pay:>12.2f}  state={op.state}"
        )


def _print_top_anomalies(session, account_id: int) -> None:
    """5 сделок с самым большим |pnl_pct| — кандидаты на ручной разбор."""
    rows = (
        session.query(Trade)
        .filter(
            Trade.account_id == account_id,
            Trade.data_source == "tinkoff_v2",
            Trade.exit_at.isnot(None),
            Trade.entry_value.isnot(None),
            Trade.pnl.isnot(None),
        )
        .all()
    )
    scored = []
    for t in rows:
        ev = float(t.entry_value)
        if ev <= 0:
            continue
        pct = abs(float(t.pnl) / ev * 100)
        scored.append((pct, t))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        print("  Нет сделок с computed pnl_pct.")
        return
    for pct, t in scored[:5]:
        print(
            f"  #{t.id}  {t.symbol:10}  pnl={float(t.pnl):>12.2f}  "
            f"entry_value={float(t.entry_value):>12.2f}  pnl_pct={pct:>7.2f}%"
        )


async def main_async(args) -> int:
    session = SessionLocal()
    try:
        _print_header(f"ACCOUNT {args.account_id} — DIAGNOSTIC REPORT")
        _print_header("1. Last sync (BrokerConnection)")
        conn = _print_last_sync(session, args.account_id)

        _print_header(f"2. Health audit history (last {args.history_days} days)")
        _print_health_history(session, args.account_id, args.history_days)

        _print_header("3. Latest audit — detail")
        _print_latest_issues_detail(session, args.account_id)

        _print_header("4. DB positions")
        db_pos = _print_db_positions(session, args.account_id)

        if not args.no_live and conn:
            from adapters.persistence.token_repo import TokenRepository
            from adapters.security.token_encryption import TokenEncryptionService

            try:
                enc = TokenEncryptionService()
                tr = TokenRepository(encryption=enc)
                token = tr.get_decrypted(
                    session,
                    account_id=args.account_id,
                    broker_account_id=conn.broker_account_id,
                )
                if token:
                    _print_header("5. Live Tinkoff positions")
                    live_pos = await _print_live_positions(
                        token, conn.broker_account_id, session
                    )
                    _print_header("6. Position diff (DB vs Live)")
                    _print_position_diff(db_pos, live_pos)
                else:
                    print("\n  ⚠️ Token недоступен — пропускаю live-сверку")
            except Exception as exc:
                print(f"\n  ⚠️ Live-сверка не удалась: {type(exc).__name__}: {exc}")

        _print_header(f"7. Recent operations (last 24h)")
        _print_recent_operations(session, args.account_id, hours=24)

        _print_header("8. Top 5 trades by abs(pnl_pct)")
        _print_top_anomalies(session, args.account_id)

        print()
        return 0
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose one account's Tinkoff import state."
    )
    parser.add_argument("--account-id", type=int, required=True)
    parser.add_argument("--history-days", type=int, default=7)
    parser.add_argument(
        "--no-live", action="store_true", help="Skip live Tinkoff API check"
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

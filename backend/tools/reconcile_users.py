"""
PR 26 (Phase 3, D8) — Reconciliation CLI tool.

Запускает 3-way reconciliation для одного юзера или всех. Используется в:
- nightly cron (scripts/reconcile_users_cron.sh)
- ad-hoc support: «проверить корректность данных юзера X»
- pre-launch validation: baseline correctness baseline

Сверяет 8 финансовых метрик (P&L, commissions, dividends, NDFL, cash flow)
наших агрегатов с broker report Tinkoff. Плюс 4 invariants + transformation
audit (T1-T8).

Usage:
    python -m tools.reconcile_users --user-id 42
    python -m tools.reconcile_users --user-id 42 --days 7 --json out.json
    python -m tools.reconcile_users --all-users --since-days 30
    python -m tools.reconcile_users --all-users --no-broker --json /tmp/recon.json

Exit codes:
    0 — все проверки ok
    1 — warnings (soft breaks)
    2 — hard breaks (важно для cron + Slack alert)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _supports_color() -> bool:
    try:
        return sys.stdout.isatty() and not (
            sys.platform == "win32" and "TERM" not in os.environ
        )
    except Exception:
        return False


_USE_COLOR = _supports_color()


def _color(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(s: str) -> str:
    return _color(s, "32")


def _yellow(s: str) -> str:
    return _color(s, "33")


def _red(s: str) -> str:
    return _color(s, "31")


def _gray(s: str) -> str:
    return _color(s, "90")


STATUS_COLORS = {
    "ok": _green,
    "warning": _yellow,
    "break": _red,
    "error": _red,
}


def _format_status(status: str) -> str:
    fn = STATUS_COLORS.get(status, lambda x: x)
    return fn(status.upper())


async def _run_for_user(
    db, user_id: int, *, days: int, skip_broker_report: bool, persist: bool,
) -> tuple[list[dict], int]:
    """Запустить reconciliation для всех аккаунтов юзера.

    Возвращает (results_dicts, max_exit_code).
    """
    import models
    from services.reconciliation_service import (
        reconcile_account,
        persist_reconciliation_run,
    )
    from utils.datetime_utils import utc_now_naive

    accounts = db.query(models.Account).filter_by(user_id=user_id).all()
    if not accounts:
        return [], 0

    period_end = utc_now_naive()
    period_start = period_end - timedelta(days=days)

    results = []
    max_exit = 0
    for acc in accounts:
        try:
            result = await reconcile_account(
                db,
                acc.id,
                period_start=period_start,
                period_end=period_end,
                fetch_broker_report=not skip_broker_report,
                trigger="nightly_cron",
            )
            if persist:
                persist_reconciliation_run(db, result, trigger="nightly_cron")
            results.append(result.to_dict())
            if result.status == "break":
                max_exit = max(max_exit, 2)
            elif result.status == "warning":
                max_exit = max(max_exit, 1)
            elif result.status == "error":
                max_exit = max(max_exit, 2)
        except Exception as exc:
            results.append({
                "account_id": acc.id,
                "user_id": user_id,
                "status": "error",
                "error": str(exc),
            })
            max_exit = max(max_exit, 2)
    return results, max_exit


def _print_user_summary(user_id: int, email: str | None, results: list[dict]) -> None:
    print()
    print(_gray("─" * 70))
    print(f"User {user_id} ({email or 'n/a'})")
    print(_gray("─" * 70))
    for r in results:
        status = r.get("status", "unknown")
        print(f"  Account {r.get('account_id')}: {_format_status(status)}", end="")
        breaks = r.get("breaks_count", 0)
        if breaks:
            print(f"  breaks={breaks}", end="")
        warns = len(r.get("transformation_warnings", []) or [])
        if warns:
            print(f"  audit={warns}", end="")
        if r.get("error_message") or r.get("error"):
            msg = r.get("error_message") or r.get("error")
            print(f"  err={msg}", end="")
        print()
        # Show metrics with non-ok status
        for m in r.get("metrics", []) or []:
            if m.get("status") in {"soft", "hard"}:
                metric = m.get("metric", "")
                ours = m.get("ours", "?")
                broker = m.get("broker", "?")
                diff = m.get("diff_abs", "?")
                colored_status = _format_status(m.get("status", "ok"))
                print(f"      {colored_status}  {metric}: ours={ours} broker={broker} diff={diff}")
        # Show transformation warnings
        for w in r.get("transformation_warnings", []) or []:
            sev = w.get("severity", "low")
            color = _red if sev == "critical" else _yellow
            print(f"      {color('[' + w.get('code', '?') + ']')}  {w.get('description', '')[:80]}")


async def _main_async(args: argparse.Namespace) -> int:
    import database
    import models

    db = next(database.get_db())
    try:
        if args.all_users:
            users = db.query(models.User).filter_by(is_active=1).all()
        elif args.user_id:
            users = db.query(models.User).filter_by(id=args.user_id).all()
            if not users:
                print(f"User {args.user_id} not found", file=sys.stderr)
                return 2
        else:
            print("Specify --user-id or --all-users", file=sys.stderr)
            return 2

        all_results = []
        max_exit = 0
        for u in users:
            results, exit_code = await _run_for_user(
                db,
                u.id,
                days=args.days,
                skip_broker_report=args.no_broker,
                persist=not args.no_persist,
            )
            _print_user_summary(u.id, u.email, results)
            all_results.append({
                "user_id": u.id,
                "email_present": bool(u.email),
                "results": results,
            })
            max_exit = max(max_exit, exit_code)

        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"\nJSON saved to {args.json}")

        # Slack webhook alert
        if args.slack_webhook and max_exit >= 2:
            _slack_alert(args.slack_webhook, all_results)

        return max_exit
    finally:
        db.close()


def _slack_alert(webhook_url: str, results: list[dict]) -> None:
    """Шлёт alert в Slack если есть hard breaks."""
    import urllib.request
    import urllib.error

    breaks_lines = []
    for entry in results:
        for r in entry.get("results", []):
            if r.get("status") in {"break", "error"}:
                ms = []
                for m in r.get("metrics", []) or []:
                    if m.get("status") == "hard":
                        ms.append(f"{m.get('metric')}: diff={m.get('diff_abs')}")
                breaks_lines.append(
                    f"• user={entry.get('user_id')} acc={r.get('account_id')} "
                    f"status={r.get('status')} {'; '.join(ms[:3])}"
                )
    if not breaks_lines:
        return
    text = (
        f":rotating_light: *Reconciliation alert* — {len(breaks_lines)} hard breaks\n"
        + "\n".join(breaks_lines[:20])
    )
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"Slack alert failed: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="3-way reconciliation for users")
    grp = parser.add_mutually_exclusive_group(required=False)
    grp.add_argument("--user-id", type=int, help="Reconcile one user")
    grp.add_argument("--all-users", action="store_true", help="Reconcile all active users")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Period length in days (default 30)",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        dest="days",
        help="Alias for --days (for backward compat)",
    )
    parser.add_argument(
        "--no-broker",
        action="store_true",
        help="Skip broker report fetch (invariants + audit only)",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Don't write ReconciliationRunORM to DB (dry-run)",
    )
    parser.add_argument("--json", type=str, help="Save JSON output to file")
    parser.add_argument(
        "--slack-webhook",
        type=str,
        default=os.environ.get("SLACK_WEBHOOK"),
        help="Slack webhook URL for break alerts (or set SLACK_WEBHOOK env)",
    )
    args = parser.parse_args()

    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())

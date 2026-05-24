"""
PR 26 — Verify user CLI.

Запускает 12 проверок (см. services/verify_service.py) для одного юзера
или всех. Используется для:

* Ad-hoc support: «у юзера X что-то не так — что именно?»
* Nightly cron: проверка всех аккаунтов на отклонения DB↔Tinkoff↔UI.
* Pre-launch acceptance: фиксация baseline корректности.

Usage:
    python -m tools.verify_user --user-id 42
    python -m tools.verify_user --user-id 42 --account-id 7 --json out.json
    python -m tools.verify_user --user-id 42 --no-live
    python -m tools.verify_user --all-users [--max-concurrency 3]

Exit codes:
    0 — все проверки ok
    1 — есть warnings, но errors нет
    2 — есть errors (важно для cron + Slack alert)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional


# Чтобы можно было запускать как `python -m tools.verify_user` ИЛИ как
# `python tools/verify_user.py`, добавляем backend root в sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ANSI цвета — отключаем под Windows если не TTY.
def _supports_color() -> bool:
    try:
        return sys.stdout.isatty() and not (
            sys.platform == "win32" and "TERM" not in __import__("os").environ
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


def _bold(s: str) -> str:
    return _color(s, "1")


def _status_str(status: str) -> str:
    if status == "ok":
        return _green("[OK   ]")
    if status == "warning":
        return _yellow("[WARN ]")
    return _red("[ERROR]")


def _print_report(report) -> None:
    print(_bold(f"\n=== Verify user_id={report.user_id} ==="))
    if not report.accounts:
        print(_yellow("  no accounts found"))
        return

    for acc in report.accounts:
        title = f"Account #{acc.account_id}"
        if acc.broker_account_id:
            title += f" (Tinkoff brk{acc.broker_account_id})"
        print(f"\n{title}: {_status_str(acc.status)}")
        for c in acc.checks:
            line = f"  {_status_str(c.status)} {c.check_id}"
            if c.message:
                line += f" — {c.message}"
            print(line)

    s = report.summary()
    print(_bold(f"\nSummary: ok={s['ok']} warn={s['warning']} err={s['error']}"))


async def _run_for_user(user_id: int, *, account_id: Optional[int], skip_live: bool):
    import database
    from services.verify_service import verify_user

    db = database.SessionLocal()
    try:
        report = await verify_user(
            db,
            user_id=user_id,
            account_id=account_id,
            skip_live=skip_live,
        )
        return report
    finally:
        db.close()


async def _run_for_all(*, max_concurrency: int, skip_live: bool):
    import database
    import models
    from services.verify_service import verify_user

    db = database.SessionLocal()
    try:
        users = db.query(models.User).filter(models.User.is_active == 1).all()
    finally:
        db.close()

    sem = asyncio.Semaphore(max_concurrency)

    async def _process(u_id: int):
        async with sem:
            db_local = database.SessionLocal()
            try:
                return await verify_user(db_local, user_id=u_id, skip_live=skip_live)
            finally:
                db_local.close()

    reports = await asyncio.gather(*[_process(u.id) for u in users])
    return reports


def main():
    parser = argparse.ArgumentParser(description="Eqio: verify user data correctness")
    parser.add_argument("--user-id", type=int, help="Verify single user")
    parser.add_argument("--account-id", type=int, help="Limit to single account")
    parser.add_argument("--all-users", action="store_true", help="Verify all active users")
    parser.add_argument("--max-concurrency", type=int, default=3,
                        help="Max concurrent verify tasks (default 3)")
    parser.add_argument("--no-live", action="store_true",
                        help="Skip Tinkoff API calls (DB-only verify)")
    parser.add_argument("--json", type=str, help="Write JSON report to this path")
    args = parser.parse_args()

    if not args.user_id and not args.all_users:
        parser.error("--user-id OR --all-users required")
        return 1

    if args.user_id:
        report = asyncio.run(_run_for_user(
            args.user_id,
            account_id=args.account_id,
            skip_live=args.no_live,
        ))
        _print_report(report)
        if args.json:
            Path(args.json).write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\nJSON written to {args.json}")
        sys.exit(report.exit_code)

    # --all-users
    reports = asyncio.run(_run_for_all(
        max_concurrency=args.max_concurrency,
        skip_live=args.no_live,
    ))
    total = {"ok": 0, "warning": 0, "error": 0}
    for r in reports:
        s = r.summary()
        total["ok"] += s.get("ok", 0)
        total["warning"] += s.get("warning", 0)
        total["error"] += s.get("error", 0)
    print(_bold(f"\n=== Verify ALL users ({len(reports)} users) ==="))
    print(f"  Total: ok={total['ok']} warn={total['warning']} err={total['error']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"reports": [r.to_dict() for r in reports], "total": total},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON written to {args.json}")

    if total["error"] > 0:
        sys.exit(2)
    if total["warning"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

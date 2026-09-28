"""
Live smoke validator для PR 0..3 (adapter-слой) на реальных данных
T-Invest API.

ЦЕЛЬ: убедиться что наши TinkoffUsersClient / OperationsClient /
InstrumentsClient / MarketDataClient действительно общаются с prod-API
Тинькофф на счёте пользователя ДО того как мы начнём PR 4 (AESGCM) и
далее. Подробности — в plans/.

ИСПОЛЬЗОВАНИЕ:

  cd backend
  # Положить токен в .env.local (gitignored):
  #   TINKOFF_LIVE_TOKEN=t.XXXX...
  #   TINKOFF_API_ENV=prod
  python -X utf8 -m tools.live_smoke --mode quick --save-report

ФЛАГИ:

  --mode quick   (default) первый аккаунт, 20 последних операций.
  --mode full    пагинация cursor'ом по ВСЕМ аккаунтам (долго).
  --brief        агрегаты + типы инструментов, без названий бумаг и сумм.
  --save-report  пишет JSON-снимок в backend/.local/live_smoke_*.json
                 (этот каталог — в .gitignore).
  --account ID   обработать только указанный broker_account_id.

БЕЗОПАСНОСТЬ: токен НИКОГДА не печатается. Любое логирование — через
`_mask.mask_token()`. В отчёте JSON не содержится `TINKOFF_LIVE_TOKEN`
(см. `redact_dict_keys`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

# .env.local подгружаем ДО любых импортов, использующих config — иначе
# settings заберёт пустые значения.
try:
    from dotenv import load_dotenv

    _backend_root = Path(__file__).resolve().parent.parent
    _env_local = _backend_root / ".env.local"
    if _env_local.exists():
        load_dotenv(_env_local, override=False)
except ImportError:
    print("[!] python-dotenv не установлен. Запусти: pip install python-dotenv")
    sys.exit(2)

from adapters.tinkoff.client_factory import client_factory  # noqa: E402
from adapters.tinkoff.instruments_client import TinkoffInstrumentsClient  # noqa: E402
from adapters.tinkoff.marketdata_client import TinkoffMarketDataClient  # noqa: E402
from adapters.tinkoff.operations_client import TinkoffOperationsClient  # noqa: E402
from adapters.tinkoff.users_client import TinkoffUsersClient  # noqa: E402
from domain.exceptions import (  # noqa: E402
    BrokerError,
    BrokerUnavailable,
    RateLimitExceeded,
    TokenInvalid,
    TokenScopeInsufficient,
)
from tools._mask import mask_token, redact_dict_keys  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decimal_safe(value: Any) -> Any:
    """Decimal → str (для JSON.dumps). Datetime → ISO."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _json_default(value: Any) -> Any:
    converted = _decimal_safe(value)
    if converted is not value:
        return converted
    raise TypeError(f"unserializable: {type(value).__name__}")


def _print_section(title: str) -> None:
    print(f"\n── {title} " + "─" * (78 - len(title) - 4))


# ── stages ─────────────────────────────────────────────────────────────


async def _stage_accounts(users: TinkoffUsersClient) -> list[Any]:
    _print_section("1. accounts")
    accounts = await users.list_accounts()
    print(f"OK accounts: {len(accounts)}")
    for acc in accounts:
        print(
            f"  · id={acc.id}  name={acc.name!r}  type={acc.type}  "
            f"status={acc.status}  access={acc.access_level}"
        )
    return accounts


async def _stage_operations(
    ops: TinkoffOperationsClient,
    account_id: str,
    *,
    full: bool,
    brief: bool,
    page_size: int,
) -> list[Any]:
    _print_section(f"2. operations (account={account_id})")
    fetched: list[Any] = []
    cursor = ""
    pages = 0
    while True:
        page, cursor = await ops.fetch_operations_cursor(
            account_id, cursor=cursor, limit=page_size
        )
        fetched.extend(page)
        pages += 1
        print(f"  page {pages}: +{len(page)} ops (total {len(fetched)}, next_cursor={'yes' if cursor else 'no'})")
        if not full or not cursor:
            break
        # Защита: не более 1000 страниц.
        if pages >= 1000:
            print("  [!] reached page limit 1000 — stopping")
            break

    print(f"OK operations fetched: {len(fetched)}")
    if not brief and fetched:
        print("  · sample (latest 5):")
        for op in fetched[:5]:
            payment_str = "—"
            if op.payment is not None:
                payment_str = f"{op.payment.to_decimal()} {op.payment.currency.upper()}"
            instr_str = op.instrument_uid or "—"
            print(
                f"    [{op.executed_at.strftime('%Y-%m-%d %H:%M')}] "
                f"{op.operation_type.value:<22} qty={op.quantity:>6}  "
                f"payment={payment_str:<18}  uid={instr_str}"
            )

    # Сводка по типам операций
    type_counts: dict[str, int] = {}
    for op in fetched:
        key = op.operation_type.value
        type_counts[key] = type_counts.get(key, 0) + 1
    if type_counts:
        print("  · types:")
        for t, n in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {t:<24} {n}")
    return fetched


async def _stage_instruments(
    instruments: TinkoffInstrumentsClient,
    operations: list[Any],
    *,
    brief: bool,
    max_lookups: int,
) -> dict[str, Any]:
    _print_section("3. instruments")
    uids: list[str] = []
    seen: set[str] = set()
    for op in operations:
        if op.instrument_uid and op.instrument_uid not in seen:
            seen.add(op.instrument_uid)
            uids.append(op.instrument_uid)
    targets = uids[:max_lookups]
    print(f"  unique instruments in ops: {len(uids)}, will resolve: {len(targets)}")
    resolved: dict[str, Any] = {}
    for uid in targets:
        try:
            inst = await instruments.get_instrument_by_uid(uid)
        except BrokerError as exc:
            print(f"  [!] {uid}: {type(exc).__name__} — {exc.message}")
            continue
        resolved[uid] = inst
        if not brief:
            print(
                f"  · {inst.instrument_type.value:<10} {inst.ticker or '—':<12} "
                f"figi={inst.figi or '—':<14} name={(inst.name or '')[:48]!r}"
            )
    print(f"OK instruments resolved: {len(resolved)}")
    return resolved


async def _stage_portfolio(
    ops: TinkoffOperationsClient, account_id: str, *, brief: bool
) -> Any:
    _print_section(f"4. portfolio (account={account_id})")
    try:
        raw = await ops.get_portfolio_raw(account_id)
    except BrokerError as exc:
        print(f"  [!] {type(exc).__name__} — {exc.message}")
        return None

    positions = list(getattr(raw, "positions", []) or [])
    print(f"OK portfolio positions: {len(positions)}")
    total_amount = getattr(raw, "total_amount_portfolio", None)
    if total_amount is not None and not brief:
        units = getattr(total_amount, "units", 0)
        nano = getattr(total_amount, "nano", 0)
        curr = getattr(total_amount, "currency", "rub").upper()
        value = Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
        print(f"  · total_amount_portfolio: {value} {curr}")

    if not brief and positions:
        print("  · positions (top 5 by abs(quantity)):")
        # OperationsService.get_portfolio.PortfolioPosition имеет
        # quantity как Quotation. Сортируем по |units|.
        positions_sorted = sorted(
            positions,
            key=lambda p: abs(getattr(getattr(p, "quantity", None), "units", 0)),
            reverse=True,
        )
        for p in positions_sorted[:5]:
            q = getattr(p, "quantity", None)
            q_units = getattr(q, "units", 0) if q else 0
            uid = getattr(p, "instrument_uid", None) or "—"
            figi = getattr(p, "figi", None) or "—"
            itype = getattr(p, "instrument_type", "") or ""
            print(f"    {itype:<10} qty={q_units:>8}  uid={uid:<40} figi={figi}")
    return raw


async def _stage_last_prices(
    marketdata: TinkoffMarketDataClient,
    operations: list[Any],
    *,
    brief: bool,
    max_prices: int,
) -> dict[str, Decimal]:
    _print_section("5. last_prices")
    uids: list[str] = []
    seen: set[str] = set()
    for op in operations:
        if op.instrument_uid and op.instrument_uid not in seen:
            seen.add(op.instrument_uid)
            uids.append(op.instrument_uid)
    targets = uids[:max_prices]
    if not targets:
        print("  no instrument_uids to query")
        return {}
    prices = await marketdata.get_last_prices(targets)
    print(f"OK last_prices: {len(prices)} of {len(targets)}")
    if not brief:
        for uid, price in prices.items():
            print(f"  · {uid}: {price}")
    return prices


# ── main ───────────────────────────────────────────────────────────────


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    token = os.getenv("TINKOFF_LIVE_TOKEN", "")
    if not token:
        print(
            "[FATAL] TINKOFF_LIVE_TOKEN не задан.\n"
            "Создай backend/.env.local со строкой:\n"
            "  TINKOFF_LIVE_TOKEN=t.XXXX...\n"
            "  TINKOFF_API_ENV=prod"
        )
        sys.exit(2)

    api_env = os.getenv("TINKOFF_API_ENV", "prod")
    print(
        f"[i] Tinkoff env: {api_env}  |  endpoint: {client_factory.endpoint}\n"
        f"[i] Token: {mask_token(token)} (length={len(token)})"
    )
    if client_factory.is_sandbox:
        print(
            "[!] TINKOFF_API_ENV=sandbox — это НЕ ваш реальный счёт. "
            "Если нужны живые данные — задайте TINKOFF_API_ENV=prod в .env.local."
        )

    started_at = time.monotonic()
    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "mode": args.mode,
        "brief": args.brief,
        "env": api_env,
        "endpoint": client_factory.endpoint,
        "token_masked": mask_token(token),
        "errors": [],
    }

    try:
        async with client_factory.async_client(token) as services:
            users = TinkoffUsersClient(services)
            ops_client = TinkoffOperationsClient(services)
            instruments_client = TinkoffInstrumentsClient(services)
            marketdata_client = TinkoffMarketDataClient(services)

            # 1. accounts
            accounts = await _stage_accounts(users)
            report["accounts"] = [
                {
                    "id": acc.id,
                    "name": acc.name if not args.brief else None,
                    "type": acc.type,
                    "status": acc.status,
                    "access_level": acc.access_level,
                    "is_read_only_or_better": acc.is_read_only_or_better,
                }
                for acc in accounts
            ]
            if not accounts:
                print("[!] нет аккаунтов — нечего тестировать дальше")
                return report

            target_accounts = accounts
            if args.account:
                target_accounts = [a for a in accounts if a.id == args.account]
                if not target_accounts:
                    print(f"[FATAL] аккаунт {args.account} не найден среди {[a.id for a in accounts]}")
                    sys.exit(3)
            elif args.mode == "quick":
                # Берём первый с правами read-only-or-better.
                target_accounts = [
                    a for a in accounts if a.is_read_only_or_better
                ][:1] or accounts[:1]

            # 2-5: по каждому target-аккаунту
            full_mode = args.mode == "full"
            account_reports: list[dict[str, Any]] = []
            for acc in target_accounts:
                ops_list = await _stage_operations(
                    ops_client,
                    acc.id,
                    full=full_mode,
                    brief=args.brief,
                    page_size=20 if not full_mode else 1000,
                )
                instruments = await _stage_instruments(
                    instruments_client,
                    ops_list,
                    brief=args.brief,
                    max_lookups=5 if not full_mode else 25,
                )
                portfolio = await _stage_portfolio(
                    ops_client, acc.id, brief=args.brief
                )
                last_prices = await _stage_last_prices(
                    marketdata_client,
                    ops_list,
                    brief=args.brief,
                    max_prices=5 if not full_mode else 25,
                )

                # Тонкий summary для отчёта (full operation list НЕ сохраняем
                # — слишком много, может содержать конфиденциальные суммы).
                op_type_counts: dict[str, int] = {}
                for op in ops_list:
                    key = op.operation_type.value
                    op_type_counts[key] = op_type_counts.get(key, 0) + 1

                account_reports.append(
                    {
                        "account_id": acc.id,
                        "operations_total": len(ops_list),
                        "operations_by_type": op_type_counts,
                        "instruments_resolved": len(instruments),
                        "instrument_types": dict(
                            (it.value, sum(1 for x in instruments.values() if x.instrument_type == it))
                            for it in {x.instrument_type for x in instruments.values()}
                        )
                        if instruments
                        else {},
                        "portfolio_positions": len(
                            list(getattr(portfolio, "positions", []) or [])
                        )
                        if portfolio is not None
                        else None,
                        "last_prices_count": len(last_prices),
                    }
                )
            report["account_reports"] = account_reports

    except TokenInvalid as exc:
        report["errors"].append({"type": "TokenInvalid", "message": exc.message})
        print(
            f"\n[FATAL] TokenInvalid: {exc.message}\n"
            "→ Токен битый или истёк (3 месяца неиспользования). "
            "Создай новый в lk.tbank.ru → Инвестиции → API."
        )
    except TokenScopeInsufficient as exc:
        report["errors"].append({"type": "TokenScopeInsufficient", "message": exc.message})
        print(
            f"\n[FATAL] TokenScopeInsufficient: {exc.message}\n"
            "→ У токена нет прав хотя бы read-only к этому счёту."
        )
    except RateLimitExceeded as exc:
        report["errors"].append({"type": "RateLimitExceeded", "message": exc.message})
        print(f"\n[!] RateLimitExceeded: {exc.message}\n→ Подожди минуту и повтори.")
    except BrokerUnavailable as exc:
        report["errors"].append({"type": "BrokerUnavailable", "message": exc.message})
        print(f"\n[!] BrokerUnavailable: {exc.message}\n→ Сетевая или сервисная проблема, повтори через 30 сек.")
    except BrokerError as exc:
        report["errors"].append({"type": type(exc).__name__, "message": exc.message})
        print(f"\n[!] {type(exc).__name__}: {exc.message}")

    report["duration_sec"] = round(time.monotonic() - started_at, 2)
    report["finished_at"] = _now_iso()
    return report


def _save_report(report: dict[str, Any]) -> Path:
    backend_root = Path(__file__).resolve().parent.parent
    out_dir = backend_root / ".local"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"live_smoke_{ts}.json"
    sanitized = redact_dict_keys(report)
    path.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live smoke validator for Tinkoff Invest adapter."
    )
    parser.add_argument("--mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--brief", action="store_true", help="Скрыть имена бумаг и суммы.")
    parser.add_argument("--save-report", action="store_true", help="Сохранить JSON-отчёт.")
    parser.add_argument(
        "--account",
        default=None,
        help="Конкретный broker_account_id; иначе первый read-only-or-better.",
    )
    args = parser.parse_args()

    report = asyncio.run(run_smoke(args))

    if args.save_report:
        path = _save_report(report)
        print(f"\n[i] report saved: {path}")

    print(f"\n[i] duration: {report.get('duration_sec', 0)} sec")
    if report.get("errors"):
        sys.exit(1)


if __name__ == "__main__":
    main()

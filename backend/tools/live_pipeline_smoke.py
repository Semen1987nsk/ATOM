"""
Live pipeline smoke — прогоняет полный `SyncPipeline.run(full_sync=True)`
на ваших реальных данных в **изолированную** SQLite-БД (`backend/.local/`),
чтобы не трогать прод-`atom.db`.

ЦЕЛЬ: end-to-end доказательство что PR 5 (orchestrator + pipeline) работает
с реальным токеном. Должны увидеть:

* N операций (точно столько же, сколько в `live_smoke --mode full`),
* инстрyments resolved'тся,
* sync_cursor сохранён в BrokerConnection,
* повторный прогон не вносит дубликатов (idempotency).

ИСПОЛЬЗОВАНИЕ:

  cd backend
  python -X utf8 -m tools.live_pipeline_smoke

БЕЗОПАСНОСТЬ:

* Токен берётся из `.env.local`. Никогда не печатается.
* Создаётся temp `backend/.local/live_pipeline.db` (gitignored). После
  прогона можно удалить или оставить для дебага.
* Шифрование токена — `with_ephemeral_dev_key()` (один процесс, перезапуск
  invalidates). Не для production — только для smoke.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# .env.local перед config.
try:
    from dotenv import load_dotenv

    _backend_root = Path(__file__).resolve().parent.parent
    _env_local = _backend_root / ".env.local"
    if _env_local.exists():
        load_dotenv(_env_local, override=False)
except ImportError:
    print("[!] python-dotenv не установлен. pip install python-dotenv")
    sys.exit(2)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.users_client import TinkoffUsersClient
from application.sync.pipeline import SyncPipeline
from models import Account, Base, BrokerConnection, OperationORM, User
from tools._mask import mask_token


_BACKEND = Path(__file__).resolve().parent.parent
_DB_DIR = _BACKEND / ".local"
_DB_PATH = _DB_DIR / "live_pipeline.db"


# ── helpers ──────────────────────────────────────────────────────────


def _print_section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 78 - len(title) - 4))


def _bootstrap_db() -> sessionmaker:
    """Создать БД-файл и таблицы. Возвращает session-фабрику."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _ensure_account_and_connection(
    session_factory: sessionmaker,
    *,
    encryption: TokenEncryptionService,
    broker_account_id: str,
    plaintext_token: str,
) -> tuple[int, int]:
    """
    Создать (или переиспользовать) минимального User+Account и активный
    BrokerConnection с зашифрованным токеном.
    """
    with session_factory() as session:
        user = (
            session.query(User)
            .filter_by(email="live-smoke@local.test")
            .first()
        )
        if user is None:
            user = User(
                email="live-smoke@local.test",
                name="Live smoke",
                is_active=1,
            )
            session.add(user)
            session.flush()

        account = (
            session.query(Account)
            .filter_by(user_id=user.id)
            .first()
        )
        if account is None:
            account = Account(user_id=user.id, name="live", currency="RUB")
            session.add(account)
            session.flush()

        token_repo = TokenRepository(encryption=encryption)
        connection = token_repo.store(
            session,
            account_id=account.id,
            broker_account_id=broker_account_id,
            plaintext_token=plaintext_token,
        )
        session.commit()
        return account.id, connection.id


async def _fetch_broker_account_id(token: str) -> str:
    """Узнать broker_account_id у Tinkoff (1-й read-only-or-better)."""
    async with client_factory.async_client(token) as services:
        users = TinkoffUsersClient(services)
        accounts = await users.list_accounts()
    candidates = [a for a in accounts if a.is_read_only_or_better]
    if not candidates:
        raise RuntimeError(
            "no read-only-or-better accounts on this token; nothing to sync"
        )
    return candidates[0].id


def _print_open_positions(session_factory: sessionmaker, account_id: int) -> None:
    """PR 11: список открытых позиций с MTM."""
    from models import InstrumentORM, PositionORM

    print(f"\n── open positions (MTM) ──────────────────────────────────────────")
    with session_factory() as session:
        rows = (
            session.query(PositionORM, InstrumentORM)
            .outerjoin(InstrumentORM, InstrumentORM.uid == PositionORM.instrument_uid)
            .filter(PositionORM.account_id == account_id)
            .all()
        )
    if not rows:
        print("  (no open positions)")
        return
    print(f"  {'TICKER':<10} {'TYPE':<10} {'QTY':>8} {'ENTRY':>12} {'CURRENT':>12} {'UNREALIZED':>14}")
    for pos, inst in rows:
        ticker = (inst.ticker if inst else "—") or "—"
        unrealized = pos.unrealized_pnl if pos.unrealized_pnl is not None else "—"
        current = pos.current_price if pos.current_price is not None else "—"
        print(
            f"  {ticker:<10} {pos.instrument_type:<10} {pos.quantity:>8} "
            f"{str(pos.avg_entry_price):>12} {str(current):>12} {str(unrealized):>14}"
        )


def _summarize_db(session_factory: sessionmaker, account_id: int) -> dict:
    """Вернуть факты из БД для сравнения с ожиданиями."""
    from sqlalchemy import func

    from models import PositionORM
    from models import Trade as TradeORM

    with session_factory() as session:
        total = (
            session.query(OperationORM)
            .filter(OperationORM.account_id == account_id)
            .count()
        )
        types_rows = (
            session.query(OperationORM.operation_type)
            .filter(OperationORM.account_id == account_id)
            .all()
        )
        type_counts: dict[str, int] = {}
        for (t,) in types_rows:
            type_counts[t] = type_counts.get(t, 0) + 1

        instrument_uids = {
            r[0]
            for r in session.query(OperationORM.instrument_uid)
            .filter(OperationORM.account_id == account_id)
            .distinct()
            .all()
            if r[0]
        }

        cursor_row = (
            session.query(BrokerConnection.sync_cursor)
            .filter_by(account_id=account_id, is_active=True)
            .first()
        )
        cursor = cursor_row[0] if cursor_row else None

        # PR 7: trades + positions сводки.
        trades_total = (
            session.query(TradeORM)
            .filter(
                TradeORM.account_id == account_id,
                TradeORM.data_source == "tinkoff_v2",
            )
            .count()
        )
        trades_by_type_rows = (
            session.query(TradeORM.instrument_type_v2, func.count())
            .filter(
                TradeORM.account_id == account_id,
                TradeORM.data_source == "tinkoff_v2",
            )
            .group_by(TradeORM.instrument_type_v2)
            .all()
        )
        # gross/net PnL по type.
        pnl_by_type_rows = (
            session.query(
                TradeORM.instrument_type_v2,
                func.sum(TradeORM.pnl),
                func.sum(TradeORM.net_pnl),
            )
            .filter(
                TradeORM.account_id == account_id,
                TradeORM.data_source == "tinkoff_v2",
            )
            .group_by(TradeORM.instrument_type_v2)
            .all()
        )

        positions_open = (
            session.query(PositionORM)
            .filter(PositionORM.account_id == account_id)
            .count()
        )
    return {
        "operations_total": total,
        "operations_by_type": type_counts,
        "instrument_uids_count": len(instrument_uids),
        "sync_cursor_saved": bool(cursor),
        "sync_cursor_length": len(cursor) if cursor else 0,
        "trades_total": trades_total,
        "trades_by_type": dict(trades_by_type_rows),
        "pnl_by_type": {
            row[0]: {
                "gross": str(row[1]) if row[1] is not None else "0",
                "net": str(row[2]) if row[2] is not None else "0",
            }
            for row in pnl_by_type_rows
        },
        "positions_open": positions_open,
    }


# ── main ─────────────────────────────────────────────────────────────


async def main() -> int:
    token = os.getenv("TINKOFF_LIVE_TOKEN", "")
    if not token:
        print("[FATAL] TINKOFF_LIVE_TOKEN не задан в backend/.env.local")
        return 2

    api_env = os.getenv("TINKOFF_API_ENV", "prod")
    print(
        f"[i] Tinkoff env: {api_env}  |  endpoint: {client_factory.endpoint}\n"
        f"[i] Token: {mask_token(token)} (length={len(token)})\n"
        f"[i] Temp DB: {_DB_PATH}"
    )
    if client_factory.is_sandbox:
        print("[!] TINKOFF_API_ENV=sandbox — это НЕ ваш реальный счёт.")

    _print_section("1. resolve broker_account_id")
    broker_account_id = await _fetch_broker_account_id(token)
    print(f"OK broker_account_id: {broker_account_id}")

    _print_section("2. bootstrap isolated DB & encrypted token")
    session_factory = _bootstrap_db()
    # Используем ephemeral dev-ключ — для smoke этого достаточно, токен
    # шифруется тем же приёмом что и в prod (AES-256-GCM).
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        encryption = TokenEncryptionService.with_ephemeral_dev_key()
    account_id, connection_id = _ensure_account_and_connection(
        session_factory,
        encryption=encryption,
        broker_account_id=broker_account_id,
        plaintext_token=token,
    )
    print(
        f"OK isolated user/account ready (account_id={account_id}, connection_id={connection_id})"
    )

    _print_section("3. first pipeline run (full_sync=True)")
    pipeline = SyncPipeline(
        account_id=account_id,
        broker_account_id=broker_account_id,
        token_plaintext=token,
        session_factory=session_factory,
        page_size=1000,
        max_instruments_per_run=200,  # хотим увидеть весь справочник
    )
    report = await pipeline.run(full_sync=True)
    print(
        f"OK pages={report.pages_fetched}  operations={report.operations_total}  "
        f"new_or_updated={report.operations_new_or_updated}  "
        f"instruments={report.instruments_resolved}  "
        f"trades={report.trades_built}  positions={report.positions_open}  "
        f"duration={report.duration_sec}s  success={report.success}"
    )
    print(
        f"  account_varmargin_total = {report.account_varmargin_total} RUB"
    )
    if report.error_message:
        print(f"  error: {report.error_type}: {report.error_message}")

    _print_open_positions(session_factory, account_id)

    _print_section("4. DB facts after first run")
    facts = _summarize_db(session_factory, account_id)
    print(f"  operations_total      = {facts['operations_total']}")
    print(f"  instrument_uids_count = {facts['instrument_uids_count']}")
    print(f"  sync_cursor_saved     = {facts['sync_cursor_saved']} (length={facts['sync_cursor_length']})")
    print(f"  trades_total (tinkoff_v2) = {facts['trades_total']}")
    print(f"  positions_open        = {facts['positions_open']}")
    print(f"  trades by type:")
    for t, n in sorted(facts["trades_by_type"].items(), key=lambda x: -(x[1] or 0)):
        print(f"    {t:<12} {n}")
    print(f"  PnL by type (gross / net):")
    for t, pnls in facts["pnl_by_type"].items():
        print(f"    {t:<12} {pnls['gross']:>12}  /  {pnls['net']:>12}")
    print(f"  top operation types:")
    for t, n in sorted(
        facts["operations_by_type"].items(), key=lambda x: -x[1]
    )[:10]:
        print(f"    {t:<24} {n}")

    _print_section("5. second run — idempotency check")
    # Pipeline должен использовать сохранённый cursor → быстро вернуться,
    # ничего нового не вставить. Дубликаты не появятся (UNIQUE constraint).
    second = await pipeline.run(full_sync=False)
    print(
        f"OK pages={second.pages_fetched}  operations={second.operations_total}  "
        f"duration={second.duration_sec}s"
    )

    facts_after = _summarize_db(session_factory, account_id)
    delta = facts_after["operations_total"] - facts["operations_total"]
    print(f"  delta_operations_total = {delta} (ожидаем 0 если в Tinkoff не было новых операций)")

    print(
        f"\n[i] live_pipeline.db saved at {_DB_PATH}. Можно удалить или открыть в DB browser для проверки."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

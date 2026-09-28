"""
Live instrument bootstrap — выгружает полный справочник Tinkoff в
изолированную SQLite БД (`backend/.local/live_instruments.db`).

ИСПОЛЬЗОВАНИЕ:

  cd backend
  python -X utf8 -m tools.live_instrument_bootstrap        # все типы
  python -X utf8 -m tools.live_instrument_bootstrap --skip-options

Цели:
1. Замерить реальный размер каждого типа инструментов в Тинькофф.
2. Замерить время полной загрузки и UPSERT — base для PR 13 UX
   («Загружаем справочник… ~3 мин»).
3. Подтвердить что наш InstrumentRepository корректно сохраняет
   100k+ записей без OperationalError (чанкование работает).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# .env.local
try:
    from dotenv import load_dotenv

    _backend_root = Path(__file__).resolve().parent.parent
    _env_local = _backend_root / ".env.local"
    if _env_local.exists():
        load_dotenv(_env_local, override=False)
except ImportError:
    print("[!] pip install python-dotenv")
    sys.exit(2)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.tinkoff.client_factory import client_factory
from application.sync.instrument_bootstrap import InstrumentBootstrapService
from models import Base, InstrumentORM
from tools._mask import mask_token


_BACKEND = Path(__file__).resolve().parent.parent
_DB_DIR = _BACKEND / ".local"
_DB_PATH = _DB_DIR / "live_instruments.db"


def _bootstrap_db() -> sessionmaker:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{_DB_PATH}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


async def main(args: argparse.Namespace) -> int:
    token = os.getenv("TINKOFF_LIVE_TOKEN", "")
    if not token:
        print("[FATAL] TINKOFF_LIVE_TOKEN не задан в backend/.env.local")
        return 2

    api_env = os.getenv("TINKOFF_API_ENV", "prod")
    print(
        f"[i] Tinkoff env: {api_env}  |  endpoint: {client_factory.endpoint}\n"
        f"[i] Token: {mask_token(token)} (length={len(token)})\n"
        f"[i] Temp DB: {_DB_PATH}\n"
        f"[i] skip_options: {args.skip_options}"
    )

    session_factory = _bootstrap_db()
    service = InstrumentBootstrapService(
        instrument_repo=InstrumentRepository(),
        session_factory=session_factory,
    )

    print("\n── bootstrap_all ─────────────────────────────────────────────────")
    report = await service.bootstrap_all(token, skip_options=args.skip_options)
    print(
        f"\n[i] success={report.success}  total={report.total}  "
        f"duration={report.duration_sec}s"
    )
    if report.error_message:
        print(f"[!] error: {report.error_type}: {report.error_message}")

    print("\n── by type ────────────────────────────────────────────────────────")
    for type_name, count in sorted(report.by_type.items(), key=lambda x: -x[1]):
        print(f"  {type_name:<12} {count}")

    print("\n── DB sanity check ──────────────────────────────────────────────")
    with session_factory() as session:
        # Per-type counts с уровня БД (должно совпадать с report.by_type).
        from sqlalchemy import func

        rows = (
            session.query(InstrumentORM.instrument_type, func.count())
            .group_by(InstrumentORM.instrument_type)
            .all()
        )
        total_in_db = session.query(InstrumentORM).count()
    print(f"  total_in_db: {total_in_db}")
    for type_name, count in sorted(rows, key=lambda x: -x[1]):
        print(f"  {type_name:<12} {count}")

    print(f"\n[i] DB saved at {_DB_PATH}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-options", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args)))

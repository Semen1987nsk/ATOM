"""
Refresh missing instrument specs — T1 fix.

Сканирует InstrumentORM на инструменты у которых отсутствуют поля важные для
PnL вычисления (min_price_increment_amount / min_price_increment у futures,
nominal у bonds, и т.п.) и точечно тянет их специфику через Tinkoff Instruments
API.

ЦЕЛЬ: убрать T1 transformation warning ("Фьючерсы без min_price_increment_amount:
P&L масштаб может быть занижен в 100x").

ИСПОЛЬЗОВАНИЕ:

    python -X utf8 -m tools.refresh_missing_instrument_specs --account-id 4
    python -X utf8 -m tools.refresh_missing_instrument_specs --account-id 4 --dry-run

Exit codes:
    0 — все targeted instruments обновлены (или dry-run выполнен)
    1 — частичная неудача (некоторые UIDs не найдены / ошибка API)
    2 — fatal (нет токена / нет коннекта)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import models
from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.instruments_client import TinkoffInstrumentsClient
from database import SessionLocal
from domain.exceptions import InstrumentNotFound, BrokerError
from moex_service import MoexService


def _find_missing_specs(db, account_id: int) -> list[dict]:
    """Все instrument_uid из operations этого account где специфика недостаёт."""
    op_uids = (
        db.query(models.OperationORM.instrument_uid, models.OperationORM.instrument_type)
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.instrument_uid.isnot(None),
        )
        .distinct()
        .all()
    )
    uid_to_type = {uid: itype for (uid, itype) in op_uids if uid}

    missing = []
    for uid, itype in uid_to_type.items():
        inst = db.query(models.InstrumentORM).filter_by(uid=uid).first()
        if inst is None:
            missing.append({
                "uid": uid,
                "ticker": None,
                "type": itype,
                "reason": "not_in_cache",
            })
            continue
        # Для futures обязательны min_price_increment_amount и min_price_increment.
        # NB: T-Bank API часто возвращает amount=Decimal(0) (мусор) — это тоже
        # invalid и требует MOEX fallback.
        if itype == "futures":
            from decimal import Decimal as _Decimal
            amount_invalid = (
                inst.min_price_increment_amount is None
                or inst.min_price_increment_amount == _Decimal(0)
            )
            minstep_invalid = (
                inst.min_price_increment is None
                or inst.min_price_increment == _Decimal(0)
            )
            if amount_invalid or minstep_invalid:
                missing.append({
                    "uid": uid,
                    "ticker": inst.ticker,
                    "type": "futures",
                    "reason": "missing_point_value_fields",
                    "min_price_increment": str(inst.min_price_increment),
                    "min_price_increment_amount": str(inst.min_price_increment_amount),
                })
        # Для bonds — nominal должен быть
        elif itype == "bonds":
            if inst.nominal is None:
                missing.append({
                    "uid": uid,
                    "ticker": inst.ticker,
                    "type": "bonds",
                    "reason": "missing_nominal",
                })
    return missing


def _enrich_futures_from_moex(inst, moex: MoexService):
    """Если у futures'а пустые min_price_increment / amount — фоллбэк на MOEX ISS.

    T-Bank API сам возвращает мусор (`amount=0`) для всех futures на acc#4
    проверке. MOEX ISS отдаёт `STEPPRICE` / `MINSTEP` корректно. Если MOEX
    не находит (например, истёкший контракт), используется
    `KNOWN_FUTURES_SPECS` таблица в moex_service.

    Возвращает (new_inst, changed, source_note). new_inst — обновлённый
    pydantic объект (Instrument frozen, нужно model_copy).
    """
    from decimal import Decimal as _Decimal

    if getattr(inst, "instrument_type", None) != "futures":
        return inst, False, ""
    api_minstep = getattr(inst, "min_price_increment", None)
    api_amount = getattr(inst, "min_price_increment_amount", None)
    needs_fix = (
        api_amount is None
        or api_amount == _Decimal(0)
        or api_minstep is None
        or api_minstep == _Decimal(0)
    )
    if not needs_fix:
        return inst, False, "api_ok"
    ticker = getattr(inst, "ticker", None)
    if not ticker:
        return inst, False, "no_ticker"
    spec = moex.get_futures_spec(ticker)
    if spec is not None:
        # MOEX ISS дал реальные данные
        minstep = spec["minstep"]
        stepprice = spec["stepprice"]
        new_inst = inst.model_copy(update={
            "min_price_increment": minstep,
            "min_price_increment_amount": stepprice,
        })
        return new_inst, True, f"moex_iss(minstep={minstep},stepprice={stepprice})"

    # MOEX не нашёл (expired contract) — пробуем KNOWN_FUTURES_SPECS таблицу
    # напрямую (различаем "найдено с pv=1" vs "не найдено вообще").
    from moex_service import KNOWN_FUTURES_SPECS
    if len(ticker) >= 3:
        for base_code in (ticker[:-2].upper(), ticker[:2].upper()):
            if base_code in KNOWN_FUTURES_SPECS:
                ks = KNOWN_FUTURES_SPECS[base_code]
                new_inst = inst.model_copy(update={
                    "min_price_increment": ks["minstep"],
                    "min_price_increment_amount": ks["stepprice"],
                })
                return new_inst, True, (
                    f"known_specs[{base_code}](minstep={ks['minstep']},"
                    f"stepprice={ks['stepprice']})"
                )
    return inst, False, "no_moex_no_known"


async def _refresh(missing: list[dict], token: str, dry_run: bool) -> tuple[int, int, int]:
    """Returns (resolved, not_found, errors)."""
    resolved = not_found = errors = 0
    if dry_run:
        return 0, 0, 0
    # T-Bank банит IP при бursty RPC (~30+ за секунду через AsyncClient).
    # Добавляем 1.5s между запросами (limit ≈40 req/min фактически, что
    # значительно ниже задеклаленных 600/min для InstrumentsService).
    INTER_RPC_DELAY_S = 1.5
    moex = MoexService()
    async with client_factory.async_client(token) as services:
        instr_client = TinkoffInstrumentsClient(services)
        session = SessionLocal()
        instr_repo = InstrumentRepository()
        try:
            batch = []
            for i, entry in enumerate(missing):
                if i > 0:
                    await asyncio.sleep(INTER_RPC_DELAY_S)
                uid = entry["uid"]
                try:
                    inst = await instr_client.get_instrument_by_uid(uid)
                    # MOEX ISS fallback для futures с пустыми amount/increment
                    inst, moex_changed, moex_src = _enrich_futures_from_moex(inst, moex)
                    batch.append(inst)
                    resolved += 1
                    moex_tag = f"  [MOEX:{moex_src}]" if moex_changed else ""
                    print(
                        f"  + {uid} ({entry.get('ticker') or '?'}) -> "
                        f"min_price_increment={inst.min_price_increment}, "
                        f"amount={inst.min_price_increment_amount}{moex_tag}"
                    )
                except InstrumentNotFound:
                    print(f"  - {uid} ({entry.get('ticker') or '?'}) NOT FOUND")
                    not_found += 1
                except BrokerError as exc:
                    print(f"  ! {uid}: {type(exc).__name__} {exc.message}")
                    errors += 1
            if batch:
                instr_repo.upsert_many(session, batch)
                session.commit()
                print(f"\nUPSERTed {len(batch)} instruments into DB")
        finally:
            session.close()
    return resolved, not_found, errors


async def main_async(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        if args.account_id:
            missing = _find_missing_specs(db, args.account_id)
        else:
            # Для всех аккаунтов
            account_ids = [
                r[0] for r in db.query(models.Account.id).distinct().all()
            ]
            missing = []
            for aid in account_ids:
                missing.extend(_find_missing_specs(db, aid))

        if not missing:
            print("No instruments need refresh. T1 should be clear.")
            return 0

        print(f"Found {len(missing)} instruments needing refresh:")
        for m in missing[:30]:
            print(f"  {m['type']:10}  {m['uid']}  {m.get('ticker') or '?':12}  {m['reason']}")
        if len(missing) > 30:
            print(f"  ... and {len(missing) - 30} more")
        print()

        # Получим токен из BrokerConnection для account_id или первого активного
        if args.account_id:
            conn = db.query(models.BrokerConnection).filter_by(
                account_id=args.account_id, is_active=True
            ).first()
        else:
            conn = db.query(models.BrokerConnection).filter_by(is_active=True).first()
        if conn is None:
            print("[FATAL] No active BrokerConnection found")
            return 2
        token_repo = TokenRepository(encryption=TokenEncryptionService())
        try:
            token = token_repo.decrypt(conn.api_token)
        except Exception as exc:
            print(f"[FATAL] Cannot decrypt token: {exc}")
            return 2

        if args.dry_run:
            print(f"[DRY-RUN] Would refresh {len(missing)} instruments via Tinkoff API")
            return 0
    finally:
        db.close()

    print(f"\nRefreshing {len(missing)} instruments via Tinkoff API...\n")
    resolved, not_found, errors = await _refresh(missing, token, args.dry_run)
    print(f"\nDone: {resolved} resolved, {not_found} not_found, {errors} errors")
    return 0 if (not_found == 0 and errors == 0) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh missing instrument specs (T1 fix)")
    parser.add_argument("--account-id", type=int, default=None,
                        help="Specific account to check. Default: all accounts.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just list affected instruments; don't call API.")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

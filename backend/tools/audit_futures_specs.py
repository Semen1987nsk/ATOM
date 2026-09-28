"""Phase 9.0 (2026-05-17): Live Tinkoff API discovery для всех closed futures
uids одного аккаунта.

Для каждого UID:
  - call `instruments.future_by(uid=...)` или `get_instrument_by_uid` если future_by fails
  - сравнить min_price_increment, min_price_increment_amount с тем что в InstrumentORM
  - вычислить drift_factor = api_pv / db_pv
  - предложить decision (refresh_cache | empirical_fallback | manual_override)

Output:
  - stdout таблица для review
  - JSON в tools/audit_results/futures_specs_diff.json для programmatic use

Usage:
    python -X utf8 -m tools.audit_futures_specs --account-id 4

Throttling: использует `services.limiter` (см. tools_workflow_au10_stream).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import database
import models
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.error_mapper import wrap_sdk_errors


def quotation_to_decimal(q) -> Decimal | None:
    if q is None:
        return None
    units = getattr(q, "units", 0) or 0
    nano = getattr(q, "nano", 0) or 0
    return Decimal(int(units)) + Decimal(int(nano)) / Decimal(1_000_000_000)


def compute_pv(min_pi: Decimal | None, min_pi_amt: Decimal | None) -> Decimal | None:
    if not min_pi or min_pi == 0 or min_pi_amt is None:
        return None
    return min_pi_amt / min_pi


async def fetch_future_spec(services, uid: str) -> dict:
    """Fetch spec from Tinkoff API. Returns dict с api fields + error если есть."""
    from t_tech.invest.schemas import InstrumentIdType

    result = {
        "uid": uid,
        "api_min_pi": None,
        "api_min_pi_amt": None,
        "api_basic_asset_size": None,
        "api_currency": None,
        "api_lot": None,
        "api_expiration_date": None,
        "api_first_trade_date": None,
        "api_last_trade_date": None,
        "api_basic_asset": None,
        "api_futures_type": None,
        "api_asset_type": None,
        "api_ticker": None,
        "error": None,
    }
    try:
        async with services.limiter:
            with wrap_sdk_errors():
                resp = await services.instruments.future_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                    id=uid,
                )
        raw = getattr(resp, "instrument", None)
        if raw is None:
            result["error"] = "no_instrument_in_response"
            return result

        result["api_ticker"] = getattr(raw, "ticker", None)
        result["api_min_pi"] = quotation_to_decimal(getattr(raw, "min_price_increment", None))
        result["api_min_pi_amt"] = quotation_to_decimal(
            getattr(raw, "min_price_increment_amount", None)
        )
        result["api_basic_asset_size"] = quotation_to_decimal(
            getattr(raw, "basic_asset_size", None)
        )
        result["api_currency"] = getattr(raw, "currency", None)
        result["api_lot"] = getattr(raw, "lot", None)
        exp_dt = getattr(raw, "expiration_date", None)
        result["api_expiration_date"] = exp_dt.isoformat() if exp_dt else None
        fdt = getattr(raw, "first_trade_date", None)
        result["api_first_trade_date"] = fdt.isoformat() if fdt else None
        ldt = getattr(raw, "last_trade_date", None)
        result["api_last_trade_date"] = ldt.isoformat() if ldt else None
        result["api_basic_asset"] = getattr(raw, "basic_asset", None) or None
        result["api_futures_type"] = getattr(raw, "futures_type", None) or None
        result["api_asset_type"] = getattr(raw, "asset_type", None) or None
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def main_async(account_id: int) -> int:
    # 1. Load token + uids from DB
    session = database.SessionLocal()
    try:
        conn = (
            session.query(models.BrokerConnection)
            .filter(
                models.BrokerConnection.account_id == account_id,
                models.BrokerConnection.is_active.is_(True),
            )
            .first()
        )
        if conn is None:
            print(f"No active BrokerConnection for account {account_id}")
            return 2

        try:
            enc = TokenEncryptionService()
        except TokenEncryptionError as e:
            print(f"Encryption setup failed: {e}")
            return 2
        repo = TokenRepository(encryption=enc)
        try:
            token = repo.get_decrypted(
                session,
                account_id=account_id,
                broker_account_id=conn.broker_account_id,
            )
        except TokenEncryptionError as e:
            print(f"Token decrypt failed: {e}")
            return 2
        if not token:
            print("Token missing")
            return 2

        # All unique closed futures uids
        rows = (
            session.query(models.Trade.instrument_uid)
            .join(
                models.InstrumentORM,
                models.InstrumentORM.uid == models.Trade.instrument_uid,
            )
            .filter(
                models.Trade.account_id == account_id,
                models.Trade.exit_at.isnot(None),
                models.InstrumentORM.instrument_type == "futures",
            )
            .distinct()
            .all()
        )
        uids = [r[0] for r in rows if r[0]]

        # Also include open futures uids (for empirical sanity check)
        open_pos_rows = (
            session.query(models.PositionORM.instrument_uid)
            .filter(
                models.PositionORM.account_id == account_id,
                models.PositionORM.quantity != 0,
                models.PositionORM.instrument_type == "futures",
            )
            .distinct()
            .all()
        )
        for r in open_pos_rows:
            if r[0] and r[0] not in uids:
                uids.append(r[0])

        # DB snapshot per uid
        db_specs = {}
        for uid in uids:
            i = (
                session.query(models.InstrumentORM)
                .filter(models.InstrumentORM.uid == uid)
                .first()
            )
            if not i:
                continue
            db_pi = Decimal(i.min_price_increment) if i.min_price_increment else None
            db_pi_amt = (
                Decimal(i.min_price_increment_amount)
                if i.min_price_increment_amount
                else None
            )
            db_specs[uid] = {
                "ticker": i.ticker,
                "db_min_pi": db_pi,
                "db_min_pi_amt": db_pi_amt,
                "db_pv": compute_pv(db_pi, db_pi_amt),
                "db_lot": i.lot,
                "db_basic_asset_size": (
                    Decimal(i.basic_asset_size) if i.basic_asset_size else None
                ),
                "db_currency": i.currency,
                "db_expiration_date": (
                    i.expiration_date.isoformat() if i.expiration_date else None
                ),
                "db_cached_at": i.cached_at.isoformat() if i.cached_at else None,
            }

        print(f"Discovery for acc#{account_id}: {len(uids)} unique futures uids")
        print(f"Calling Tinkoff future_by() for each (rate-limited)...")
        print()
    finally:
        session.close()

    # 2. Live API calls
    rows = []
    async with client_factory.async_client(token) as services:
        for idx, uid in enumerate(uids, 1):
            print(f"  [{idx}/{len(uids)}] {db_specs.get(uid, {}).get('ticker', uid[:12])}...", end=" ")
            api_data = await fetch_future_spec(services, uid)
            if api_data["error"]:
                print(f"ERROR: {api_data['error']}")
            else:
                api_pv = compute_pv(api_data["api_min_pi"], api_data["api_min_pi_amt"])
                print(f"api_pv={api_pv}")

            row = {**db_specs.get(uid, {}), **api_data}
            db_pv = row.get("db_pv")
            api_pv = compute_pv(row.get("api_min_pi"), row.get("api_min_pi_amt"))
            row["api_pv"] = api_pv
            if db_pv and api_pv and db_pv > 0:
                row["drift_factor"] = float(api_pv / db_pv)
            else:
                row["drift_factor"] = None
            rows.append(row)

    # 3. Output table
    print()
    print("=" * 140)
    print(f"{'Ticker':<10} {'DB pv':>10} {'API pv':>12} {'Drift':>8}  "
          f"{'DB lot':>6} {'API lot':>7}  {'DB curr':<6} {'API curr':<7}  "
          f"{'Expiry':<11}  {'Error / Recommendation'}")
    print("-" * 140)

    decisions = []
    for r in sorted(rows, key=lambda x: float(x.get("drift_factor") or 0) if x.get("drift_factor") else -1):
        ticker = r.get("ticker") or r.get("api_ticker") or "?"
        db_pv = r.get("db_pv")
        api_pv = r.get("api_pv")
        drift = r.get("drift_factor")
        db_lot = r.get("db_lot") or "?"
        api_lot = r.get("api_lot") or "?"
        db_curr = (r.get("db_currency") or "?")[:5]
        api_curr = (r.get("api_currency") or "?")[:5]
        expiry = (r.get("db_expiration_date") or r.get("api_expiration_date") or "?")[:10]

        if r.get("error"):
            note = f"API_ERR ({r['error'][:50]})"
            decision = "empirical_fallback"
        elif drift is None:
            note = "no_pv_data"
            decision = "manual"
        elif 0.9 <= drift <= 1.1:
            note = "OK (cache matches API)"
            decision = "no_action"
        elif drift > 5 or drift < 0.2:
            note = f"LARGE_DRIFT ({drift:.3f}x)"
            decision = "refresh_cache"
        else:
            note = f"minor_drift ({drift:.3f}x)"
            decision = "refresh_cache"

        db_pv_str = f"{float(db_pv):.3f}" if db_pv else "—"
        api_pv_str = f"{float(api_pv):.3f}" if api_pv else "—"
        drift_str = f"{drift:.3f}" if drift else "—"

        print(f"{ticker:<10} {db_pv_str:>10} {api_pv_str:>12} {drift_str:>8}  "
              f"{db_lot:>6} {str(api_lot):>7}  {db_curr:<6} {api_curr:<7}  "
              f"{expiry:<11}  {note}  -> {decision}")
        decisions.append({**r, "decision": decision, "note": note})

    # 4. Save JSON
    out_dir = Path("tools/audit_results")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "futures_specs_diff.json"
    serializable = []
    for d in decisions:
        s = {}
        for k, v in d.items():
            if isinstance(v, Decimal):
                s[k] = float(v)
            else:
                s[k] = v
        serializable.append(s)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({
            "account_id": account_id,
            "generated_at": datetime.utcnow().isoformat(),
            "rows": serializable,
        }, f, indent=2, ensure_ascii=False, default=str)
    print()
    print(f"Saved {len(decisions)} rows to {out_path}")

    # 5. Summary
    print()
    counts = {}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    print("Summary:")
    for k, v in counts.items():
        print(f"  {k:<25}: {v}")

    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    args = p.parse_args()
    return asyncio.run(main_async(args.account_id))


if __name__ == "__main__":
    sys.exit(main())

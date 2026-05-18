"""
Public landing endpoints — live MOEX ticker для guest-landing.

5 hardcoded symbols, server-side 60-second cache, graceful fallback:
- happy path: свежие prices из MOEX ISS API, stale=False
- кэш тёплый, MOEX упал: последний known good, stale=True
- кэш пуст, MOEX упал: 503

См. design spec §4.2 и §6.
"""
from __future__ import annotations
from typing import Any
import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/landing", tags=["landing"])

SYMBOLS = ("SBER", "GAZP", "LKOH", "YNDX", "IMOEX")

# 60-second cache, single key
_CACHE: TTLCache = TTLCache(maxsize=1, ttl=60)
# Last known-good snapshot — survives TTL expiry, used for stale=true
_LAST_GOOD: dict[str, Any] = {}


def _fetch_moex_marketdata() -> dict[str, dict[str, float]]:
    """Pull current marketdata for SYMBOLS via MOEX ISS API.

    SBER/GAZP/LKOH/YNDX from shares market, IMOEX from index market.
    Returns dict[symbol -> {"last": float, "change_pct": float}].
    """
    result: dict[str, dict[str, float]] = {}
    share_syms = [s for s in SYMBOLS if s != "IMOEX"]

    with httpx.Client(timeout=4.0) as cli:
        url_shares = (
            "https://iss.moex.com/iss/engines/stock/markets/shares/securities.json"
            f"?securities={','.join(share_syms)}&iss.meta=off&iss.only=marketdata"
            "&marketdata.columns=SECID,LAST,LASTCHANGEPRCNT"
        )
        r = cli.get(url_shares)
        r.raise_for_status()
        payload = r.json()["marketdata"]
        cols = payload["columns"]
        i_sec, i_last, i_chg = cols.index("SECID"), cols.index("LAST"), cols.index("LASTCHANGEPRCNT")
        for row in payload["data"]:
            sec, last, chg = row[i_sec], row[i_last], row[i_chg]
            if last is None:
                continue
            result[sec] = {"last": float(last), "change_pct": float(chg or 0)}

        url_idx = (
            "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
            "?iss.meta=off&iss.only=marketdata&marketdata.columns=SECID,LASTVALUE,LASTCHANGETOOPENPRC"
        )
        r2 = cli.get(url_idx)
        r2.raise_for_status()
        idx_rows = r2.json()["marketdata"]["data"]
        if idx_rows:
            row = idx_rows[0]
            result["IMOEX"] = {"last": float(row[1]), "change_pct": float(row[2] or 0)}

    return result


@router.get("/ticker")
def get_ticker() -> dict[str, Any]:
    """Live MOEX ticker — 5 symbols, 60s cache, graceful fallback."""
    cached = _CACHE.get("ticker")
    if cached is not None:
        return {"stale": False, "tickers": cached, "as_of": None}

    try:
        fresh = _fetch_moex_marketdata()
        tickers_list = [{"symbol": s, **fresh[s]} for s in SYMBOLS if s in fresh]
        if len(tickers_list) < 3:
            raise RuntimeError("too few symbols returned from MOEX")
        _CACHE["ticker"] = tickers_list
        _LAST_GOOD["snapshot"] = tickers_list
        return {"stale": False, "tickers": tickers_list, "as_of": None}
    except Exception:
        if "snapshot" in _LAST_GOOD:
            return {"stale": True, "tickers": _LAST_GOOD["snapshot"], "as_of": None}
        raise HTTPException(status_code=503, detail="ticker temporarily unavailable")

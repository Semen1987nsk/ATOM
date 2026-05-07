"""
MoexClient — production-ready async-клиент MOEX ISS API для Eqio.

Что внутри:
  - httpx.AsyncClient с timeout=10 сек.
  - Retry через tenacity: 4 попытки, экспонента 1→8 сек с jitter.
  - In-memory TTL-кэш на dict + monotonic clock (thread-safe для async).
  - Парсер column-oriented JSON (_normalize_iss_block).
  - Пагинация для свечей по 500 записей.
  - Методы: get_quote, get_candles, get_imoex_history, get_futures_spec.

Пример использования:

    async with MoexClient() as moex:
        quote = await moex.get_quote("SBER")
        candles = await moex.get_candles(
            "SBER",
            from_dt=datetime(2026, 5, 5, 10, 0),
            till_dt=datetime(2026, 5, 5, 18, 45),
            interval=1,
        )

В Eqio этот клиент заменяет sync httpx.Client из backend/moex_service.py.
Async важен для FastAPI — иначе блокируется event loop при batch-запросах.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

ISS_BASE = "https://iss.moex.com/iss"
DEFAULT_TIMEOUT = 10.0
MAX_PAGES = 100  # сторожевой: 100 * 500 = 50k свечей, достаточно


# ════════════════════════════════════════════════════════════════════
#  Модели
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Quote:
    secid: str
    last: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    updated_at: datetime


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float
    begin: datetime  # MSK, naive
    end: datetime    # MSK, naive


@dataclass(frozen=True)
class FuturesSpec:
    secid: str
    minstep: float
    stepprice: float
    lotsize: int
    asset_code: str
    last_trade_date: Optional[str]


# ════════════════════════════════════════════════════════════════════
#  TTL-кэш
# ════════════════════════════════════════════════════════════════════

@dataclass
class _CacheEntry:
    expires_at: float
    value: Any


class _TTLCache:
    """Thread-safe TTL-кэш на dict + monotonic clock."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None or _time.monotonic() > entry.expires_at:
                self._store.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl: float) -> None:
        async with self._lock:
            self._store[key] = _CacheEntry(_time.monotonic() + ttl, value)


# ════════════════════════════════════════════════════════════════════
#  Парсер column-oriented JSON
# ════════════════════════════════════════════════════════════════════

def _normalize_iss_block(block: Optional[dict]) -> list[dict]:
    """ISS column-oriented → list[dict]. Безопасен к None и битому формату."""
    if not block or not isinstance(block, dict):
        return []
    columns = block.get("columns") or []
    rows = block.get("data") or []
    if not columns or not rows:
        return []
    return [dict(zip(columns, row)) for row in rows]


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    """Парсит ISS datetime: 'YYYY-MM-DD HH:MM:SS' или 'YYYY-MM-DD'."""
    if not s:
        return None
    try:
        if " " in s:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return datetime.strptime(s, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


# ════════════════════════════════════════════════════════════════════
#  Клиент
# ════════════════════════════════════════════════════════════════════

class MoexClient:
    """
    Async-клиент MOEX ISS. Singleton-friendly через контекстный менеджер.

    TTL по типам данных (см. SKILL.md раздел 6):
      - quote: 30 сек
      - candles прошедшего дня: 24 часа
      - candles текущего дня: 5 минут
      - index history: 1 час
      - futures spec: 5 минут
    """

    QUOTE_TTL = 30.0
    CANDLES_PAST_TTL = 24 * 3600.0
    CANDLES_TODAY_TTL = 300.0
    INDEX_TTL = 3600.0
    SPEC_TTL = 300.0

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._cache = _TTLCache()

    async def __aenter__(self) -> "MoexClient":
        self._client = httpx.AsyncClient(
            base_url=ISS_BASE,
            timeout=self._timeout,
            headers={"User-Agent": "Eqio/1.0 (+https://eqio.app)"},
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ────────────────────────────────────────────────────────────
    #  HTTP с retry
    # ────────────────────────────────────────────────────────────

    async def _get_json(self, path: str, params: dict) -> dict:
        """GET с retry. Бросает RetryError если все попытки провалились."""
        assert self._client is not None, "Use 'async with MoexClient() as ...'"
        client = self._client

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential_jitter(initial=1, max=8, jitter=0.5),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, _RetryableISSError)
            ),
            reraise=True,
        ):
            with attempt:
                started = _time.monotonic()
                resp = await client.get(path, params=params)
                elapsed_ms = (_time.monotonic() - started) * 1000

                if resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "ISS %s %s -> %d, retrying", path, params, resp.status_code
                    )
                    raise _RetryableISSError(resp.status_code)

                if resp.status_code != 200:
                    logger.warning(
                        "ISS %s %s -> %d (no retry, client error)",
                        path,
                        params,
                        resp.status_code,
                    )
                    resp.raise_for_status()

                logger.debug("ISS %s OK in %.0fms", path, elapsed_ms)
                return resp.json()

        # Недостижимо, но mypy спокойнее
        raise RuntimeError("retry loop exited without result")

    # ────────────────────────────────────────────────────────────
    #  Quotes
    # ────────────────────────────────────────────────────────────

    async def get_quote(self, secid: str, board: str = "TQBR") -> Optional[Quote]:
        """Последняя цена + bid/ask. Кэш 30 сек."""
        cache_key = f"quote:{secid}:{board}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        path = f"/engines/stock/markets/shares/boards/{board}/securities/{secid}.json"
        params = {
            "iss.meta": "off",
            "iss.only": "marketdata",
            "marketdata.columns": "SECID,LAST,BID,OFFER,UPDATETIME",
        }
        data = await self._get_json(path, params)
        rows = _normalize_iss_block(data.get("marketdata"))
        if not rows:
            return None

        row = rows[0]
        quote = Quote(
            secid=row.get("SECID") or secid,
            last=_safe_float(row.get("LAST")),
            bid=_safe_float(row.get("BID")),
            ask=_safe_float(row.get("OFFER")),
            updated_at=datetime.utcnow(),
        )
        await self._cache.set(cache_key, quote, self.QUOTE_TTL)
        return quote

    # ────────────────────────────────────────────────────────────
    #  Candles
    # ────────────────────────────────────────────────────────────

    async def get_candles(
        self,
        secid: str,
        from_dt: datetime,
        till_dt: datetime,
        interval: int = 1,
        board: str = "TQBR",
    ) -> list[Candle]:
        """
        Свечи за окно [from_dt, till_dt] в MSK.

        interval: 1 (1m), 10 (10m), 60 (1h), 24 (1d), 7 (1w), 31 (1mo).
        Поддерживает пагинацию по 500 свечей.

        Кэш: 24 часа для целиком прошедшего окна, 5 минут если till_dt
        лежит в текущем дне.
        """
        if from_dt >= till_dt:
            return []

        cache_key = (
            f"candles:{secid}:{board}:{interval}:"
            f"{from_dt.isoformat()}:{till_dt.isoformat()}"
        )
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        path = (
            f"/engines/stock/markets/shares/boards/{board}"
            f"/securities/{secid}/candles.json"
        )
        all_rows: list[dict] = []
        offset = 0
        for _ in range(MAX_PAGES):
            params = {
                "iss.meta": "off",
                "iss.only": "candles",
                "interval": interval,
                "from": from_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "till": till_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "start": offset,
            }
            try:
                data = await self._get_json(path, params)
            except (RetryError, httpx.HTTPStatusError) as exc:
                logger.warning("Candles fetch failed for %s: %s", secid, exc)
                break

            page = _normalize_iss_block(data.get("candles"))
            if not page:
                break
            all_rows.extend(page)
            if len(page) < 500:
                break
            offset += len(page)
        else:
            logger.error("Candles paging exceeded %d pages for %s", MAX_PAGES, secid)

        candles = [_row_to_candle(r) for r in all_rows]
        candles = [c for c in candles if c is not None]

        # Кэш-TTL: если till_dt сегодня или будущее — короткий, иначе долгий.
        today = datetime.utcnow().date()
        ttl = self.CANDLES_TODAY_TTL if till_dt.date() >= today else self.CANDLES_PAST_TTL
        await self._cache.set(cache_key, candles, ttl)

        return candles

    # ────────────────────────────────────────────────────────────
    #  IMOEX история (для overlay benchmark)
    # ────────────────────────────────────────────────────────────

    async def get_imoex_history(
        self,
        from_dt: datetime,
        till_dt: datetime,
        ticker: str = "IMOEX",
    ) -> list[dict]:
        """
        Дневная история индекса. Возвращает [{date, close, value}, ...].
        Использует /history/ endpoint, пагинация по 100.
        """
        cache_key = f"index:{ticker}:{from_dt.date()}:{till_dt.date()}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        path = f"/history/engines/stock/markets/index/securities/{ticker}.json"
        all_rows: list[dict] = []
        offset = 0
        for _ in range(MAX_PAGES):
            params = {
                "iss.meta": "off",
                "iss.only": "history",
                "history.columns": "TRADEDATE,CLOSE,VALUE",
                "from": from_dt.strftime("%Y-%m-%d"),
                "till": till_dt.strftime("%Y-%m-%d"),
                "start": offset,
            }
            try:
                data = await self._get_json(path, params)
            except (RetryError, httpx.HTTPStatusError) as exc:
                logger.warning("IMOEX history failed: %s", exc)
                break

            page = _normalize_iss_block(data.get("history"))
            if not page:
                break
            for row in page:
                close = _safe_float(row.get("CLOSE"))
                if close is None:
                    continue
                all_rows.append(
                    {
                        "date": str(row.get("TRADEDATE")),
                        "close": close,
                        "value": _safe_float(row.get("VALUE")),
                    }
                )
            if len(page) < 100:
                break
            offset += len(page)

        await self._cache.set(cache_key, all_rows, self.INDEX_TTL)
        return all_rows

    # ────────────────────────────────────────────────────────────
    #  Futures specs
    # ────────────────────────────────────────────────────────────

    async def get_futures_spec(self, secid: str) -> Optional[FuturesSpec]:
        """Спецификация фьючерса (MINSTEP/STEPPRICE/LOTSIZE)."""
        cache_key = f"spec:{secid}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        path = f"/engines/futures/markets/forts/securities/{secid}.json"
        params = {"iss.meta": "off", "iss.only": "securities"}
        try:
            data = await self._get_json(path, params)
        except (RetryError, httpx.HTTPStatusError) as exc:
            logger.warning("Futures spec failed for %s: %s", secid, exc)
            return None

        rows = _normalize_iss_block(data.get("securities"))
        if not rows:
            return None
        row = rows[0]
        spec = FuturesSpec(
            secid=row.get("SECID") or secid,
            minstep=_safe_float(row.get("MINSTEP")) or 1.0,
            stepprice=_safe_float(row.get("STEPPRICE")) or 1.0,
            lotsize=int(row.get("LOTSIZE") or 1),
            asset_code=str(row.get("ASSETCODE") or ""),
            last_trade_date=row.get("LASTTRADEDATE"),
        )
        await self._cache.set(cache_key, spec, self.SPEC_TTL)
        return spec


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════

class _RetryableISSError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"ISS returned {status}")
        self.status = status


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_to_candle(row: dict) -> Optional[Candle]:
    try:
        return Candle(
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume") or 0),
            begin=_parse_dt(row.get("begin")),
            end=_parse_dt(row.get("end")),
        )
    except (KeyError, TypeError, ValueError):
        return None

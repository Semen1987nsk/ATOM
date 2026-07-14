"""SYNC-04/PERF-04: единый httpx.AsyncClient для MOEX-вызовов.

Singleton AsyncClient с общими timeout/limits + retry/backoff. Используется
как в market_service (Task 1.2/PERF-04), так и в moex_service (Task 1.3) —
вместо разных sync requests.get/httpx.Client. Один shared pool коннекций
снимает блокировку async event-loop'а и держит handshake-цену под контролем.

Lifecycle:
- get_client(): lazy-инициализация. Первый вызов создаёт AsyncClient.
- close_client(): graceful aclose; зовётся из FastAPI lifespan shutdown.

Retry policy (fetch_json):
- 2 ретрая (всего 3 попытки) на httpx.HTTPError (timeout, 5xx, network) И
  ValueError (json.JSONDecodeError — MOEX иногда отдаёт HTML под 200 на
  maintenance, тогда resp.json() бросает JSONDecodeError; без расширенного
  except'а fetch_json бросал бы это наружу вместо graceful None).
- Exponential backoff с jitter: 0.5/1.0/2.0с × (0.8 + random.random()*0.4).
  Jitter критичен под gunicorn workers (без него thundering herd на 429/503).
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=2.0)
_DEFAULT_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def get_client() -> httpx.AsyncClient:
    """Lazy-singleton AsyncClient. На shutdown зови `close_client()`."""
    global _client
    if _client is None or _client.is_closed:
        async with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, limits=_DEFAULT_LIMITS)
    return _client


async def close_client() -> None:
    """Закрывает singleton-клиента. Идемпотентно — повторный вызов no-op."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    retries: int = 2,
) -> Optional[dict[str, Any]]:
    """GET → json. None при сетевой ошибке (caller сам решает fallback).

    Возвращает None если:
    - все попытки упали по httpx.HTTPError (timeout/network/5xx)
    - resp.raise_for_status() выбросил 4xx/5xx после ретраев
    - resp.json() бросил ValueError (MOEX вернул HTML на maintenance под 200)

    json.JSONDecodeError — подкласс ValueError, поэтому ловим базовый класс.
    """
    client = await get_client()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            last_exc = exc
            if attempt < retries:
                # Exponential backoff с jitter ±20% — без jitter под
                # gunicorn workers получим thundering herd на 429/503.
                base = 0.5 * (2 ** attempt)  # 0.5, 1.0, 2.0
                jitter = base * (0.8 + random.random() * 0.4)
                await asyncio.sleep(jitter)
                continue
    logger.warning("MOEX fetch failed %s: %s", url, last_exc)
    return None

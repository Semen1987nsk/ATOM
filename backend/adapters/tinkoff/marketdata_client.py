"""
TinkoffMarketDataClient — обёртка над `services.market_data.get_last_prices`.

Mark-to-market для открытых позиций (PR 11). Лимит на этом методе щадящий
(600/min для Quotes), но для тысяч пользователей всё равно нужно
кэширование, чтобы повторные запросы цен в течение одного sync-цикла шли
в память, а не в API.

Кэш — простой dict per-instance с TTL 60 секунд. Подходит для одного
sync-прохода (orchestrator открывает клиент → запрашивает цены пакетом
→ закрывает). Cross-process кэш (Redis) — это отдельный PR (когда
понадобится).
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Iterable

from logger import get_logger

from adapters.tinkoff.error_mapper import wrap_sdk_errors
from adapters.tinkoff.proto_to_domain import quotation_to_decimal

log = get_logger("tinkoff.marketdata_client")

_DEFAULT_CACHE_TTL_SEC = 60


class TinkoffMarketDataClient:
    def __init__(self, services: Any, *, cache_ttl_sec: int = _DEFAULT_CACHE_TTL_SEC) -> None:
        self._svc = services
        self._cache_ttl = cache_ttl_sec
        # uid → (price, fetched_at)
        self._cache: dict[str, tuple[Decimal, float]] = {}

    async def get_last_prices(self, uids: Iterable[str]) -> dict[str, Decimal]:
        """Текущие last_price по списку UID. Кэш 60 сек per-instance."""
        unique_uids = list({u for u in uids if u})
        if not unique_uids:
            return {}

        now = time.monotonic()
        result: dict[str, Decimal] = {}
        missing: list[str] = []

        for uid in unique_uids:
            cached = self._cache.get(uid)
            if cached is not None and now - cached[1] < self._cache_ttl:
                result[uid] = cached[0]
            else:
                missing.append(uid)

        if not missing:
            return result

        # AU1: per-RPC rate-limit gate. MarketData лимит щадящий (600/min)
        # но всё равно идём через общий per-token bucket, чтобы не выжечь
        # лимит из-за нескольких параллельных синков на один token.
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await self._svc.market_data.get_last_prices(
                    instrument_id=missing,
                )

        items = list(getattr(response, "last_prices", []) or [])
        for item in items:
            uid = getattr(item, "instrument_uid", "") or ""
            price_raw = getattr(item, "price", None)
            price = quotation_to_decimal(price_raw)
            if uid and price is not None:
                self._cache[uid] = (price, now)
                result[uid] = price

        log.debug(
            "get_last_prices",
            extra={
                "requested": len(unique_uids),
                "cache_hit": len(unique_uids) - len(missing),
                "fetched": len(items),
            },
        )
        return result

    def invalidate(self, uids: Iterable[str] | None = None) -> None:
        """Сбросить кэш (целиком или по UID-списку)."""
        if uids is None:
            self._cache.clear()
            return
        for uid in uids:
            self._cache.pop(uid, None)

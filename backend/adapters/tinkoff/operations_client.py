"""
TinkoffOperationsClient — обёртка над `services.operations.*`.

Главный метод — `fetch_operations_cursor()`. Это рекомендуемый T-Bank
способ синхронизации (см. план PR 5):

* Идемпотентен по дизайну: повторный вызов с тем же `cursor` возвращает
  тот же набор операций.
* Поддерживает инкрементальный sync: сохраняем `next_cursor` после
  успешного UPSERT, в следующий раз дёргаем с него.
* При первом подключении (cursor=""), API отдаёт всю историю порциями
  (по умолчанию 100, max 1000).

Клиент НЕ открывает gRPC-канал сам — принимает уже готовый `services`
объект из `client_factory.async_client(token)` контекста. Это упрощает
тестирование (можно подсунуть mock без gRPC) и позволяет orchestrator'у
держать единое окно соединения для одного account_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator, Optional, Sequence

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from logger import get_logger

from adapters.tinkoff.error_mapper import wrap_sdk_errors
from adapters.tinkoff.proto_to_domain import operation_from_proto
from domain.entities import Operation
from domain.exceptions import BrokerError, BrokerUnavailable, RateLimitExceeded

log = get_logger("tinkoff.operations_client")


# PR 15: ретраить только transient ошибки. TokenInvalid/PERMISSION_DENIED/
# INSTRUMENT_NOT_FOUND — не retryable, проброс наверх.
_RETRYABLE = (BrokerUnavailable, RateLimitExceeded)


def _retry_policy() -> AsyncRetrying:
    """
    5 попыток с экспоненциальным backoff (2 → 4 → 8 → 16 → 32 сек) + jitter
    [0..2] сек. Итого max ожидание ~62 сек, p99 ~70 сек на retry-chain.

    Для RateLimitExceeded — лимит Tinkoff сбрасывается раз в минуту, наш
    backoff с этим согласуется.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60) + wait_random(0, 2),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )


class TinkoffOperationsClient:
    """
    Обёртка над OperationsService. Живёт ровно столько, сколько открыт
    канал `services` — обычно один-два sync-цикла.
    """

    def __init__(self, services: Any) -> None:
        self._svc = services

    async def fetch_operations_cursor(
        self,
        account_id: str,
        *,
        cursor: str = "",
        limit: int = 1000,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> tuple[list[Operation], str]:
        """
        Один батч операций (с retry, PR 15). Возвращает (operations, next_cursor).

        * `cursor=""` → начало (full sync).
        * `next_cursor=""` в ответе → история закончилась.
        * Поле `from_dt` имеет смысл только при `cursor=""` — иначе SDK
          игнорирует.

        Tenacity ретраит только `BrokerUnavailable` / `RateLimitExceeded`
        (5 попыток, exp-backoff). `TokenInvalid` пробрасывается сразу.
        """
        # Импорт SDK ленивый, чтобы dev-окружения без него поднимались.
        from tinkoff.invest.schemas import GetOperationsByCursorRequest

        request = GetOperationsByCursorRequest(
            account_id=account_id,
            cursor=cursor,
            limit=limit,
            from_=from_dt,
            to=to_dt,
        )

        async def _call():
            with wrap_sdk_errors():
                return await self._svc.operations.get_operations_by_cursor(request)

        response = None
        async for attempt in _retry_policy():
            with attempt:
                response = await _call()
        if response is None:  # практически не случится — reraise=True
            return [], ""

        items = list(getattr(response, "items", []) or [])
        next_cursor = getattr(response, "next_cursor", "") or ""
        operations = [operation_from_proto(item, account_id=account_id) for item in items]

        log.debug(
            "fetch_operations_cursor",
            extra={
                "account_id": account_id,
                "fetched": len(operations),
                "has_next": bool(next_cursor),
            },
        )
        return operations, next_cursor

    async def iter_all_operations(
        self,
        account_id: str,
        *,
        cursor: str = "",
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        page_size: int = 1000,
    ) -> AsyncIterator[Operation]:
        """
        Async-итератор по всей истории операций с автоматической пагинацией.

        Удобно когда не нужно держать всё в памяти: orchestrator pipeline
        сохраняет операции пакетами в БД через `OperationRepository.upsert_many`.
        """
        current_cursor = cursor
        while True:
            ops, next_cursor = await self.fetch_operations_cursor(
                account_id,
                cursor=current_cursor,
                limit=page_size,
                from_dt=from_dt,
                to_dt=to_dt,
            )
            for op in ops:
                yield op
            if not next_cursor or next_cursor == current_cursor:
                # Защита от бесконечной петли при кривой реализации сервера.
                break
            current_cursor = next_cursor

    async def get_portfolio_raw(self, account_id: str) -> Any:
        """
        Сырой PortfolioResponse с retry (PR 15).
        """
        async def _call():
            with wrap_sdk_errors():
                return await self._svc.operations.get_portfolio(account_id=account_id)

        async for attempt in _retry_policy():
            with attempt:
                return await _call()

    async def get_positions_raw(self, account_id: str) -> Any:
        """Сырой PositionsResponse с retry (PR 15)."""
        async def _call():
            with wrap_sdk_errors():
                return await self._svc.operations.get_positions(account_id=account_id)

        async for attempt in _retry_policy():
            with attempt:
                return await _call()

"""
TinkoffOperationsStreamClient — обёртка над `services.operations_stream.*`.

AU10 Phase 4c: foundation для real-time push-syncing. Новый SDK
`t-tech-investments 0.3.1+` добавил `operations_stream.operations_stream(...)` —
gRPC server-streaming endpoint, который выкидывает новые операции мгновенно
(вместо polling каждые N минут). Это позволит убрать большую часть RPC-нагрузки
для активных юзеров.

Status: foundation only. Pipeline integration в `sync_scheduler.py` —
отдельный backlog refactor (~10-15h), потому что требует:
* Long-lived task per account_id с reconnect logic
* Dedup между push-events и cursor-based catchup при reconnect
* Backpressure если poller не успевает обработать events
* Coordinated shutdown с lifespan handler

Этот файл даёт минимальный клиент; интеграция — позже.

Pattern совпадает с `operations_client.py`:
* Передаёт services из `client_factory.async_client(token)` context.
* Per-RPC rate-limit через `self._svc.limiter` (AU1).
* Маппинг proto → domain через `proto_to_domain.operation_from_proto`.
* Все SDK-ошибки идут через `error_mapper.wrap_sdk_errors()`.

Минимальная реализация — async generator который yield'ит domain.Operation
по мере прихода push-events. Reconnect logic при `UNAVAILABLE` /
`DEADLINE_EXCEEDED` через exponential backoff.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from logger import get_logger

from adapters.tinkoff.error_mapper import wrap_sdk_errors
from adapters.tinkoff.proto_to_domain import operation_from_proto
from domain.entities import Operation
from domain.exceptions import BrokerError, BrokerUnavailable

log = get_logger("tinkoff.operations_stream_client")


# Exponential backoff schedule для reconnect-цикла (секунды).
# 5s → 15s → 30s → 60s → 120s, потом 120s бесконечно.
_RECONNECT_BACKOFF = [5.0, 15.0, 30.0, 60.0, 120.0]


class TinkoffOperationsStreamClient:
    """Long-lived stream of новых операций по account_id.

    Usage (когда придёт время интеграции в pipeline):

        async with client_factory.async_client(token) as services:
            stream_client = TinkoffOperationsStreamClient(services)
            async for op in stream_client.stream_operations(broker_account_id):
                # op — domain.Operation
                await persist_operation(op)
                await maybe_recompute_trades(op)
    """

    def __init__(self, services: Any) -> None:
        self._svc = services

    async def stream_operations(
        self,
        broker_account_id: str,
        *,
        max_reconnect_attempts: int = 0,
    ) -> AsyncIterator[Operation]:
        """Async generator выкидывающий Operation по мере push'ей от T-Bank.

        Args:
            broker_account_id: Tinkoff-side account id (не наш account_id).
            max_reconnect_attempts: 0 = бесконечный reconnect (для long-lived
                worker'ов); >0 — лимит для тестов и одноразовых задач.

        Reconnect behavior:
            При `BrokerUnavailable` (UNAVAILABLE / DEADLINE_EXCEEDED) ждём
            backoff из `_RECONNECT_BACKOFF` и переоткрываем stream.
            При `TokenInvalid` — пробрасываем сразу (ретраи бессмысленны).
            При других `BrokerError` — пробрасываем (orchestrator решит что
            делать).
        """
        from t_tech.invest.schemas import OperationsStreamRequest

        attempt = 0
        while True:
            try:
                async for op in self._stream_once(broker_account_id):
                    yield op
                # Если стрим завершился без exception — выходим.
                return
            except BrokerUnavailable as exc:
                attempt += 1
                if max_reconnect_attempts and attempt > max_reconnect_attempts:
                    log.warning(
                        "operations_stream.reconnect_limit_reached",
                        extra={
                            "broker_account_id": broker_account_id,
                            "attempts": attempt,
                        },
                    )
                    raise
                delay = _RECONNECT_BACKOFF[min(attempt - 1, len(_RECONNECT_BACKOFF) - 1)]
                log.info(
                    "operations_stream.reconnecting",
                    extra={
                        "broker_account_id": broker_account_id,
                        "attempt": attempt,
                        "delay_s": delay,
                        "reason": str(exc),
                    },
                )
                await asyncio.sleep(delay)
                continue
            except BrokerError:
                raise

    async def _stream_once(
        self, broker_account_id: str
    ) -> AsyncIterator[Operation]:
        """Один открывающий-закрывающий цикл стрима. При разрыве yields stop."""
        from t_tech.invest.schemas import OperationsStreamRequest

        request = OperationsStreamRequest(accounts=[broker_account_id])
        # AU1: per-RPC rate-limit gate (limiter token берётся 1 раз на открытие
        # стрима; долгоживущий канал внутри лимитера не вычитывает).
        async with self._svc.limiter:
            with wrap_sdk_errors():
                stream = self._svc.operations_stream.operations_stream(request)
                async for response in stream:
                    op_proto = self._extract_operation_proto(response)
                    if op_proto is None:
                        continue
                    yield operation_from_proto(op_proto, account_id=broker_account_id)

    @staticmethod
    def _extract_operation_proto(response: Any) -> Optional[Any]:
        """Извлекает payload `Operation` из `OperationsStreamResponse`.

        Response — oneof, в нём может быть `operation`, `ping`, `subscription`,
        `portfolio` и т.д. Мы интересуемся только `operation`.
        """
        op = getattr(response, "operation", None)
        if op is not None:
            return op
        return None

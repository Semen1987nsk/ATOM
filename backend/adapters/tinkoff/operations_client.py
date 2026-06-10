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

import asyncio
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

from config import settings
from logger import get_logger

from adapters.tinkoff.error_mapper import wrap_sdk_errors
from adapters.tinkoff.proto_to_domain import (
    broker_report_trade_from_proto,
    operation_from_proto,
)
from domain.entities import BrokerReportTradeRow, Operation
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

    async def _guarded(self, limiter, coro):
        """SYNC-01 (limiter) + SYNC-03 (call deadline) обёртка одного RPC.

        Лимитер-токен берётся на КАЖДЫЙ RPC; сам вызов ограничен по времени
        (зависший RPC иначе держит токен/семафор бесконечно). asyncio.TimeoutError
        == TimeoutError на 3.11+; wrap_sdk_errors маппит его → BrokerUnavailable.
        """
        async with limiter:
            with wrap_sdk_errors():
                return await asyncio.wait_for(
                    coro, settings.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS
                )

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
        from t_tech.invest.schemas import GetOperationsByCursorRequest

        request = GetOperationsByCursorRequest(
            account_id=account_id,
            cursor=cursor,
            limit=limit,
            from_=from_dt,
            to=to_dt,
        )

        async def _call():
            return await self._guarded(
                self._svc.limiter,
                self._svc.operations.get_operations_by_cursor(request),
            )

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
            return await self._guarded(
                self._svc.limiter,
                self._svc.operations.get_portfolio(account_id=account_id),
            )

        async for attempt in _retry_policy():
            with attempt:
                return await _call()

    async def get_positions_raw(self, account_id: str) -> Any:
        """Сырой PositionsResponse с retry (PR 15)."""
        async def _call():
            return await self._guarded(
                self._svc.limiter,
                self._svc.operations.get_positions(account_id=account_id),
            )

        async for attempt in _retry_policy():
            with attempt:
                return await _call()

    # ────────────────────────────────────────────────────────────────────
    # PR 26 (Phase 3) — Broker Report API (Three-way reconciliation)
    # ────────────────────────────────────────────────────────────────────

    async def generate_broker_report(
        self,
        account_id: str,
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> tuple[str, Optional[Any]]:
        """Запрос генерации брокерского отчёта.

        Возвращает `(task_id, immediate_page_or_None)`.

        AU10 finding: t-tech-investments SDK 0.3.5 (и видимо T-Bank API
        в целом) на первый `get_broker_report(generate_broker_report_request=...)`
        ОДНОВРЕМЕННО:
          - создаёт отчёт (task_id),
          - и сразу же возвращает первую страницу `get_broker_report_response`
            если отчёт можно отдать без задержки.

        Если отчёт большой/долгий — `get_broker_report_response.pagesCount=0`
        или вообще None, а `generate_broker_report_response.task_id` непустой —
        тогда нужен polling по task_id.

        Раньше код возвращал только `task_id`, а вторую страницу тянул
        отдельным RPC — но для маленьких периодов task_id был None,
        задача казалась "не созданной". Теперь возвращаем и task_id, и
        возможно уже-готовую страницу.
        """
        from t_tech.invest.schemas import GenerateBrokerReportRequest

        request = GenerateBrokerReportRequest(
            account_id=account_id,
            from_=from_dt,
            to=to_dt,
        )

        async def _call():
            return await self._guarded(
                self._svc.broker_report_limiter,
                self._svc.operations.get_broker_report(
                    generate_broker_report_request=request,
                ),
            )

        async for attempt in _retry_policy():
            with attempt:
                response = await _call()
                # 1. Попробовать снять task_id из generate_broker_report_response
                gen_resp = getattr(response, "generate_broker_report_response", None)
                task_id = getattr(gen_resp, "task_id", "") if gen_resp else ""
                # 2. Если SDK вернул сразу страницу — extract task_id оттуда
                page_resp = getattr(response, "get_broker_report_response", None)
                if not task_id and page_resp is not None:
                    task_id = getattr(page_resp, "task_id", "") or ""
                if not task_id:
                    task_id = getattr(response, "task_id", "") or ""
                # SDK 0.3.5 использует camelCase `pagesCount` в response
                # (proto-generated), но fallback на snake_case для совместимости.
                pages_count = 0
                if page_resp is not None:
                    pages_count = int(
                        getattr(page_resp, "pagesCount", None)
                        or getattr(page_resp, "pages_count", 0)
                        or 0
                    )
                log.info(
                    "broker_report_task_created",
                    extra={
                        "account_id": account_id,
                        "task_id": task_id,
                        "immediate_pages_count": pages_count,
                    },
                )
                # Если SDK сразу вернул pagesCount>0 — это готовая первая
                # страница; callers могут не делать второй RPC.
                immediate_page = page_resp if pages_count > 0 else None
                return task_id, immediate_page
        return "", None

    async def fetch_broker_report_page(
        self,
        task_id: str,
        *,
        page: int = 0,
    ) -> tuple[list[BrokerReportTradeRow], int, int]:
        """Одна страница broker report. Возвращает (rows, page, pagesCount).

        Использует тот же `get_broker_report` SDK-метод, но с
        `get_broker_report_request` oneof.
        """
        from t_tech.invest.schemas import GetBrokerReportRequest

        request = GetBrokerReportRequest(task_id=task_id, page=page)

        async def _call():
            return await self._guarded(
                self._svc.broker_report_limiter,
                self._svc.operations.get_broker_report(
                    get_broker_report_request=request,
                ),
            )

        async for attempt in _retry_policy():
            with attempt:
                response = await _call()
                # BrokerReportResponse → get_broker_report_response (oneof)
                wrapper = getattr(response, "get_broker_report_response", response)
                rows_raw = (
                    getattr(wrapper, "broker_report", None)
                    or getattr(wrapper, "items", None)
                    or []
                )
                # SDK 0.3.5: camelCase `pagesCount`; fallback на snake_case.
                pages_count = int(
                    getattr(wrapper, "pagesCount", None)
                    or getattr(wrapper, "pages_count", 0)
                    or 0
                )
                current_page = int(getattr(wrapper, "page", page) or page)
                rows = [broker_report_trade_from_proto(r) for r in rows_raw]
                log.debug(
                    "broker_report_page_fetched",
                    extra={
                        "task_id": task_id,
                        "page": current_page,
                        "pages_count": pages_count,
                        "rows": len(rows),
                    },
                )
                return rows, current_page, pages_count
        return [], page, 0

    async def fetch_full_broker_report(
        self,
        account_id: str,
        *,
        from_dt: datetime,
        to_dt: datetime,
        max_poll_attempts: int = 8,
        page_size_limit: int = 100,
    ) -> list[BrokerReportTradeRow]:
        """Полный broker report за период: generate → poll → собрать все страницы.

        Tinkoff генерирует отчёт асинхронно. Первый вызов get_broker_report
        может вернуть BROKER_REPORT_NOT_READY — тогда ждём и повторяем.

        AU2 fix: linear polling каждые 2 сек заменён на exponential backoff
        (2s → 5s → 10s → 15s → 30s → 30s → 30s → 30s). При лимите 5/min на
        broker_report sub-limiter старый linear polling x30 пробивал лимит
        примерно за 1 минуту. Новый paced schedule укладывается в 5/min:
        ~7 запросов за 2 минуты ожидания.

        Args:
            max_poll_attempts: страховка от бесконечного цикла.
            page_size_limit: hard cap чтобы не утечь память (max ~100 pages).
        """
        # AU2: exponential backoff schedule для polling готовности отчёта.
        # Сумма ~120 секунд — большинство отчётов готовы за 30-60 сек.
        _POLL_BACKOFF = [2.0, 5.0, 10.0, 15.0, 30.0, 30.0, 30.0, 30.0]

        task_id, immediate_page = await self.generate_broker_report(
            account_id, from_dt=from_dt, to_dt=to_dt
        )
        if not task_id:
            log.warning(
                "broker_report_no_task_id",
                extra={"account_id": account_id},
            )
            return []

        # AU10 finding: для маленьких отчётов SDK сразу возвращает первую
        # страницу в том же RPC что и generate. Не делаем лишний RPC.
        first_rows: list[BrokerReportTradeRow] = []
        pages_count = 0
        if immediate_page is not None:
            rows_raw = (
                getattr(immediate_page, "broker_report", None)
                or getattr(immediate_page, "items", None)
                or []
            )
            first_rows = [broker_report_trade_from_proto(r) for r in rows_raw]
            pages_count = int(
                getattr(immediate_page, "pagesCount", None)
                or getattr(immediate_page, "pages_count", 0)
                or 0
            )

        # Polling первой страницы — только если SDK не вернул сразу.
        # Сигналы что отчёт ещё генерируется (любого из них достаточно):
        #   - текст "not_ready" / "not ready" в exception (legacy SDK)
        #   - T-Bank API error code 30058 (REPORT_GENERATION_IN_PROGRESS / NOT_READY)
        if pages_count == 0:
            for attempt_idx in range(max_poll_attempts):
                try:
                    first_rows, _, pages_count = await self.fetch_broker_report_page(
                        task_id, page=0
                    )
                    if pages_count > 0:
                        break
                except BrokerError as exc:
                    msg = str(exc).lower()
                    is_not_ready = (
                        "not_ready" in msg
                        or "not ready" in msg
                        or "30058" in msg
                        or "broker_report_in_progress" in msg
                    )
                    if is_not_ready:
                        log.debug(
                            "broker_report_not_ready",
                            extra={
                                "task_id": task_id,
                                "attempt": attempt_idx,
                                "code_hint": msg[:80],
                            },
                        )
                    else:
                        raise
                sleep_s = _POLL_BACKOFF[min(attempt_idx, len(_POLL_BACKOFF) - 1)]
                await asyncio.sleep(sleep_s)
            else:
                log.warning(
                    "broker_report_timeout",
                    extra={"account_id": account_id, "task_id": task_id},
                )
                return []

        all_rows: list[BrokerReportTradeRow] = list(first_rows)
        # Остальные страницы (page 1..pages_count-1)
        for page in range(1, min(pages_count, page_size_limit)):
            rows, _, _ = await self.fetch_broker_report_page(task_id, page=page)
            all_rows.extend(rows)
        log.info(
            "broker_report_fetched",
            extra={
                "account_id": account_id,
                "trades": len(all_rows),
                "pages": pages_count,
            },
        )
        return all_rows

    async def get_dividends_foreign_issuer(
        self,
        account_id: str,
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[dict[str, Any]]:
        """Отчёт по дивидендам иностранных эмитентов (NDFL ground truth).

        Это **независимый** источник истины по withheld tax — то, что Tinkoff
        реально удержал и перечислил в ФНС. Используется для cross-check
        наших расчётов NDFL в reconciliation_service (метрика #6).

        Возвращает raw dict'ы — конкретный mapper будет в reconciliation_service.
        """
        from t_tech.invest.schemas import GetDividendsForeignIssuerRequest

        request = GetDividendsForeignIssuerRequest(
            account_id=account_id,
            from_=from_dt,
            to=to_dt,
        )

        async def _call():
            return await self._guarded(
                self._svc.limiter,
                self._svc.operations.get_dividends_foreign_issuer(request),
            )

        async for attempt in _retry_policy():
            with attempt:
                response = await _call()
                # T-API ответ: либо .dividends_foreign_issuer_report (list)
                # либо отдельная подгенерация через task_id. У большинства
                # SDK версий это прямой ответ.
                rows = getattr(response, "dividends_foreign_issuer_report", None) or []
                # Конвертим в dict для гибкости (mapper выберет в service слое).
                result: list[dict[str, Any]] = []
                for r in rows:
                    result.append({
                        "record_date": getattr(r, "record_date", None),
                        "payment_date": getattr(r, "payment_date", None),
                        "security_name": getattr(r, "security_name", None),
                        "isin": getattr(r, "isin", None),
                        "issuer_country": getattr(r, "issuer_country", None),
                        "quantity": getattr(r, "quantity", 0) or 0,
                        "dividend": getattr(r, "dividend", None),
                        "dividend_gross": getattr(r, "dividend_gross", None),
                        "external_commission": getattr(r, "external_commission", None),
                        "tax": getattr(r, "tax", None),
                        "dividend_amount": getattr(r, "dividend_amount", None),
                    })
                return result
        return []

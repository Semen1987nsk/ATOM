"""
Маппинг ошибок Tinkoff SDK / gRPC → domain-исключения.

Все клиенты (`*_client.py`) оборачивают свои вызовы через `wrap_sdk_errors()`
context manager, чтобы выше по стеку видели только `domain.exceptions.*`.

Классификация (см. `domain/exceptions.py`):

| gRPC StatusCode      | Domain exception          | Retryable |
| -------------------- | ------------------------- | --------- |
| UNAUTHENTICATED      | TokenInvalid              | no        |
| PERMISSION_DENIED    | TokenScopeInsufficient    | no        |
| NOT_FOUND            | InstrumentNotFound        | no        |
| INVALID_ARGUMENT     | OperationParseError       | no        |
| RESOURCE_EXHAUSTED   | RateLimitExceeded         | yes       |
| UNAVAILABLE          | BrokerUnavailable         | yes       |
| DEADLINE_EXCEEDED    | BrokerUnavailable         | yes       |
| (anything else)      | BrokerError               | no        |

SDK-исключения (`tinkoff.invest.exceptions.AioRequestError` и т.п.) имеют
поле `.code` (типа `grpc.StatusCode`) и `.details` (строка). Async и sync
варианты обрабатываем одинаково через MRO-совпадение по `InvestError`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import grpc

from domain.exceptions import (
    BrokerError,
    BrokerUnavailable,
    InstrumentNotFound,
    OperationParseError,
    RateLimitExceeded,
    TokenInvalid,
    TokenScopeInsufficient,
)


# Маппинг StatusCode → класс domain-исключения. Берём по `.value[0]`
# (числовой код) или по самому StatusCode — в `RequestError.code` SDK
# кладёт enum-значение.
_STATUS_TO_EXCEPTION: dict[grpc.StatusCode, type[BrokerError]] = {
    grpc.StatusCode.UNAUTHENTICATED: TokenInvalid,
    grpc.StatusCode.PERMISSION_DENIED: TokenScopeInsufficient,
    grpc.StatusCode.NOT_FOUND: InstrumentNotFound,
    grpc.StatusCode.INVALID_ARGUMENT: OperationParseError,
    grpc.StatusCode.RESOURCE_EXHAUSTED: RateLimitExceeded,
    grpc.StatusCode.UNAVAILABLE: BrokerUnavailable,
    grpc.StatusCode.DEADLINE_EXCEEDED: BrokerUnavailable,
}


def map_sdk_error(exc: BaseException) -> BrokerError:
    """Превратить любую SDK/gRPC ошибку в domain-исключение."""
    code = getattr(exc, "code", None)
    details = getattr(exc, "details", None) or str(exc)

    # `.code` может быть enum или callable (у grpc.RpcError — метод).
    if callable(code):
        try:
            code = code()
        except Exception:
            code = None

    if isinstance(code, grpc.StatusCode):
        target_cls = _STATUS_TO_EXCEPTION.get(code, BrokerError)
        return target_cls(message=str(details), code=code.name)

    # Не gRPC-ошибка (например, network timeout до открытия канала, JSON
    # parse в стриминге). Считаем сетевой проблемой → retryable.
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return BrokerUnavailable(message=str(details), code=type(exc).__name__)

    # Tinkoff SDK имеет UnauthenticatedError / AioUnauthenticatedError
    # как отдельные классы (без StatusCode). Разворачиваем по имени.
    name = type(exc).__name__
    if "Unauthenticated" in name:
        return TokenInvalid(message=str(details), code=name)

    return BrokerError(message=str(details), code=name)


@contextmanager
def wrap_sdk_errors() -> Iterator[None]:
    """
    Context manager: ловит все низкоуровневые исключения и поднимает
    domain-варианты.

    Использование в клиентах::

        async def fetch_operations_cursor(...):
            with wrap_sdk_errors():
                response = await self._svc.operations.get_operations_by_cursor(req)
            ...

    NB: `domain.exceptions.BrokerError` пропускаем как есть (already mapped),
    чтобы не делать двойную обёртку при вложенных вызовах.
    """
    try:
        yield
    except BrokerError:
        raise
    except BaseException as exc:
        # Не ловим KeyboardInterrupt / SystemExit — они BaseException, но
        # не Exception. Catching BaseException опасно; делаем re-raise.
        if not isinstance(exc, Exception):
            raise
        raise map_sdk_error(exc) from exc

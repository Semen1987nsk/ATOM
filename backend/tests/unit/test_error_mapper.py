"""
Unit-тесты `adapters.tinkoff.error_mapper`. Проверяем:

* gRPC StatusCode корректно мапятся в правильные domain-исключения,
* `retryable` флаг проставлен правильно,
* нестандартные ошибки (TimeoutError) уходят в `BrokerUnavailable`,
* `wrap_sdk_errors()` не оборачивает уже-domain исключения дважды.
"""

from __future__ import annotations

import pytest
import grpc

from adapters.tinkoff.error_mapper import map_sdk_error, wrap_sdk_errors
from domain.exceptions import (
    BrokerError,
    BrokerUnavailable,
    InstrumentNotFound,
    OperationParseError,
    RateLimitExceeded,
    TokenInvalid,
    TokenScopeInsufficient,
)


class _FakeRpcError(Exception):
    """Имитация AioRequestError из tinkoff-investments SDK."""

    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


@pytest.mark.parametrize(
    "status_code,expected_cls,retryable",
    [
        (grpc.StatusCode.UNAUTHENTICATED, TokenInvalid, False),
        (grpc.StatusCode.PERMISSION_DENIED, TokenScopeInsufficient, False),
        (grpc.StatusCode.NOT_FOUND, InstrumentNotFound, False),
        (grpc.StatusCode.INVALID_ARGUMENT, OperationParseError, False),
        (grpc.StatusCode.RESOURCE_EXHAUSTED, RateLimitExceeded, True),
        (grpc.StatusCode.UNAVAILABLE, BrokerUnavailable, True),
        (grpc.StatusCode.DEADLINE_EXCEEDED, BrokerUnavailable, True),
    ],
)
def test_map_known_status_codes(
    status_code: grpc.StatusCode, expected_cls: type[BrokerError], retryable: bool
) -> None:
    err = _FakeRpcError(status_code, "test")
    mapped = map_sdk_error(err)
    assert isinstance(mapped, expected_cls)
    assert mapped.retryable is retryable
    assert mapped.code == status_code.name


def test_map_unknown_status_code_to_broker_error() -> None:
    err = _FakeRpcError(grpc.StatusCode.ABORTED, "weird")
    mapped = map_sdk_error(err)
    # Неизвестный статус → generic BrokerError, не retryable.
    assert isinstance(mapped, BrokerError)
    # Не является более специфичным подклассом.
    assert not isinstance(mapped, (TokenInvalid, RateLimitExceeded, BrokerUnavailable))


def test_map_timeout_error_is_retryable() -> None:
    mapped = map_sdk_error(TimeoutError("connection timed out"))
    assert isinstance(mapped, BrokerUnavailable)
    assert mapped.retryable is True


def test_map_connection_error_is_retryable() -> None:
    mapped = map_sdk_error(ConnectionError("connection refused"))
    assert isinstance(mapped, BrokerUnavailable)
    assert mapped.retryable is True


def test_map_unauthenticated_error_by_class_name() -> None:
    """SDK поднимает AioUnauthenticatedError — без StatusCode, по имени."""

    class AioUnauthenticatedError(Exception):
        pass

    mapped = map_sdk_error(AioUnauthenticatedError("invalid token"))
    assert isinstance(mapped, TokenInvalid)


def test_wrap_sdk_errors_translates() -> None:
    """`wrap_sdk_errors` ловит SDK ошибки и поднимает domain."""
    with pytest.raises(RateLimitExceeded):
        with wrap_sdk_errors():
            raise _FakeRpcError(grpc.StatusCode.RESOURCE_EXHAUSTED, "limit")


def test_wrap_sdk_errors_does_not_double_wrap() -> None:
    """Если уже domain — пробрасываем как есть."""
    original = TokenInvalid("already mapped")
    with pytest.raises(TokenInvalid) as exc_info:
        with wrap_sdk_errors():
            raise original
    assert exc_info.value is original


def test_wrap_sdk_errors_lets_keyboard_interrupt_through() -> None:
    """KeyboardInterrupt (BaseException) не должен оборачиваться."""
    with pytest.raises(KeyboardInterrupt):
        with wrap_sdk_errors():
            raise KeyboardInterrupt()


def test_callable_code_is_evaluated() -> None:
    """`grpc.RpcError.code()` — метод. Маппер должен это понять."""

    class _RpcErrorWithCallableCode(Exception):
        def code(self) -> grpc.StatusCode:
            return grpc.StatusCode.UNAUTHENTICATED

        def details(self) -> str:
            return "invalid token"

    mapped = map_sdk_error(_RpcErrorWithCallableCode())
    assert isinstance(mapped, TokenInvalid)

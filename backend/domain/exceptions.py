"""
Иерархия domain-исключений для Tinkoff-интеграции.

Все ошибки внешнего мира (gRPC статусы, network failures, HTTP ошибки)
маппятся в эти типы в `adapters/tinkoff/error_mapper.py`. Application-слой
ловит только их, никогда — низкоуровневые `grpc.RpcError` или `httpx.HTTPError`.

Деление на retryable/non-retryable нужно для tenacity (см. PR 15) и для
circuit breaker'а: 5 подряд `BrokerUnavailable`/`RateLimitExceeded` ставят
токен в `circuit_open_until = now + 15min`.
"""

from __future__ import annotations


class BrokerError(Exception):
    """Базовый класс всех ошибок взаимодействия с брокером."""

    retryable: bool = False

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def __repr__(self) -> str:  # для логов
        return f"{type(self).__name__}(message={self.message!r}, code={self.code!r})"


# ── Не-retryable: ошибки токена / прав / параметров ──


class TokenInvalid(BrokerError):
    """Токен невалиден, отозван или просрочен (gRPC UNAUTHENTICATED).

    Реакция: деактивировать `BrokerConnection.is_active=False`, уведомить
    пользователя email/in-app.
    """

    retryable = False


class TokenScopeInsufficient(BrokerError):
    """Токен валиден, но не имеет нужных прав (gRPC PERMISSION_DENIED).

    Например, у read-only токена нет доступа к OperationsService для
    конкретного аккаунта. Не путать с `TokenInvalid` — токен живой,
    просто ограничен.
    """

    retryable = False


class InstrumentNotFound(BrokerError):
    """Инструмент не найден (gRPC NOT_FOUND).

    Возникает при запросе по UID/FIGI, которого нет в справочнике
    Тинькофф (например, делистинг). Сохранить операцию с пометкой
    `data_source='tinkoff_v2'` всё равно надо, но instrument-кэш не
    пополняем.
    """

    retryable = False


class OperationParseError(BrokerError):
    """Не удалось распарсить ответ API (gRPC INVALID_ARGUMENT, malformed proto).

    Чаще всего — рассинхронизация версии SDK с серверной стороной.
    Логируем, не повторяем (повтор не поможет), уходим в DLQ для ручного
    разбора (PR 14+).
    """

    retryable = False


# ── Retryable: транзиентные сбои ──


class BrokerUnavailable(BrokerError):
    """Сервис временно недоступен (gRPC UNAVAILABLE / DEADLINE_EXCEEDED).

    Реакция: tenacity retry с exponential backoff + jitter (PR 15).
    После 5 подряд — circuit breaker открывается.
    """

    retryable = True


class RateLimitExceeded(BrokerError):
    """Превышен лимит запросов (gRPC RESOURCE_EXHAUSTED).

    Возникает при попытке обойти aiolimiter (например, два процесса
    делят один токен) или при динамическом понижении grade'а пользователя.

    Реакция: backoff на 60 секунд минимум, потом retry.
    """

    retryable = True


class CircuitBreakerOpen(BrokerError):
    """Circuit breaker открыт — синхронизация для этого токена приостановлена.

    Возникает в orchestrator'е (PR 5+15), когда `BrokerConnection.circuit_open_until > now`.
    Сам по себе не retryable — нужно либо подождать reset_timeout,
    либо явно сбросить через UI.
    """

    retryable = False

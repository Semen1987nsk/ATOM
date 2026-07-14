"""
TinkoffClientFactory — единственная точка создания gRPC-клиентов к T-Invest API.

Оборачивает официальный SDK `tinkoff-investments` (Tinkoff/invest-python) так,
чтобы выше по стеку никто не знал про SDK напрямую: верхний код держит
`async with factory.async_client(token)` и вызывает SDK через context manager.

Ключевые принципы (см. план PR 1 / PR 3):

* sandbox vs prod определяется `settings.TINKOFF_API_ENV` (по умолчанию prod).
* Per-token aiolimiter (`TINKOFF_RATE_LIMIT_PER_MIN`, default 150/min) — запас
  от официального лимита 200/min на Operations. Один лимитер на токен,
  переиспользуется через dict (бессрочно — масштаб ≤ thousands of tokens,
  memory cost ~200B/limiter).
* AU1 fix: лимитер срабатывает на КАЖДЫЙ RPC, не только при открытии клиента.
  Раньше `async with limiter` оборачивал лишь `AsyncClient(...)` open;
  последующие RPC внутри `yield` шли без throttling — на 1000 юзеров это
  выжигало лимит T-Bank API за секунды. Теперь yielded объект — обёртка
  `RateLimitedServices`, у которой есть `.limiter` attribute, и каждый клиент
  (TinkoffOperationsClient, TinkoffUsersClient, TinkoffInstrumentsClient)
  оборачивает каждый RPC через `async with self._svc.limiter:`.
* App name отправляется в gRPC metadata (`TINKOFF_APP_NAME`) — Тинькофф
  использует это для аналитики grade и issue-репортов.
* Все ошибки наружу — RPC-исключения SDK; маппинг в domain-исключения
  делается в `error_mapper.py` (PR 3).

Сам экземпляр SDK-клиента создаётся через context manager, так что фабрика
не держит долгоживущих gRPC-каналов. Это упрощает unit-тестирование (легко
патчить) и снимает риск утечки соединений при отключении пользователя.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from adapters.tinkoff.grpc_rate_limiter import (
    SharedRateLimiter,
    build_token_bucket_backend,
    token_key,
)
from config import settings
from logger import get_logger

log = get_logger("tinkoff.client_factory")


class RateLimitedServices:
    """Wrapper над SDK `services` объектом с дополнительными limiter-атрибутами.

    Прозрачно прокидывает обращения к `services.users`, `services.operations`,
    `services.instruments` и т.д. Клиенты-обёртки (TinkoffOperationsClient и пр.)
    обязаны брать `self._svc.limiter` token перед каждым RPC, иначе мы
    регрессируем на оригинальный AU1 баг.

    AU2: отдельный `broker_report_limiter` для `GenerateBrokerReport` /
    `GetBrokerReport`, у которых официальный лимит 5/min — намного жёстче
    обычного OperationsService лимита 200/min.
    """

    __slots__ = ("_services", "limiter", "broker_report_limiter")

    def __init__(
        self,
        services: Any,
        limiter: SharedRateLimiter,
        broker_report_limiter: SharedRateLimiter,
    ) -> None:
        self._services = services
        self.limiter = limiter
        self.broker_report_limiter = broker_report_limiter

    def __getattr__(self, name: str) -> Any:
        # __getattr__ вызывается только если атрибут не найден через __slots__,
        # т.е. для users / operations / instruments / sandbox / market_data etc.
        return getattr(self._services, name)


class TinkoffClientFactory:
    """
    Создаёт асинхронные клиенты к T-Invest API с правильным endpoint'ом
    и per-token rate-limit'ом.

    Использование (PR 3+):

        factory = TinkoffClientFactory()
        async with factory.async_client(token) as services:
            # services.limiter — единый per-token leaky-bucket
            # клиенты-обёртки внутри RPC делают `async with services.limiter:`
            ops_client = TinkoffOperationsClient(services)
            ops = await ops_client.fetch_operations_cursor(account_id)
    """

    def __init__(self) -> None:
        # SYNC-02: ОДИН общий backend на процесс. SharedRateLimiter'ы stateless
        # (состояние в backend/Redis), поэтому per-token dict больше не нужен —
        # нет утечки лимитеров на токен.
        self._backend = build_token_bucket_backend()

    def _limiter_for(self, token: str, *, kind: str) -> SharedRateLimiter:
        """SharedRateLimiter для (token, kind). kind ∈ {'ops','broker_report'}."""
        if kind == "broker_report":
            rate = settings.TINKOFF_BROKER_REPORT_RATE_LIMIT_PER_MIN
        else:
            rate = settings.TINKOFF_RATE_LIMIT_PER_MIN
        return SharedRateLimiter(
            self._backend,
            key=token_key(token, kind=kind),
            rate=rate,
            period=60,
            max_wait=settings.TINKOFF_LIMITER_MAX_WAIT_SECONDS,
        )

    @property
    def endpoint(self) -> str:
        """Возвращает gRPC endpoint в зависимости от TINKOFF_API_ENV."""
        if settings.TINKOFF_API_ENV == "sandbox":
            return settings.TINKOFF_SANDBOX_ENDPOINT
        return settings.TINKOFF_API_ENDPOINT

    @property
    def is_sandbox(self) -> bool:
        return settings.TINKOFF_API_ENV == "sandbox"

    @asynccontextmanager
    async def async_client(self, token: str) -> AsyncIterator[RateLimitedServices]:
        """
        Открывает async-клиент к T-Invest API. Yields `RateLimitedServices`
        с per-token `.limiter` атрибутом — throttling делают сами клиенты-
        обёртки в каждом RPC.

        Импорт SDK ленивый: пакет `tinkoff-investments` подключается только
        при реальном использовании, чтобы dev-окружение могло поднимать
        backend без него (для тестов, не зависящих от gRPC).
        """
        # Поздний импорт: keeps fastapi import-time чистым.
        # AU10: SDK переименован tinkoff-investments → t-tech-investments,
        # namespace tinkoff.invest → t_tech.invest. AsyncClient signature
        # идентичен (token, *, target, sandbox_token, options, app_name, interceptors).
        from t_tech.invest import AsyncClient  # type: ignore

        limiter = self._limiter_for(token, kind="ops")
        broker_report_limiter = self._limiter_for(token, kind="broker_report")
        target = self.endpoint
        app_name = settings.TINKOFF_APP_NAME

        log.debug(
            "tinkoff.async_client.open",
            extra={"endpoint": target, "sandbox": self.is_sandbox, "app_name": app_name},
        )

        async with AsyncClient(token, target=target, app_name=app_name) as client:
            yield RateLimitedServices(client, limiter, broker_report_limiter)


# Единственный фабричный синглтон процесса. Можно безопасно импортировать
# из любого места — состояние ограничивается dict с лимитерами.
client_factory = TinkoffClientFactory()

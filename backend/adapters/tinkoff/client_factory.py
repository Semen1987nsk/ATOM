"""
TinkoffClientFactory — единственная точка создания gRPC-клиентов к T-Invest API.

Оборачивает официальный SDK `tinkoff-investments` (Tinkoff/invest-python) так,
чтобы выше по стеку никто не знал про SDK напрямую: верхний код держит
`async with factory.async_client(token)` и вызывает SDK через context manager.

Ключевые принципы (см. план PR 1 / PR 3):

* sandbox vs prod определяется `settings.TINKOFF_API_ENV` (по умолчанию prod).
* Per-token aiolimiter (`TINKOFF_RATE_LIMIT_PER_MIN`, default 60/min) — запас
  от официального лимита 200/min на Operations. Один лимитер на токен,
  переиспользуется через WeakValueDictionary, чтобы не плодить bucket'ы.
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
from typing import AsyncIterator

from aiolimiter import AsyncLimiter

from config import settings
from logger import get_logger

log = get_logger("tinkoff.client_factory")


class TinkoffClientFactory:
    """
    Создаёт асинхронные клиенты к T-Invest API с правильным endpoint'ом
    и per-token rate-limit'ом.

    Использование (PR 3+):

        factory = TinkoffClientFactory()
        async with factory.async_client(token) as client:
            accounts = await client.users.get_accounts()
    """

    def __init__(self) -> None:
        # Каждый токен — свой leaky-bucket лимитер.
        # Обычный dict (а не WeakValueDictionary): `aiolimiter.AsyncLimiter`
        # использует __slots__ без __weakref__, и weakref на него вызовет
        # TypeError. На текущем масштабе (десятки активных токенов в памяти)
        # утечки нет; при подключении к Redis (см. план) лимит уедет
        # вообще из процесса.
        self._limiters: dict[str, AsyncLimiter] = {}

    @property
    def endpoint(self) -> str:
        """Возвращает gRPC endpoint в зависимости от TINKOFF_API_ENV."""
        if settings.TINKOFF_API_ENV == "sandbox":
            return settings.TINKOFF_SANDBOX_ENDPOINT
        return settings.TINKOFF_API_ENDPOINT

    @property
    def is_sandbox(self) -> bool:
        return settings.TINKOFF_API_ENV == "sandbox"

    def _get_limiter(self, token: str) -> AsyncLimiter:
        """Возвращает (или создаёт) per-token leaky-bucket."""
        limiter = self._limiters.get(token)
        if limiter is None:
            # AsyncLimiter(max_rate, time_period). 60 req per 60 sec.
            limiter = AsyncLimiter(
                max_rate=settings.TINKOFF_RATE_LIMIT_PER_MIN,
                time_period=60,
            )
            self._limiters[token] = limiter
        return limiter

    @asynccontextmanager
    async def async_client(self, token: str) -> AsyncIterator[object]:
        """
        Открывает async-клиент к T-Invest API, держит rate-limit на токене.

        Импорт SDK ленивый: пакет `tinkoff-investments` подключается только
        при реальном использовании, чтобы dev-окружение могло поднимать
        backend без него (для тестов, не зависящих от gRPC).
        """
        # Поздний импорт: keeps fastapi import-time чистым.
        from tinkoff.invest import AsyncClient  # type: ignore

        limiter = self._get_limiter(token)
        target = self.endpoint
        app_name = settings.TINKOFF_APP_NAME

        log.debug(
            "tinkoff.async_client.open",
            extra={"endpoint": target, "sandbox": self.is_sandbox, "app_name": app_name},
        )

        async with limiter:
            async with AsyncClient(token, target=target, app_name=app_name) as client:
                yield client


# Единственный фабричный синглтон процесса. Можно безопасно импортировать
# из любого места — состояние ограничивается WeakValueDictionary с лимитерами.
client_factory = TinkoffClientFactory()

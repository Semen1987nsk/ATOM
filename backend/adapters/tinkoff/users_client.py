"""
TinkoffUsersClient — `services.users.*`.

Используется для:

* Валидации токена (PR 4 + PR 12) — `get_accounts()` echo-вызов при
  подключении нового токена. Если падает — токен невалиден; если
  возвращает аккаунты с `access_level=NO_ACCESS` — scope недостаточный.
* Read-only scope check (PR 12) — анализируем `access_level` каждого
  аккаунта, отказываем в подключении если нет хотя бы READ_ONLY.
* Tracking grade (PR 16) — `get_user_tariff()` отдаёт текущие лимиты
  пользователя; полезно для observability.
"""

from __future__ import annotations

from typing import Any

from logger import get_logger

from adapters.tinkoff.error_mapper import wrap_sdk_errors

log = get_logger("tinkoff.users_client")


class TinkoffAccountInfo:
    """Простой DTO для эндпоинтов /broker/connect (PR 12)."""

    __slots__ = ("id", "name", "type", "status", "access_level", "opened_date")

    def __init__(
        self,
        *,
        id: str,
        name: str,
        type: str,
        status: str,
        access_level: str,
        opened_date: Any = None,
    ) -> None:
        self.id = id
        self.name = name
        self.type = type
        self.status = status
        self.access_level = access_level
        self.opened_date = opened_date

    @property
    def is_read_only_or_better(self) -> bool:
        """READ_ONLY и FULL_ACCESS — оба позволяют читать операции."""
        return self.access_level in (
            "ACCOUNT_ACCESS_LEVEL_READ_ONLY",
            "ACCOUNT_ACCESS_LEVEL_FULL_ACCESS",
        )

    @property
    def is_strictly_read_only(self) -> bool:
        """Только read-only, без trading прав. Это что просим у юзера в PR 13."""
        return self.access_level == "ACCOUNT_ACCESS_LEVEL_READ_ONLY"


def _enum_name(value: Any) -> str:
    return getattr(value, "name", None) or str(value)


class TinkoffUsersClient:
    def __init__(self, services: Any) -> None:
        self._svc = services

    async def list_accounts(self) -> list[TinkoffAccountInfo]:
        """Список доступных аккаунтов с access_level (для валидации scope)."""
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                response = await self._svc.users.get_accounts()

        result: list[TinkoffAccountInfo] = []
        for acc in getattr(response, "accounts", []) or []:
            result.append(
                TinkoffAccountInfo(
                    id=getattr(acc, "id", "") or "",
                    name=getattr(acc, "name", "") or "",
                    type=_enum_name(getattr(acc, "type", "")),
                    status=_enum_name(getattr(acc, "status", "")),
                    access_level=_enum_name(getattr(acc, "access_level", "")),
                    opened_date=getattr(acc, "opened_date", None),
                )
            )
        return result

    async def get_user_tariff_raw(self) -> Any:
        """
        Сырой `GetUserTariffResponse`. Содержит unary_limits (RPS на
        методах) и stream_limits (лимит open streams). Сейчас (PR 3) не
        парсим — используется в observability (PR 16) для алертов.
        """
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                return await self._svc.users.get_user_tariff()

    async def get_info_raw(self) -> Any:
        # AU1: per-RPC rate-limit gate
        async with self._svc.limiter:
            with wrap_sdk_errors():
                return await self._svc.users.get_info()

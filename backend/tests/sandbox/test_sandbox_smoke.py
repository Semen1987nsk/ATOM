"""
Sandbox smoke (PR 14).

Минимальный e2e против реального sandbox API: открыть sandbox-аккаунт,
пополнить, запросить операции через наш adapter, удалить аккаунт.

Тест skip-ается без `TINKOFF_SANDBOX_TOKEN_TEST`. Это РЕАЛЬНЫЙ
сетевой вызов — не запускать в обычном CI, только когда явно проверяете
интеграцию.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone

import pytest


def _sdk_installed() -> bool:
    return importlib.util.find_spec("tinkoff.invest") is not None


def _sandbox_token() -> str | None:
    return os.getenv("TINKOFF_SANDBOX_TOKEN_TEST")


pytestmark = [
    pytest.mark.skipif(not _sdk_installed(), reason="tinkoff-investments SDK not installed"),
    pytest.mark.skipif(not _sandbox_token(), reason="TINKOFF_SANDBOX_TOKEN_TEST not set"),
]


@pytest.mark.asyncio
async def test_sandbox_open_account_and_fetch_operations(monkeypatch) -> None:
    """
    Полный sandbox-цикл:
    1. Открыть sandbox-аккаунт (через нативный SDK — наш adapter не имеет
       sandbox-методов).
    2. Пополнить 1М RUB.
    3. Через наш `TinkoffOperationsClient.fetch_operations_cursor` запросить
       операции.
    4. Закрыть sandbox-аккаунт.
    """
    monkeypatch.setenv("TINKOFF_API_ENV", "sandbox")

    from tinkoff.invest import AsyncClient
    from tinkoff.invest.schemas import GetOperationsByCursorRequest, MoneyValue as PbMoney

    from adapters.tinkoff.client_factory import TinkoffClientFactory
    from adapters.tinkoff.operations_client import TinkoffOperationsClient

    token = _sandbox_token()
    assert token

    # 1. Открыть sandbox-аккаунт через native SDK.
    async with AsyncClient(
        token, target="sandbox-invest-public-api.tinkoff.ru:443", app_name="eqio.smoke"
    ) as client:
        open_response = await client.sandbox.open_sandbox_account()
        account_id = open_response.account_id

        try:
            # 2. Пополнить.
            await client.sandbox.sandbox_pay_in(
                account_id=account_id,
                amount=PbMoney(currency="rub", units=1_000_000, nano=0),
            )

            # 3. Запросить операции через наш adapter.
            factory = TinkoffClientFactory()
            assert factory.is_sandbox, "factory must be in sandbox mode"
            async with factory.async_client(token) as services:
                ops_client = TinkoffOperationsClient(services)
                operations, cursor = await ops_client.fetch_operations_cursor(
                    account_id, limit=100
                )

            # PayIn от шага 2 должен быть в списке.
            assert isinstance(operations, list)
            assert any(
                op.operation_type.value == "input" for op in operations
            ), f"expected INPUT op among {[o.operation_type.value for o in operations]}"
        finally:
            # 4. Гарантированно закрыть sandbox-аккаунт (даже при failure).
            await client.sandbox.close_sandbox_account(account_id=account_id)


@pytest.mark.asyncio
async def test_sandbox_users_list_accounts_returns_at_least_one(monkeypatch) -> None:
    """`users.get_accounts()` через наш adapter возвращает sandbox-аккаунт."""
    monkeypatch.setenv("TINKOFF_API_ENV", "sandbox")

    from tinkoff.invest import AsyncClient

    from adapters.tinkoff.client_factory import TinkoffClientFactory
    from adapters.tinkoff.users_client import TinkoffUsersClient

    token = _sandbox_token()
    assert token

    # Откроем sandbox-аккаунт чтобы было что вернуть.
    async with AsyncClient(
        token, target="sandbox-invest-public-api.tinkoff.ru:443", app_name="eqio.smoke"
    ) as native:
        opened = await native.sandbox.open_sandbox_account()
        try:
            factory = TinkoffClientFactory()
            async with factory.async_client(token) as services:
                users = TinkoffUsersClient(services)
                accounts = await users.list_accounts()
            assert len(accounts) >= 1
            assert any(a.id == opened.account_id for a in accounts)
        finally:
            await native.sandbox.close_sandbox_account(account_id=opened.account_id)

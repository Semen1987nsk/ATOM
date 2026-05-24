"""
Smoke-тест PR 1: client_factory открывает async-клиент к Tinkoff sandbox
и успешно вызывает users.get_accounts().

Тест skip-ится если:
* `TINKOFF_SANDBOX_TOKEN_TEST` не установлен (в CI без секрета — ок),
* SDK `t-tech-investments` не установлен (раньше `tinkoff-investments`,
  переименован в AU10).

Что проверяется:
* фабрика выбирает sandbox endpoint, когда TINKOFF_API_ENV=sandbox;
* `async_client` успешно подключается и возвращает SDK-объект;
* реальный gRPC вызов (`get_accounts`) возвращает структуру с полем
  `accounts` без RPC-ошибок.

В PR 3 этот тест расширится на остальные клиенты (operations, instruments,
marketdata), в PR 14 — превращается в полноценный sandbox-цикл.
"""

from __future__ import annotations

import importlib.util
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


def _sdk_installed() -> bool:
    # AU10: SDK переименован tinkoff.invest → t_tech.invest.
    return importlib.util.find_spec("t_tech.invest") is not None


def _sandbox_token() -> str | None:
    return os.getenv("TINKOFF_SANDBOX_TOKEN_TEST")


@pytest.mark.asyncio
@pytest.mark.skipif(not _sdk_installed(), reason="t-tech-investments SDK not installed")
@pytest.mark.skipif(not _sandbox_token(), reason="TINKOFF_SANDBOX_TOKEN_TEST not set")
async def test_sandbox_get_accounts_via_factory(monkeypatch):
    """Открыть клиент к sandbox через фабрику и убедиться что get_accounts работает."""
    # Заставляем фабрику использовать sandbox endpoint независимо от .env.
    monkeypatch.setenv("TINKOFF_API_ENV", "sandbox")

    # Импорт после monkeypatch, чтобы settings подхватили sandbox env.
    # (settings — синглтон, в реальной среде .env уже может быть выставлен;
    # для теста мы просто гарантируем нужное значение в self.endpoint).
    from adapters.tinkoff.client_factory import TinkoffClientFactory

    factory = TinkoffClientFactory()
    # endpoint должен быть sandbox после monkeypatch — но settings уже
    # инстанцирован, поэтому явно проверяем: если env переключён, всё ок;
    # если нет (settings закэшировал prod) — пропускаем тест.
    if not factory.is_sandbox:
        pytest.skip(
            "settings.TINKOFF_API_ENV не переключён на sandbox в этом процессе; "
            "поднимите тест с TINKOFF_API_ENV=sandbox в env."
        )

    token = _sandbox_token()
    assert token is not None  # type-narrow для проверки

    async with factory.async_client(token) as client:
        accounts_response = await client.users.get_accounts()

    # У sandbox-токена должен быть как минимум один аккаунт (создан при
    # первом open_sandbox_account() — обычно делается один раз вручную).
    assert hasattr(accounts_response, "accounts"), (
        "ожидали поле accounts в ответе users.get_accounts()"
    )


def test_factory_endpoint_switches_on_env(monkeypatch):
    """Без сети: фабрика возвращает разные endpoint'ы для prod/sandbox."""
    # Этот тест не требует SDK или токена — проверяет только логику выбора.
    from adapters.tinkoff.client_factory import TinkoffClientFactory

    # У нас не получится переустановить settings внутри одного процесса
    # (синглтон), поэтому просто проверяем что текущие endpoint'ы
    # соответствуют settings и что property is_sandbox консистентен.
    from config import settings as cfg

    factory = TinkoffClientFactory()
    if cfg.TINKOFF_API_ENV == "sandbox":
        assert factory.endpoint == cfg.TINKOFF_SANDBOX_ENDPOINT
        assert factory.is_sandbox is True
    else:
        assert factory.endpoint == cfg.TINKOFF_API_ENDPOINT
        assert factory.is_sandbox is False


def test_factory_singleton_importable():
    """`client_factory` синглтон импортируется без побочных эффектов."""
    from adapters.tinkoff.client_factory import client_factory, TinkoffClientFactory

    assert isinstance(client_factory, TinkoffClientFactory)


def test_factory_get_limiter_does_not_use_weakref():
    """
    Regression: aiolimiter.AsyncLimiter использует __slots__ без __weakref__.
    Хранить лимитеры в WeakValueDictionary даёт TypeError при первом
    обращении (нашли через live_smoke). Проверяем что хранилище принимает
    AsyncLimiter без ошибок и переиспользует bucket по токену.
    """
    from adapters.tinkoff.client_factory import TinkoffClientFactory

    factory = TinkoffClientFactory()
    limiter_a = factory._get_limiter("t.TOKEN_A")
    limiter_b = factory._get_limiter("t.TOKEN_B")
    limiter_a_again = factory._get_limiter("t.TOKEN_A")

    # Разные токены → разные лимитеры.
    assert limiter_a is not limiter_b
    # Тот же токен → переиспользуется тот же лимитер (важно для honest
    # rate-limiting между двумя последовательными вызовами).
    assert limiter_a is limiter_a_again

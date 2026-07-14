"""PERF-04: проверки async-обвязки services/moex_async.

Pytest-httpx может быть недоступен (NO-COMMIT mode у implementer'а). Чтобы
тесты были детерминированы и не лезли в сеть, мокаем httpx.AsyncClient.get
через monkeypatch — этого достаточно для проверки retry/singleton/fallback
семантики.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from services import moex_async


def _resp(status: int, json_data: dict | None = None, url: str = "https://x") -> httpx.Response:
    """Build httpx.Response с прицепленным request — иначе raise_for_status падает."""
    return httpx.Response(status, json=json_data, request=httpx.Request("GET", url))


@pytest.fixture(autouse=True)
def _reset_client_between_tests():
    """Чистим singleton перед/после каждого теста — иначе client из одного
    теста (с замоканным get) тащится в следующий.

    Sync fixture с asyncio.run, потому что в проекте нет asyncio_mode=auto
    и async-autouse не поддерживается."""
    asyncio.run(moex_async.close_client())
    yield
    asyncio.run(moex_async.close_client())


# ─── Singleton lifecycle ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_client_returns_singleton():
    """Повторный вызов get_client() возвращает тот же AsyncClient."""
    c1 = await moex_async.get_client()
    c2 = await moex_async.get_client()
    assert c1 is c2
    assert isinstance(c1, httpx.AsyncClient)


@pytest.mark.asyncio
async def test_close_client_recreates_on_next_get():
    """После close_client() следующий get_client() даёт новый instance."""
    c1 = await moex_async.get_client()
    await moex_async.close_client()
    assert c1.is_closed
    c2 = await moex_async.get_client()
    assert c2 is not c1
    assert not c2.is_closed


@pytest.mark.asyncio
async def test_close_client_idempotent():
    """Двойной close_client() не падает (например, если lifespan crash'нулся
    и shutdown вызвался дважды)."""
    await moex_async.get_client()
    await moex_async.close_client()
    await moex_async.close_client()  # no-op, не должно бросать


# ─── fetch_json семантика ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_json_returns_payload_on_200(monkeypatch):
    """Happy-path: 200 OK → возвращаем dict из json()."""
    payload = {"securities": {"columns": ["A"], "data": [["x"]]}}
    mock_get = AsyncMock(return_value=_resp(200, payload))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    result = await moex_async.fetch_json("https://iss.moex.com/x.json")

    assert result == payload
    assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_json_passes_params(monkeypatch):
    """params=... передаются в client.get как kwargs."""
    seen: list[dict] = []

    async def fake_get(self, url, params=None):
        seen.append({"url": url, "params": params})
        return _resp(200, {"ok": True}, url)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await moex_async.fetch_json(
        "https://iss.moex.com/y.json", params={"from": "2025-01-01"}
    )

    assert result == {"ok": True}
    assert seen == [{"url": "https://iss.moex.com/y.json", "params": {"from": "2025-01-01"}}]


@pytest.mark.asyncio
async def test_fetch_json_retries_on_http_error_then_succeeds(monkeypatch):
    """5xx первой попытки → ретрай → 200. Должны увидеть payload."""
    calls = {"n": 0}

    async def fake_get(self, url, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _resp(503, url=url)
        return _resp(200, {"recovered": True}, url)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(moex_async.asyncio, "sleep", AsyncMock())

    result = await moex_async.fetch_json("https://iss.moex.com/z.json")

    assert result == {"recovered": True}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_fetch_json_returns_none_after_all_retries_fail(monkeypatch):
    """Все 3 попытки упали → None (не бросаем исключение наружу)."""
    calls = {"n": 0}

    async def fake_get(self, url, params=None):
        calls["n"] += 1
        return _resp(503, url=url)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(moex_async.asyncio, "sleep", AsyncMock())

    result = await moex_async.fetch_json("https://iss.moex.com/fail.json", retries=2)

    assert result is None
    assert calls["n"] == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_fetch_json_handles_timeout(monkeypatch):
    """httpx.TimeoutException на первой попытке → ретрай → ok."""
    calls = {"n": 0}

    async def fake_get(self, url, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("slow")
        return _resp(200, {"ok": 1}, url)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(moex_async.asyncio, "sleep", AsyncMock())

    result = await moex_async.fetch_json("https://iss.moex.com/t.json")
    assert result == {"ok": 1}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_fetch_json_does_not_block_event_loop(monkeypatch):
    """Sanity: fetch_json — корутина (не sync requests.get внутри)."""
    payload = {"x": 1}

    async def fake_get(self, url, params=None):
        # Если бы fetch_json пускал sync requests.get, await тут не сработал бы
        await asyncio.sleep(0)
        return _resp(200, payload, url)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    coro = moex_async.fetch_json("https://iss.moex.com/q.json")
    assert asyncio.iscoroutine(coro)
    assert await coro == payload


# ─── PERF-04: get_candles + downstream API должны быть async ──────────


def test_get_candles_is_async():
    """PERF-04 Blocker: get_candles обязан быть async coroutine.

    Зовётся из async-роутов /trades/* (calculate-mae-mfe bulk на 50-500 сделок)
    через calculate_mae_mfe / calculate_post_exit_analysis. Любой sync HTTP
    тут блокирует event-loop под нагрузкой.
    """
    import inspect
    from market_service import MarketService

    svc = MarketService()
    assert inspect.iscoroutinefunction(svc.get_candles), \
        "get_candles must be async after PERF-04 (Blocker от code-reviewer)"


def test_calculate_mae_mfe_is_async():
    """PERF-04: caller тоже должен стать async, иначе await get_candles внутри
    не сработает."""
    import inspect
    from market_service import MarketService

    svc = MarketService()
    assert inspect.iscoroutinefunction(svc.calculate_mae_mfe)


def test_calculate_post_exit_analysis_is_async():
    """PERF-04: caller тоже должен стать async."""
    import inspect
    from market_service import MarketService

    svc = MarketService()
    assert inspect.iscoroutinefunction(svc.calculate_post_exit_analysis)


@pytest.mark.asyncio
async def test_fetch_json_handles_json_decode_error(monkeypatch):
    """Suggestion #4 от reviewer'а: MOEX может вернуть HTML под 200 при maintenance —
    resp.json() бросает json.JSONDecodeError (подкласс ValueError). Это не httpx.HTTPError,
    значит без расширенного except'а fetch_json бросал бы наружу вместо graceful None.
    """
    class _BadJsonResp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            raise ValueError("not json")

    async def fake_get(self, url, params=None):
        return _BadJsonResp()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(moex_async.asyncio, "sleep", AsyncMock())

    result = await moex_async.fetch_json("https://iss.moex.com/maintenance.html", retries=1)

    # 1 initial + 1 retry — оба бросили ValueError → graceful None
    assert result is None

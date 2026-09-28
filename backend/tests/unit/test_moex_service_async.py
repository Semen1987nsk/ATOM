"""SYNC-04 (Task 1.3): проверки async-обвязки MoexService.

MoexService раньше держал sync httpx.Client в трёх местах:
- get_futures_spec (sync HTTP к ISS, кэшируется)
- get_candles (sync HTTP, используется из /trades/{id}/replay)
- get_index_history (sync HTTP, используется из /stats/ под IMOEX overlay)

После SYNC-04 — get_candles и get_index_history переходят на async через
services.moex_async.fetch_json (горячий путь async-роутов).

get_futures_spec намеренно остаётся sync: его callers (pnl_service,
import_service, application.sync.pipeline, services.moex_cross_check,
tools/refresh_missing_instrument_specs) — sync-функции PnL/import/pipeline,
которые НЕ работают на async event-loop. См. SELF-REVIEW в моём ответе.

Тесты мокают services.moex_async.fetch_json через monkeypatch (не лезем в
сеть, детерминированы).
"""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from unittest.mock import AsyncMock

import pytest


# ─── 1. Async-сигнатуры HTTP-методов ────────────────────────────────


def test_get_candles_is_async():
    """SYNC-04 Blocker: get_candles обязан быть async после миграции.

    Вызывается из routers/replay.py (async-роут). Sync httpx внутри блокировал
    event-loop на ~0.3-2с под cold cache → /trades/{id}/replay висел.
    """
    from moex_service import get_moex_service

    svc = get_moex_service()
    assert inspect.iscoroutinefunction(svc.get_candles), (
        "MoexService.get_candles must be async after SYNC-04 (Task 1.3)"
    )


def test_get_index_history_is_async():
    """SYNC-04: get_index_history обязан быть async.

    Вызывается из routers/stats.py:_build_imoex_overlay (async-handler через
    to_thread-обёртку). После SYNC-04 — нативный await без to_thread."""
    from moex_service import get_moex_service

    svc = get_moex_service()
    assert inspect.iscoroutinefunction(svc.get_index_history), (
        "MoexService.get_index_history must be async after SYNC-04"
    )


def test_get_futures_spec_intentionally_remains_sync():
    """SYNC-04 design choice: get_futures_spec остаётся sync.

    Callers — все sync (pnl_service.get_point_value, import_service.import_*,
    services.moex_cross_check.cross_check_account, tools/refresh_missing_…).
    Не работает на async event-loop горячего пути → миграция дала бы каскад
    переделки всего PnL-стека без выгоды по latency.

    Если в будущем появится async-caller, тест переломится → нужно будет
    либо мигрировать всех callers, либо добавить отдельный async-вариант."""
    from moex_service import get_moex_service

    svc = get_moex_service()
    assert not inspect.iscoroutinefunction(svc.get_futures_spec), (
        "get_futures_spec намеренно sync — см. docstring теста и self-review"
    )


# ─── 2. Happy-path: get_candles через moex_async.fetch_json ──────────


@pytest.mark.asyncio
async def test_get_candles_calls_fetch_json_and_parses_rows(monkeypatch):
    """Happy path: get_candles тянет данные через moex_async.fetch_json
    и нормально парсит candles-payload."""
    from moex_service import get_moex_service
    from services import moex_async

    payload = {
        "candles": {
            "columns": ["open", "close", "high", "low", "value", "volume", "begin", "end"],
            "data": [
                [300.0, 305.0, 306.0, 299.0, 1.5e6, 1000, "2026-05-01 10:00:00", "2026-05-01 11:00:00"],
                [305.0, 310.0, 311.0, 304.0, 2.0e6, 2000, "2026-05-01 11:00:00", "2026-05-01 12:00:00"],
            ],
        }
    }
    mock_fetch = AsyncMock(return_value=payload)
    monkeypatch.setattr(moex_async, "fetch_json", mock_fetch)

    svc = get_moex_service()
    result = await svc.get_candles(
        ticker="SBER",
        interval="1h",
        start=datetime(2026, 5, 1, 10, 0),
        end=datetime(2026, 5, 1, 12, 0),
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["t"] == "2026-05-01 10:00:00"
    assert result[0]["o"] == 300.0
    assert result[0]["c"] == 305.0
    assert result[0]["v"] == 1000
    # fetch_json должен был быть позван хотя бы один раз (urls fallback допускается)
    assert mock_fetch.await_count >= 1


@pytest.mark.asyncio
async def test_get_candles_returns_empty_when_fetch_returns_none(monkeypatch):
    """Если все urls вернули None (сеть упала / 404) — возвращаем []."""
    from moex_service import get_moex_service
    from services import moex_async

    monkeypatch.setattr(moex_async, "fetch_json", AsyncMock(return_value=None))

    svc = get_moex_service()
    result = await svc.get_candles(
        ticker="SBER",
        interval="1h",
        start=datetime(2026, 5, 1, 10, 0),
        end=datetime(2026, 5, 1, 12, 0),
    )
    assert result == []


@pytest.mark.asyncio
async def test_get_candles_falls_through_to_second_url(monkeypatch):
    """Если первый url дал пустой/None payload, get_candles пробует второй."""
    from moex_service import get_moex_service
    from services import moex_async

    second_payload = {
        "candles": {
            "columns": ["open", "close", "high", "low", "value", "volume", "begin", "end"],
            "data": [[100.0, 110.0, 115.0, 95.0, 0.0, 50, "2026-05-01 10:00:00", "2026-05-01 11:00:00"]],
        }
    }

    call_count = {"n": 0}

    async def fake_fetch(url, params=None, retries=2):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None  # эмулируем 404 / network error на первый url
        return second_payload

    monkeypatch.setattr(moex_async, "fetch_json", fake_fetch)

    svc = get_moex_service()
    result = await svc.get_candles(
        ticker="SiH6",  # фьючерс → первый url forts, второй shares
        interval="1h",
        start=datetime(2026, 5, 1, 10, 0),
        end=datetime(2026, 5, 1, 12, 0),
    )
    assert len(result) == 1
    assert result[0]["o"] == 100.0
    assert call_count["n"] == 2  # реально пробовали оба url


# ─── 3. Happy-path: get_index_history через moex_async.fetch_json ────


@pytest.mark.asyncio
async def test_get_index_history_calls_fetch_json_and_parses_rows(monkeypatch):
    """get_index_history парсит history-payload и возвращает [{date, value}]."""
    from moex_service import MoexService
    from services import moex_async

    payload = {
        "history": {
            "columns": ["TRADEDATE", "CLOSE"],
            "data": [
                ["2026-05-01", 3200.0],
                ["2026-05-02", 3210.5],
            ],
        }
    }
    mock_fetch = AsyncMock(return_value=payload)
    monkeypatch.setattr(moex_async, "fetch_json", mock_fetch)

    # Свежий instance чтобы обойти TTL-кэш
    svc = MoexService()
    result = await svc.get_index_history(
        "IMOEX",
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 31),
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"date": "2026-05-01", "value": 3200.0}
    assert result[1] == {"date": "2026-05-02", "value": 3210.5}


@pytest.mark.asyncio
async def test_get_index_history_paginates_when_rows_equal_page_size(monkeypatch):
    """ISS пагинирует по 100 записей. Если первая страница вернула 100 строк —
    нужно ещё раз сходить со start=100; если меньше — break."""
    from moex_service import MoexService
    from services import moex_async

    full_page = {
        "history": {
            "columns": ["TRADEDATE", "CLOSE"],
            "data": [["2026-05-01", float(i)] for i in range(100)],
        }
    }
    partial_page = {
        "history": {
            "columns": ["TRADEDATE", "CLOSE"],
            "data": [["2026-05-02", 999.0]],
        }
    }

    calls = {"n": 0}

    async def fake_fetch(url, params=None, retries=2):
        calls["n"] += 1
        return full_page if calls["n"] == 1 else partial_page

    monkeypatch.setattr(moex_async, "fetch_json", fake_fetch)

    svc = MoexService()
    result = await svc.get_index_history(
        "IMOEX",
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 31),
    )
    assert len(result) == 101  # 100 + 1
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_get_index_history_cache_hit_does_not_fetch(monkeypatch):
    """TTL-кэш по (ticker, start, end) должен работать после миграции:
    повторный вызов в окне TTL не должен лезть в fetch_json."""
    from moex_service import MoexService
    from services import moex_async

    payload = {
        "history": {
            "columns": ["TRADEDATE", "CLOSE"],
            "data": [["2026-05-01", 3200.0]],
        }
    }
    mock_fetch = AsyncMock(return_value=payload)
    monkeypatch.setattr(moex_async, "fetch_json", mock_fetch)

    svc = MoexService()
    start = datetime(2026, 5, 1)
    end = datetime(2026, 5, 31)

    r1 = await svc.get_index_history("IMOEX", start=start, end=end)
    r2 = await svc.get_index_history("IMOEX", start=start, end=end)

    assert r1 == r2
    # Второй вызов должен попасть в кэш — fetch_json вызван ровно один раз
    assert mock_fetch.await_count == 1


@pytest.mark.asyncio
async def test_get_index_history_returns_empty_when_fetch_returns_none(monkeypatch):
    """Сеть отвалилась → fetch_json вернул None → graceful []."""
    from moex_service import MoexService
    from services import moex_async

    monkeypatch.setattr(moex_async, "fetch_json", AsyncMock(return_value=None))

    svc = MoexService()
    result = await svc.get_index_history(
        "IMOEX",
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 31),
    )
    assert result == []

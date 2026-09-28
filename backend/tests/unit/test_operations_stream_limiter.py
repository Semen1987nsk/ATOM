"""SYNC-07: лимитер захватывается ровно 1 раз на открытие стрима, не на каждое
событие и не на весь lifetime. Усиленный вариант: лимитер-контекст обязан
ВЫЙТИ до начала чтения событий (на старом коде он держится весь read-loop)."""
from __future__ import annotations

import pytest

from adapters.tinkoff.operations_stream_client import TinkoffOperationsStreamClient


class _CountingLimiter:
    def __init__(self):
        self.entered = 0
        self.exited = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *a):
        self.exited += 1
        return None


class _FakeStream:
    """Async-iterator из N фейковых событий, каждое с .operation=None
    (extract вернёт None → не маппим домен, нам важен только счётчик limiter).

    На отдаче ПЕРВОГО элемента ассертит, что лимитер-контекст уже закрыт
    (`limiter.exited == 1`): чтение идёт ВНЕ лимитера."""

    def __init__(self, n, limiter):
        self._items = [object() for _ in range(n)]
        self._limiter = limiter
        self._first = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        if self._first:
            self._first = False
            assert self._limiter.exited == 1, (
                "лимитер-контекст должен закрыться до начала чтения событий"
            )
        return self._items.pop(0)


class _OpsStream:
    def __init__(self, n, limiter):
        self._n = n
        self._limiter = limiter

    def operations_stream(self, request):
        return _FakeStream(self._n, self._limiter)


class _Services:
    def __init__(self, n):
        self.limiter = _CountingLimiter()
        self.operations_stream = _OpsStream(n, self.limiter)


@pytest.mark.asyncio
async def test_one_limiter_acquire_per_stream_regardless_of_events():
    svc = _Services(n=25)
    client = TinkoffOperationsStreamClient(svc)
    got = [op async for op in client.stream_operations("acc", max_reconnect_attempts=1)]
    assert svc.limiter.entered == 1  # 1 токен на стрим, не 25
    assert svc.limiter.exited == 1  # контекст вышел до read-loop
    assert got == []  # все события .operation=None → ничего не сэмитили

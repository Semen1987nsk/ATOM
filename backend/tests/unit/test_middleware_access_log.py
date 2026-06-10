"""
PERF-03 — sync db.commit() в access-log middleware не должен блокировать
async event-loop. Проверяем, что _persist_access_log_async выгружает
синхронную запись в worker-thread через asyncio.to_thread.
"""

import threading
from unittest.mock import MagicMock

import pytest

from middleware import RequestLoggingMiddleware


@pytest.mark.asyncio
async def test_persist_access_log_does_not_block_event_loop(monkeypatch):
    """PERF-03: sync db.commit() inside dispatch must run in a worker thread."""
    captured_thread_ids: list[int] = []

    def fake_session_factory():
        captured_thread_ids.append(threading.get_ident())
        sess = MagicMock()
        sess.add = MagicMock()
        sess.commit = MagicMock()
        sess.close = MagicMock()
        return sess

    # SessionLocal импортируется лениво внутри _persist_access_log,
    # патчим в его источнике.
    monkeypatch.setattr("database.SessionLocal", fake_session_factory)

    mw = RequestLoggingMiddleware(app=MagicMock())
    request = MagicMock()
    request.url.path = "/api/x"
    request.method = "GET"
    request.headers = {}
    request.client.host = "1.2.3.4"
    request.state = MagicMock(user_id=None, request_id="rid-1")

    await mw._persist_access_log_async(request, 200, 12.5, "1.2.3.4")

    assert captured_thread_ids, "persist did not run"
    assert captured_thread_ids[0] != threading.get_ident(), (
        "persist ran on event-loop thread — would block"
    )

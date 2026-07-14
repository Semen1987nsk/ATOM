"""SYNC-06: при ошибке выполнения advisory-lock запроса коннект должен
закрываться, а не утекать из пула."""
from __future__ import annotations

import sync_scheduler


class _Conn:
    def __init__(self, fail_execute=False):
        self.closed = False
        self._fail = fail_execute

    def execute(self, *a, **k):
        if self._fail:
            raise RuntimeError("boom during pg_try_advisory_lock")
        class _R:
            def scalar(self_inner):
                return True
        return _R()

    def close(self):
        self.closed = True


class _Engine:
    def __init__(self, conn):
        self._conn = conn
        class _D:
            name = "postgresql"
        self.dialect = _D()

    def connect(self):
        return self._conn


def test_connection_closed_when_execute_fails(monkeypatch):
    conn = _Conn(fail_execute=True)
    monkeypatch.setattr(sync_scheduler, "engine", _Engine(conn), raising=False)
    sync_scheduler._acquire_scheduler_lock()   # must not raise
    assert conn.closed is True


def test_connection_kept_open_when_lock_acquired(monkeypatch):
    conn = _Conn(fail_execute=False)
    monkeypatch.setattr(sync_scheduler, "engine", _Engine(conn), raising=False)
    sync_scheduler._lock_connection = None
    got = sync_scheduler._acquire_scheduler_lock()
    assert got is True
    assert conn.closed is False
    assert sync_scheduler._lock_connection is conn
    sync_scheduler._release_scheduler_lock()

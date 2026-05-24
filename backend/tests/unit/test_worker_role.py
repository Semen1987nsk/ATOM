"""is_scheduler_worker(): singleton-фоновые задачи (scheduler + streams)
должны идти ровно на одном воркере. Default true (одиночный деплой)."""
from __future__ import annotations

import importlib


def _fresh(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("IS_SCHEDULER_WORKER", raising=False)
    else:
        monkeypatch.setenv("IS_SCHEDULER_WORKER", value)
    import worker_role
    importlib.reload(worker_role)
    return worker_role.is_scheduler_worker()


def test_default_is_true(monkeypatch):
    assert _fresh(monkeypatch, None) is True


def test_false_when_disabled(monkeypatch):
    assert _fresh(monkeypatch, "false") is False
    assert _fresh(monkeypatch, "FALSE") is False


def test_true_when_enabled(monkeypatch):
    assert _fresh(monkeypatch, "true") is True

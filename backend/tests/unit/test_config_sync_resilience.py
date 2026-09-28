"""Sprint 1B: новые resilience-настройки имеют разумные дефолты и читаются из env."""
from __future__ import annotations

import importlib


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config
    return importlib.reload(config).settings


def test_defaults(monkeypatch):
    s = _reload_config(monkeypatch)
    assert s.TINKOFF_LIMITER_MAX_WAIT_SECONDS == 60.0
    assert s.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS == 30.0
    assert s.TINKOFF_IP_COOLDOWN_BASE_SECONDS == 60
    assert s.TINKOFF_IP_COOLDOWN_MAX_SECONDS == 600
    assert s.TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS == 2


def test_env_override(monkeypatch):
    s = _reload_config(
        monkeypatch,
        TINKOFF_GRPC_CALL_TIMEOUT_SECONDS="12.5",
        TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS="5",
    )
    assert s.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS == 12.5
    assert s.TINKOFF_IP_COOLDOWN_MIN_DISTINCT_CONNECTIONS == 5

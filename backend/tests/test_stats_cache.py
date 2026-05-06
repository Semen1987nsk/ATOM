"""
Тесты на services.stats_cache — extracted из routers/stats.py.

Проверяем: TTL expiry, eviction, потокобезопасность, стабильность ключей.
"""
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.stats_cache import (  # noqa: E402
    StatsCache,
    build_request_key,
    build_trades_state_fingerprint,
)


# ─────────────────────────────────────────
#  TTL & basic semantics
# ─────────────────────────────────────────


def test_set_then_get_returns_value():
    cache = StatsCache(ttl_seconds=10, max_size=10)
    cache.set("k", {"x": 1})
    assert cache.get("k") == {"x": 1}


def test_get_missing_returns_none():
    cache = StatsCache(ttl_seconds=10, max_size=10)
    assert cache.get("nonexistent") is None


def test_ttl_expiry():
    cache = StatsCache(ttl_seconds=0, max_size=10)  # мгновенное протухание
    cache.set("k", "v")
    time.sleep(0.01)
    assert cache.get("k") is None


def test_invalidate_removes_entry():
    cache = StatsCache(ttl_seconds=60)
    cache.set("k", "v")
    cache.invalidate("k")
    assert cache.get("k") is None


def test_clear_drops_everything():
    cache = StatsCache(ttl_seconds=60)
    for i in range(5):
        cache.set(f"k{i}", i)
    cache.clear()
    for i in range(5):
        assert cache.get(f"k{i}") is None


# ─────────────────────────────────────────
#  Eviction
# ─────────────────────────────────────────


def test_eviction_when_max_size_exceeded():
    cache = StatsCache(ttl_seconds=60, max_size=4)
    for i in range(10):
        cache.set(f"k{i}", i)
    # После эвикции должно остаться <= max_size//2 + новые добавления.
    # Точный размер не критичен — критично, что НЕ растёт неограниченно.
    assert len(cache._store) <= 6


# ─────────────────────────────────────────
#  Key builders
# ─────────────────────────────────────────


def test_request_key_stable_under_param_reorder():
    k1 = build_request_key(1, period="month", symbol="SBER")
    k2 = build_request_key(1, symbol="SBER", period="month")
    assert k1 == k2


def test_request_key_ignores_none_params():
    k_with_none = build_request_key(1, period="month", symbol=None)
    k_without = build_request_key(1, period="month")
    assert k_with_none == k_without


def test_request_key_changes_with_account():
    assert build_request_key(1, period="month") != build_request_key(2, period="month")


def test_fingerprint_changes_when_pnl_changes():
    t1 = SimpleNamespace(
        id=1, pnl=100, net_pnl=95, risk_amount=50,
        entry_at=None, exit_at=None, tags=None, mae_price=None, mfe_price=None,
    )
    t2 = SimpleNamespace(
        id=1, pnl=200, net_pnl=95, risk_amount=50,
        entry_at=None, exit_at=None, tags=None, mae_price=None, mfe_price=None,
    )
    assert build_trades_state_fingerprint([t1]) != build_trades_state_fingerprint([t2])


def test_fingerprint_stable_for_same_data():
    t = SimpleNamespace(
        id=1, pnl=100, net_pnl=95, risk_amount=50,
        entry_at=None, exit_at=None, tags=["a"], mae_price=None, mfe_price=None,
    )
    assert build_trades_state_fingerprint([t]) == build_trades_state_fingerprint([t])


# ─────────────────────────────────────────
#  Thread-safety
# ─────────────────────────────────────────


def test_concurrent_set_get_does_not_crash():
    """Smoke test: 50 потоков пишут и читают одновременно — гонок нет."""
    cache = StatsCache(ttl_seconds=60, max_size=200)

    def worker(idx: int):
        for j in range(20):
            cache.set(f"t{idx}-{j}", {"i": j})
            assert cache.get(f"t{idx}-{j}") in (None, {"i": j})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

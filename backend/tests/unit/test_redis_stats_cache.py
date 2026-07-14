"""PERF-05: RedisStatsCache — общий кэш между воркерами, тот же интерфейс
что in-memory StatsCache, JSON-сериализация, graceful-degrade при сбое Redis."""
from __future__ import annotations

from services.stats_cache import RedisStatsCache


class FakeRedis:
    """Минимальный in-memory дублёр redis-клиента для теста."""
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.fail = False

    def get(self, k):
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.get(k)

    def set(self, k, v, ex=None):
        if self.fail:
            raise ConnectionError("redis down")
        self.store[k] = v

    def delete(self, *names):
        for n in names:
            self.store.pop(n, None)

    def scan_iter(self, match=None):
        pref = (match or "").rstrip("*")
        return [k for k in list(self.store) if k.startswith(pref)]


def test_set_get_roundtrip_json_value():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    value = {"win_rate": 48.52, "n": 10, "nested": {"x": [1, 2]}}
    c.set("k1", value)
    assert c.get("k1") == value


def test_keys_are_namespaced():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    c.set("k1", 123)
    assert all(k.startswith("stats:") for k in r.store)


def test_ttl_passed_to_redis():
    r = FakeRedis()
    captured = {}
    orig = r.set
    def spy(k, v, ex=None):
        captured["ex"] = ex
        return orig(k, v, ex=ex)
    r.set = spy
    c = RedisStatsCache(r, ttl_seconds=42)
    c.set("k1", 1)
    assert captured["ex"] == 42


def test_get_miss_returns_none():
    c = RedisStatsCache(FakeRedis(), ttl_seconds=30)
    assert c.get("absent") is None


def test_invalidate_and_clear():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    c.set("a", 1); c.set("b", 2)
    c.invalidate("a")
    assert c.get("a") is None and c.get("b") == 2
    c.clear()
    assert c.get("b") is None


def test_non_serializable_value_skipped_not_crash():
    r = FakeRedis()
    c = RedisStatsCache(r, ttl_seconds=30)
    c.set("k", object())   # не JSON-сериализуемо → пропускаем, без исключения
    assert c.get("k") is None


def test_redis_failure_degrades_to_miss_not_crash():
    r = FakeRedis(); r.fail = True
    c = RedisStatsCache(r, ttl_seconds=30)
    assert c.get("k") is None
    c.set("k", {"a": 1})

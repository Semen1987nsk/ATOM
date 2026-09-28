from datetime import datetime, timedelta

from moex_service import MoexService


def test_index_cache_evicts_expired_on_write():
    svc = MoexService()
    old = datetime.utcnow() - timedelta(hours=2)  # старше TTL (1ч)
    svc._index_cache[("IMOEX", "2020-01-01", "2020-12-31")] = ([], old)
    svc._store_index_cache(("IMOEX", "2025-01-01", "2025-12-31"), [{"date": "2025-01-01", "value": 1.0}])
    # Протухшая запись должна быть удалена при записи новой.
    assert ("IMOEX", "2020-01-01", "2020-12-31") not in svc._index_cache


def test_index_cache_bounded_size():
    svc = MoexService()
    for i in range(300):
        svc._store_index_cache(("IMOEX", f"2025-{i:03d}", "x"), [])
    assert len(svc._index_cache) <= svc._INDEX_CACHE_MAX

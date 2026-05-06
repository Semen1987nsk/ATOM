"""
Stats cache — потокобезопасный in-memory кеш для дорогих агрегаций /stats/.

Извлечён из routers/stats.py, где жил inline 80+ строк.
Отдельным модулем легче:
- покрыть unit-тестами;
- заменить на Redis в Phase 2 (`from services.stats_cache import StatsCache`
  → drop-in `RedisStatsCache`).

ВАЖНО: это per-process кеш. Под gunicorn с N воркерами каждый воркер
держит свой словарь — общий hit-rate ниже, чем кажется.
Когда захочется консистентного hit-rate, мигрируй на Redis-backed реализацию.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Any, Iterable, Optional


class StatsCache:
    """Thread-safe TTL cache с LRU-подобной эвикцией по timestamp."""

    def __init__(self, ttl_seconds: int = 30, max_size: int = 100) -> None:
        self._store: dict[str, tuple[Any, datetime]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max = max_size

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, ts = item
            if (datetime.now() - ts).total_seconds() < self._ttl:
                return value
            # Expired — удаляем под тем же локом
            self._store.pop(key, None)
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (value, datetime.now())
            self._evict_if_full_locked()

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_if_full_locked(self) -> None:
        """Должен вызываться под self._lock."""
        if len(self._store) <= self._max:
            return
        # Удаляем половину самых старых записей за раз — амортизирует cost.
        sorted_keys = sorted(self._store.keys(), key=lambda k: self._store[k][1])
        evict_count = len(self._store) - self._max // 2
        for k in sorted_keys[:evict_count]:
            self._store.pop(k, None)


# ──────────────────────────────────────────────
#  Key builders
# ──────────────────────────────────────────────

def build_request_key(account_id: int, **params) -> str:
    """
    Стабильный кеш-ключ из account_id + произвольных kwargs.
    None-значения игнорируются — они не должны вынуждать новый кеш-промах.
    """
    payload = {k: v for k, v in params.items() if v is not None}
    payload["account_id"] = account_id
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def build_trades_state_fingerprint(trades: Iterable) -> str:
    """
    Отпечаток состояния отфильтрованного набора сделок.

    Зачем: даже если ключ запроса (account_id + фильтры) совпал, данные могли
    измениться — новая сделка, edit, delete. Считаем хэш по существенным полям
    и кладём в составной кеш-ключ. Если хоть одно поле поменялось — cache miss.
    """
    payload = []
    for trade in trades:
        payload.append({
            "id": trade.id,
            "pnl": float(trade.pnl) if trade.pnl is not None else None,
            "net_pnl": float(trade.net_pnl) if trade.net_pnl is not None else None,
            "risk_amount": float(trade.risk_amount) if trade.risk_amount is not None else None,
            "entry_at": trade.entry_at.isoformat() if trade.entry_at else None,
            "exit_at": trade.exit_at.isoformat() if trade.exit_at else None,
            "tags": trade.tags or [],
            "mae_price": float(trade.mae_price) if trade.mae_price is not None else None,
            "mfe_price": float(trade.mfe_price) if trade.mfe_price is not None else None,
        })
    state = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(state.encode()).hexdigest()


# ──────────────────────────────────────────────
#  Module-global instance
# ──────────────────────────────────────────────

# Дефолтный кеш для роутера /stats/. Тесты могут создать собственный экземпляр.
stats_cache = StatsCache(ttl_seconds=30, max_size=100)

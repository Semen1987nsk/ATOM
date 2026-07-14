"""StreamOperationDeduplicator — AU-stream Phase 1+ component.

Stream events могут пересекаться с тем что уже сохранилось через cursor-based
catch-up при reconnect. UNIQUE constraint в БД (account_id, operation_id)
защитит от двойной вставки на DB level, но дёргать INSERT впустую — расход
DB connection и stream throughput. Этот класс делает быструю проверку
ДО persist:

1. In-memory LRU cache последних N operation_id (быстро, no DB hit).
2. Если не в cache — fallback на DB query.
3. Если найден — skip persist (return is_new=False).
4. Если новый — UPSERT (caller сам делает) и добавляет в cache.

Cache size 1000 — для активных traders с 10 trades/min покрывает ~100
минут истории. При reconnect catch-up может дать всплеск 100-1000
операций; cache переживает (LRU).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from sqlalchemy.orm import Session

import models
from logger import get_logger

log = get_logger("application.sync.dedup")


class StreamOperationDeduplicator:
    """LRU-cached check на existence operation_id в БД.

    Не thread-safe — предполагается один consumer per account_id.
    """

    def __init__(self, *, cache_size: int = 1000) -> None:
        self._cache_size = cache_size
        # OrderedDict для LRU: ключ = (account_id, operation_id), value = True
        # Move-to-end на access; popitem(last=False) для eviction.
        self._cache: OrderedDict[tuple[int, str], bool] = OrderedDict()

    def is_new(
        self,
        *,
        account_id: int,
        operation_id: str,
        session: Session,
    ) -> bool:
        """True если operation НЕ найдена в кэше И не найдена в БД.

        False означает что operation уже была обработана — caller skip persist.
        """
        if not operation_id:
            # Пустой operation_id — defensive: считаем "новым", caller разберётся
            return True

        key = (account_id, operation_id)

        # 1. Cache hit — дубликат
        if key in self._cache:
            self._cache.move_to_end(key)  # LRU touch
            return False

        # 2. DB check — может быть в БД но ещё не в нашем cache (после reconnect)
        exists = (
            session.query(models.OperationORM.id)
            .filter(
                models.OperationORM.account_id == account_id,
                models.OperationORM.operation_id == operation_id,
            )
            .first()
            is not None
        )
        if exists:
            self._mark_seen(key)
            return False

        # 3. Новая операция
        return True

    def mark_persisted(self, *, account_id: int, operation_id: str) -> None:
        """Отметить что operation сохранена. Вызывать после успешного UPSERT."""
        if not operation_id:
            return
        self._mark_seen((account_id, operation_id))

    def _mark_seen(self, key: tuple[int, str]) -> None:
        """Добавить в cache + evict oldest если переполнили."""
        self._cache[key] = True
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            evicted_key, _ = self._cache.popitem(last=False)
            log.debug("dedup.cache_evict", extra={"key": str(evicted_key)})

    def cache_size(self) -> int:
        """Для observability/тестов."""
        return len(self._cache)

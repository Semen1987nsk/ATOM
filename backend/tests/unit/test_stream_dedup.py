"""AU-stream Phase 1+: tests для StreamOperationDeduplicator."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.sync.dedup import StreamOperationDeduplicator


class TestStreamOperationDeduplicator:
    def _mock_session_returns(self, found: bool):
        """Helper: mock session.query().filter().first() chain."""
        sess = MagicMock()
        first = MagicMock(return_value=(MagicMock() if found else None))
        sess.query.return_value.filter.return_value.first = first
        return sess

    def test_first_call_is_new(self):
        """Новая operation → is_new=True (cache miss + DB miss)."""
        d = StreamOperationDeduplicator()
        sess = self._mock_session_returns(found=False)
        assert d.is_new(account_id=1, operation_id="op-1", session=sess) is True

    def test_cached_returns_not_new(self):
        """После mark_persisted следующий is_new для того же id → False."""
        d = StreamOperationDeduplicator()
        d.mark_persisted(account_id=1, operation_id="op-1")
        # Session не должен быть нужен — cache hit
        sess = MagicMock()
        assert d.is_new(account_id=1, operation_id="op-1", session=sess) is False
        sess.query.assert_not_called()

    def test_db_found_caches_and_returns_not_new(self):
        """Если DB говорит "exists" → False + добавляется в cache."""
        d = StreamOperationDeduplicator()
        sess = self._mock_session_returns(found=True)
        assert d.is_new(account_id=1, operation_id="op-1", session=sess) is False
        # Второй вызов — cache hit, нет DB query
        sess2 = MagicMock()
        assert d.is_new(account_id=1, operation_id="op-1", session=sess2) is False
        sess2.query.assert_not_called()

    def test_different_account_same_op_id_independent(self):
        """operation_id одинаковый для двух разных account → независимые keys."""
        d = StreamOperationDeduplicator()
        d.mark_persisted(account_id=1, operation_id="op-1")
        sess = self._mock_session_returns(found=False)
        # Account 2 — не в cache
        assert d.is_new(account_id=2, operation_id="op-1", session=sess) is True

    def test_lru_eviction_at_max_size(self):
        """При переполнении cache самый старый ключ выселяется (LRU)."""
        d = StreamOperationDeduplicator(cache_size=3)
        d.mark_persisted(account_id=1, operation_id="op-1")
        d.mark_persisted(account_id=1, operation_id="op-2")
        d.mark_persisted(account_id=1, operation_id="op-3")
        assert d.cache_size() == 3
        # 4-й добавляется → op-1 эвиктнут
        d.mark_persisted(account_id=1, operation_id="op-4")
        assert d.cache_size() == 3

        # op-1 теперь не в cache → DB query будет
        sess = self._mock_session_returns(found=False)
        d.is_new(account_id=1, operation_id="op-1", session=sess)
        sess.query.assert_called_once()

    def test_lru_touch_on_hit(self):
        """Cache hit — "оживляет" ключ, защищая от eviction."""
        d = StreamOperationDeduplicator(cache_size=3)
        d.mark_persisted(account_id=1, operation_id="op-1")
        d.mark_persisted(account_id=1, operation_id="op-2")
        d.mark_persisted(account_id=1, operation_id="op-3")

        # Touch op-1 (cache hit)
        sess = MagicMock()
        d.is_new(account_id=1, operation_id="op-1", session=sess)

        # Добавить op-4 → теперь самый старый — op-2, не op-1
        d.mark_persisted(account_id=1, operation_id="op-4")

        # op-2 эвиктнут
        sess2 = self._mock_session_returns(found=False)
        d.is_new(account_id=1, operation_id="op-2", session=sess2)
        sess2.query.assert_called_once()

        # op-1 всё ещё в cache (благодаря touch)
        sess3 = MagicMock()
        d.is_new(account_id=1, operation_id="op-1", session=sess3)
        sess3.query.assert_not_called()

    def test_empty_operation_id_treated_as_new(self):
        """Пустой operation_id — defensive return True (caller разберётся)."""
        d = StreamOperationDeduplicator()
        sess = MagicMock()
        assert d.is_new(account_id=1, operation_id="", session=sess) is True
        sess.query.assert_not_called()

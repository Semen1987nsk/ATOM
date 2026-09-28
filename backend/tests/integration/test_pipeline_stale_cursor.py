"""S2-14: stale-cursor детект работает при ЛЮБОМ числе страниц.

Многостраничный stale-ответ (cursor валиден, отдаёт >page_size старых ops,
затем next_cursor=None) раньше проходил незамеченным: `current == cursor`
уже неверно после первой страницы. Проверяем что max(batch) < max(db) − 1ч
триггерит fallback независимо от пагинации.
"""
from datetime import datetime, timedelta

from application.sync.pipeline import _is_stale_batch


def test_multipage_stale_detected():
    max_in_batch = datetime(2024, 1, 1)
    max_in_db = datetime(2026, 1, 1)
    assert _is_stale_batch(max_in_batch, max_in_db) is True


def test_fresh_batch_not_stale():
    now = datetime(2026, 1, 1, 12, 0)
    assert _is_stale_batch(now, now - timedelta(minutes=5)) is False


def test_none_db_max_not_stale():
    assert _is_stale_batch(datetime(2024, 1, 1), None) is False

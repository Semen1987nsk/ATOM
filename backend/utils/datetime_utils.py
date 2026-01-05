"""
Утилиты для работы с датой и временем.

Используй utc_now() вместо datetime.utcnow() — это timezone-aware
и не вызывает DeprecationWarning в Python 3.12+.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    Возвращает текущее время в UTC (timezone-aware).
    Замена deprecated datetime.utcnow().
    """
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    """
    Возвращает текущее время в UTC без timezone info.
    Для совместимости с SQLite и существующими моделями.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

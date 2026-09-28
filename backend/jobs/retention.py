"""PERF-09 (Sprint 3, Task 3.3): retention/cleanup для безграничных таблиц.

Запускается раз в 24ч ТОЛЬКО на scheduler-воркере (см. sync_scheduler.py).

Без retention эти таблицы растут безгранично:
  * access_log — 10% sampled HTTP requests (~MB/день при mid-нагрузке);
  * sync_events — 1 строка на каждый sync attempt всех accounts (~KB/день/account);
  * revoked_tokens — JWT jti до истечения токена (после expires_at бесполезны).

Cutoff'ы в днях задаются через settings (ACCESS_LOG_RETENTION_DAYS=30,
SYNC_EVENTS_RETENTION_DAYS=90); revoked_tokens чистятся по фактическому
expires_at (любая запись с expires_at < now — мусор).

Все timestamps в проекте — tz-naive UTC (см. utils.datetime_utils.utc_now_naive),
поэтому threshold формируется тем же способом.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


def _utc_naive_threshold(days: int) -> datetime:
    """tz-naive UTC datetime ровно `days` дней назад."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)


def cleanup_access_log(session: Session, *, retention_days: int) -> int:
    """Удаляет записи access_log старше `retention_days`. Возвращает количество удалённых."""
    cutoff = _utc_naive_threshold(retention_days)
    n = (
        session.query(models.AccessLogORM)
        .filter(models.AccessLogORM.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    logger.info("retention.access_log deleted=%d cutoff=%s", n, cutoff.isoformat())
    return int(n)


def cleanup_sync_events(session: Session, *, retention_days: int) -> int:
    """Удаляет записи sync_events старше `retention_days`. Возвращает количество удалённых."""
    cutoff = _utc_naive_threshold(retention_days)
    n = (
        session.query(models.SyncEventORM)
        .filter(models.SyncEventORM.started_at < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    logger.info("retention.sync_events deleted=%d cutoff=%s", n, cutoff.isoformat())
    return int(n)


def cleanup_revoked_tokens(session: Session) -> int:
    """Удаляет JWT jti с истёкшим expires_at — токен и так невалиден.

    Параметр retention не нужен: revoked_tokens.expires_at = native TTL токена.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    n = (
        session.query(models.RevokedTokenORM)
        .filter(models.RevokedTokenORM.expires_at < now)
        .delete(synchronize_session=False)
    )
    session.commit()
    logger.info("retention.revoked_tokens deleted=%d now=%s", n, now.isoformat())
    return int(n)

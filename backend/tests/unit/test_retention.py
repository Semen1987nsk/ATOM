"""PERF-09 (Sprint 3, Task 3.3): retention jobs для access_log, sync_events, revoked_tokens.

Поля моделей (см. models.py):
  * AccessLogORM: method, path, status_code, created_at (timezone-naive UTC)
  * SyncEventORM: account_id, status, started_at (NOT NULL)
  * RevokedTokenORM: jti, user_id, revoked_at, expires_at
"""
from datetime import datetime, timedelta, timezone

import models
from jobs.retention import (
    cleanup_access_log,
    cleanup_revoked_tokens,
    cleanup_sync_events,
)


def _utc_naive(offset: timedelta = timedelta(0)) -> datetime:
    return (datetime.now(timezone.utc) + offset).replace(tzinfo=None)


def test_cleanup_access_log_deletes_old(db_session):
    old = models.AccessLogORM(
        path="/", method="GET", status_code=200,
        created_at=_utc_naive(-timedelta(days=31)),
    )
    fresh = models.AccessLogORM(
        path="/", method="GET", status_code=200,
        created_at=_utc_naive(-timedelta(days=5)),
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    deleted = cleanup_access_log(db_session, retention_days=30)
    assert deleted == 1
    remaining = db_session.query(models.AccessLogORM).all()
    assert len(remaining) == 1
    assert remaining[0].created_at > _utc_naive(-timedelta(days=10))


def test_cleanup_access_log_noop_when_empty(db_session):
    assert cleanup_access_log(db_session, retention_days=30) == 0


def test_cleanup_sync_events_deletes_old(db_session):
    old = models.SyncEventORM(
        account_id=1, status="success",
        started_at=_utc_naive(-timedelta(days=91)),
    )
    fresh = models.SyncEventORM(
        account_id=1, status="success",
        started_at=_utc_naive(-timedelta(days=10)),
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    deleted = cleanup_sync_events(db_session, retention_days=90)
    assert deleted == 1
    remaining = db_session.query(models.SyncEventORM).all()
    assert len(remaining) == 1


def test_cleanup_revoked_tokens_uses_expires_at(db_session):
    expired = models.RevokedTokenORM(
        jti="a", user_id=1,
        revoked_at=_utc_naive(-timedelta(days=2)),
        expires_at=_utc_naive(-timedelta(hours=1)),
    )
    still_valid = models.RevokedTokenORM(
        jti="b", user_id=1,
        revoked_at=_utc_naive(-timedelta(hours=1)),
        expires_at=_utc_naive(timedelta(hours=1)),
    )
    db_session.add_all([expired, still_valid])
    db_session.commit()

    deleted = cleanup_revoked_tokens(db_session)
    assert deleted == 1
    remaining = db_session.query(models.RevokedTokenORM).all()
    assert len(remaining) == 1
    assert remaining[0].jti == "b"


def test_cleanup_revoked_tokens_noop_when_all_valid(db_session):
    db_session.add(
        models.RevokedTokenORM(
            jti="future", user_id=1,
            revoked_at=_utc_naive(),
            expires_at=_utc_naive(timedelta(days=7)),
        )
    )
    db_session.commit()
    assert cleanup_revoked_tokens(db_session) == 0

from datetime import datetime, timedelta

import models
from services import pd_deletion


def test_finalize_deletes_token_orphans(db_session):
    user = models.User(email="orph@x.com", hashed_password="x", is_active=1)
    db_session.add(user)
    db_session.flush()
    db_session.add(models.PasswordResetTokenORM(
        token="t1", user_id=user.id, created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1), requester_ip="1.2.3.4",
    ))
    db_session.add(models.FeatureFlagORM(user_id=user.id, flag_name="mae-mfe-beta", enabled=True))
    db_session.add(models.RevokedTokenORM(
        jti="j1", user_id=user.id, revoked_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    ))
    db_session.commit()

    pd_deletion.finalize_deletion(db_session, user)

    assert db_session.query(models.PasswordResetTokenORM).filter_by(user_id=user.id).count() == 0
    assert db_session.query(models.FeatureFlagORM).filter_by(user_id=user.id).count() == 0
    assert db_session.query(models.RevokedTokenORM).filter_by(user_id=user.id).count() == 0

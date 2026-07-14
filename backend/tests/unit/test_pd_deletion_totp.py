import models
from services import pd_deletion


def test_finalize_clears_totp_and_verification(db_session):
    user = models.User(
        email="t@x.com", hashed_password="x", is_active=1,
        totp_secret="SECRET32", totp_enabled=True, email_verification_token="tok123",
    )
    db_session.add(user)
    db_session.commit()

    pd_deletion.finalize_deletion(db_session, user)

    assert user.totp_secret is None
    assert user.totp_enabled is False
    assert user.email_verification_token is None

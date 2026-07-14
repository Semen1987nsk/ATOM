"""PD-экспорт (152-ФЗ) не должен утекать 2FA-секрет и verification-токен."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from services.pd_export import build_user_export


def test_export_excludes_secrets(db_session):
    user = models.User(
        email="s@e.com", name="S", hashed_password="x", is_active=1, settings={},
        totp_secret="SUPERSECRET32", totp_enabled=True,
        email_verification_token="verif-token-abc",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    export = build_user_export(db_session, user)
    flat = str(export)
    # Секреты не должны присутствовать ни под каким ключом верхнего user-объекта.
    assert "SUPERSECRET32" not in flat, "totp_secret утёк в экспорт"
    assert "verif-token-abc" not in flat, "email_verification_token утёк в экспорт"
    assert "x" != export["user"].get("hashed_password"), "hashed_password утёк в экспорт"
    assert "hashed_password" not in export["user"]
    assert "totp_secret" not in export["user"]
    assert "email_verification_token" not in export["user"]
    assert "tokens_valid_after" not in export["user"]

    # Легитимный ПД остаётся в экспорте — не переусердствовали с exclude.
    assert export["user"]["email"] == "s@e.com"
    assert export["user"]["name"] == "S"
    assert export["user"]["totp_enabled"] is True

"""
S1-05: 401 зарезервирован ИСКЛЮЧИТЕЛЬНО за сессионной аутентификацией
(get_current_user). Ошибка невалидного/отозванного БРОКЕРСКОГО (T-Bank)
токена не должна отдавать 401 — иначе apiClient.ts на любой не-auth 401
делает refresh→retry→clearAuthTokens()+dispatchEvent('auth:logout'),
принудительно выкидывая юзера из приложения из-за проблемы с брокером,
а не с его сессией.

Проверяем:
* статический grep всех `except TokenInvalid` в broker.py/real_pnl.py —
  ни один не отдаёт 401;
* реальный HTTP-прогон GET /broker/portfolio с замоканным TokenInvalid
  из client_factory.async_client — код ответа 424, не 401;
* реальный HTTP-прогон GET /real-pnl/ — то же самое;
* сессионная 401 (запрос без токена) остаётся 401 — не задета фиксом.
"""

import os
import re
import sys
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth_service
from database import get_db
from domain.exceptions import TokenInvalid
from main import app
from models import Account, Base, BrokerConnection, BrokerType, User

BASE = os.path.dirname(os.path.abspath(__file__))
ROUTERS_DIR = os.path.join(os.path.dirname(BASE), "routers")


def _token_invalid_status_codes(path):
    src = open(path, encoding="utf-8").read()
    codes = []
    for m in re.finditer(
        r"except\s+TokenInvalid\s*:(.+?)(?=\n\s*except|\n\s*return|\n@|\Z)",
        src,
        re.S,
    ):
        block = m.group(1)
        for c in re.finditer(r"status_code=(\d+)", block):
            codes.append(int(c.group(1)))
    return codes


def test_broker_token_invalid_never_returns_401_static():
    """Статический контроль: ни один except TokenInvalid не отдаёт 401.

    401 зарезервирован за сессионной auth. connect_broker/verify-token
    (echo-валидация НОВОГО токена от юзера, broker.py ~318) намеренно
    остаются на 400 — это не broker-token-in-use сценарий, туда не лезем.
    """
    for rel in ("broker.py", "real_pnl.py"):
        codes = _token_invalid_status_codes(os.path.join(ROUTERS_DIR, rel))
        assert codes, f"не нашёл except TokenInvalid в {rel}"
        assert 401 not in codes, f"{rel}: TokenInvalid всё ещё отдаёт 401 ({codes})"


@pytest.fixture
def test_app():
    """Fresh in-memory DB per test (паттерн из test_pr26_endpoints)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db_session = TestingSessionLocal()
    yield {"client": TestClient(app), "db": db_session}
    db_session.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _user_account_conn(db):
    u = User(
        email="brokertoken@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(user_id=u.id, name="Main", currency="RUB")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    conn = BrokerConnection(
        account_id=acc.id,
        broker=BrokerType.TINKOFF,
        api_token="ciphertext-stub",
        broker_account_id="2135909232",
        is_active=True,
        auto_sync_enabled=True,
        sync_interval_minutes=60,
        total_synced_trades=0,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return u, acc, conn


def _auth_headers(user):
    token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return {"Authorization": f"Bearer {token}"}


@asynccontextmanager
async def _raising_async_client(_token):
    """Имитирует client_factory.async_client, чей __aenter__ бросает TokenInvalid
    (T-Bank отклонил невалидный/отозванный токен)."""
    raise TokenInvalid("revoked")
    yield  # pragma: no cover - недостижимо, нужен для генератора


def test_get_portfolio_returns_424_on_broker_token_invalid(test_app):
    """GET /broker/portfolio с отозванным T-Bank токеном -> 424, НЕ 401."""
    db = test_app["db"]
    user, acc, conn = _user_account_conn(db)

    with patch("routers.broker.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.broker._token_repo"
    ) as mock_repo, patch(
        "routers.broker.client_factory.async_client", side_effect=_raising_async_client
    ):
        mock_repo.return_value.get_decrypted.return_value = "t.fake"
        r = test_app["client"].get("/broker/portfolio", headers=_auth_headers(user))

    assert r.status_code == 424, r.text
    assert r.status_code != 401


def test_real_pnl_returns_424_on_broker_token_invalid(test_app):
    """GET /real-pnl/ с отозванным T-Bank токеном -> 424, НЕ 401."""
    db = test_app["db"]
    user, acc, conn = _user_account_conn(db)

    with patch("routers.real_pnl.settings.BROKER_SYNC_V2_ENABLED", True), patch(
        "routers.real_pnl.TokenRepository"
    ) as mock_repo, patch(
        "routers.real_pnl.client_factory.async_client", side_effect=_raising_async_client
    ):
        mock_repo.return_value.get_decrypted.return_value = "t.fake"
        r = test_app["client"].get("/real-pnl/", headers=_auth_headers(user))

    assert r.status_code == 424, r.text
    assert r.status_code != 401


def test_session_auth_still_returns_401(test_app):
    """Сессионная auth (get_current_user) без токена вообще -> остаётся 401."""
    r = test_app["client"].get("/broker/portfolio")
    assert r.status_code == 401

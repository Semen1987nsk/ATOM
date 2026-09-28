"""
DATA-03: удаление Account не должно оставлять BrokerConnection-сирот.

BrokerConnection хранит зашифрованный api_token брокера (персональные
данные, 152-ФЗ). Раньше relationship со стороны Account был backref'ом
без cascade — при ORM-delete аккаунта SQLAlchemy выставлял
account_id=NULL вместо удаления строки, и токен оставался в БД сиротой.

Проверяем: delete(Account) через ORM удаляет строку broker_connections
целиком (count==0), а не FK-NULL'ит её.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Account, Base, BrokerConnection, BrokerType, User


@pytest.fixture
def db():
    """Fresh in-memory DB per test (паттерн из test_broker_connections_visibility)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _make_user_account_connection(db):
    user = User(email="user@test.com", hashed_password="x", is_active=1)
    db.add(user)
    db.commit()
    db.refresh(user)
    acc = Account(user_id=user.id, name="Main", currency="RUB")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    conn = BrokerConnection(
        account_id=acc.id,
        broker=BrokerType.TINKOFF,
        api_token="ciphertext-stub",
        broker_account_id="2000000001",
        is_active=True,
        auto_sync_enabled=True,
        sync_interval_minutes=60,
        total_synced_trades=0,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return user, acc, conn


def test_delete_account_deletes_broker_connection(db):
    """ORM-delete аккаунта удаляет BrokerConnection, не оставляя сироту с NULL FK."""
    _user, acc, _conn = _make_user_account_connection(db)

    db.delete(acc)
    db.commit()

    remaining = db.scalar(select(func.count()).select_from(BrokerConnection))
    assert remaining == 0, (
        f"broker_connections должна быть пуста после удаления Account, "
        f"осталось строк: {remaining} (FK-NULL сирота = утечка токена, 152-ФЗ)"
    )


def test_delete_account_leaves_no_null_fk_orphans(db):
    """Явная проверка анти-паттерна: строка с account_id=NULL недопустима."""
    _user, acc, _conn = _make_user_account_connection(db)

    db.delete(acc)
    db.commit()

    orphans = db.scalar(
        select(func.count())
        .select_from(BrokerConnection)
        .where(BrokerConnection.account_id.is_(None))
    )
    assert orphans == 0, "BrokerConnection с account_id=NULL — осиротевший токен"

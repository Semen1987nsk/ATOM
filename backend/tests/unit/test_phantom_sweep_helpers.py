"""Helpers для phantom sweep: цены и проверка recent operations."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from models import Base
from application.sync.phantom_sweep_helpers import (
    last_known_price, has_recent_operations,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_last_known_price_from_position_current_price(session):
    """Если Position имеет current_price — возвращаем его."""
    pos = models.PositionORM(
        account_id=1, instrument_uid="uid-1", instrument_type="futures",
        quantity=10, avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("50"),
    )
    session.add(pos)
    session.commit()

    assert last_known_price(session, "uid-1") == Decimal("105")


def test_last_known_price_returns_none_when_no_position(session):
    """Если Position строки нет (она удалена при закрытии позиции) — None."""
    assert last_known_price(session, "uid-missing") is None


def test_has_recent_operations_true_when_recent(session):
    """Recent operation в последние 24h → True (защита от Tinkoff blip)."""
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-1000, payment_nano=0,
        executed_at=now - timedelta(hours=2),
    )
    session.add(op)
    session.commit()

    assert has_recent_operations(session, 1, hours=24, now=now) is True


def test_has_recent_operations_false_when_old(session):
    """Нет recent ops в 24h → False (sweep можно делать смело)."""
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    op = models.OperationORM(
        operation_id="op-old", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-1000, payment_nano=0,
        executed_at=now - timedelta(days=5),
    )
    session.add(op)
    session.commit()

    assert has_recent_operations(session, 1, hours=24, now=now) is False

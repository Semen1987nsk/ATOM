"""
Регрессия: `_stage_fifo_match` падал с
`ValueError: not enough values to unpack (expected 3, got 2)`, когда операция
ссылалась на `instrument_uid`, которого нет в локальном справочнике
(T-Bank `GetInstrumentBy` → `NOT_FOUND 50002`, стадия enrich его пропустила).

Ранний выход `if instrument is None: return 0, 0` возвращал 2 значения, а
вызывающий код распаковывает 3 (`trades, positions, mae_ids`). Любой аккаунт
с хотя бы одним неразрешимым инструментом → весь sync падал, и фронт показывал
«Failed to fetch» (необработанное исключение рвало ответ через
BaseHTTPMiddleware).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.sync.pipeline import SyncPipeline
from domain.entities import Operation
from domain.enums import InstrumentType, OperationState, OperationType
from domain.value_objects import MoneyValue
from models import Account, Base, User


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_fifo_missing_instr.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        yield Session
    finally:
        engine.dispose()


@pytest.fixture
def account_id(db_session_factory) -> int:
    with db_session_factory() as s:
        user = User(email="fifo-missing@test.local", name="t", is_active=1)
        s.add(user)
        s.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        s.add(account)
        s.commit()
        return account.id


def _op_for_unresolvable_instrument() -> Operation:
    return Operation(
        operation_id="op-1",
        account_id="acc-1",
        instrument_uid="uid-does-not-exist",  # отсутствует в InstrumentRepository
        instrument_figi="",
        instrument_type=InstrumentType.SHARE,
        operation_type=OperationType.BUY,
        state=OperationState.EXECUTED,
        quantity=10,
        price=MoneyValue.from_decimal(100, "rub"),
        payment=MoneyValue.from_decimal(-1000, "rub"),
        executed_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
    )


def test_fifo_match_skips_unresolved_instrument_without_crashing(
    db_session_factory, account_id
) -> None:
    """Неразрешимый инструмент должен молча пропускаться, а не валить весь sync."""
    pipeline = SyncPipeline(
        account_id=account_id,
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_session_factory,
    )
    op = _op_for_unresolvable_instrument()

    # До фикса: ValueError: not enough values to unpack (expected 3, got 2).
    trades, positions = asyncio.run(pipeline._stage_fifo_match([op]))

    assert trades == 0
    assert positions == 0

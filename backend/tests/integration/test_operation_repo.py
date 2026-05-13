"""
Integration-тесты `OperationRepository` (PR 5 Stage 1).

Проверяем:

* UPSERT идемпотентен: вторая вставка тех же операций не плодит дубликаты,
* Изменения (например, state: PROGRESS → EXECUTED) применяются на UPSERT,
* save_cursor → get_last_cursor round-trip,
* fetch_for_instrument возвращает в хронологическом порядке,
* list_unique_instrument_uids исключает NULL.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.operation_repo import OperationRepository
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from domain.entities import Operation
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
)
from domain.value_objects import MoneyValue
from models import Account, Base, BrokerConnection, OperationORM, User


# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_op_repo.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield Session
    engine.dispose()


@pytest.fixture
def setup(db_session_factory):
    """Создаём User + Account + активный BrokerConnection."""
    with db_session_factory() as session:
        user = User(
            email=f"u-{secrets.token_hex(4)}@test.local",
            name="t",
            is_active=1,
        )
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, name="A1", currency="RUB")
        session.add(account)
        session.flush()
        account_id = account.id
        broker_account_id = "2135909232"

        # store BrokerConnection через TokenRepository
        enc = TokenEncryptionService(
            active_keys={1: secrets.token_bytes(32)}, current_key_id=1
        )
        token_repo = TokenRepository(encryption=enc)
        token_repo.store(
            session,
            account_id=account_id,
            broker_account_id=broker_account_id,
            plaintext_token="t.fake.dummy",
        )
        session.commit()

    return {"account_id": account_id, "broker_account_id": broker_account_id}


def _make_op(
    *,
    op_id: str,
    instrument_uid: str = "uid-X",
    operation_type: OperationType = OperationType.BUY,
    state: OperationState = OperationState.EXECUTED,
    quantity: int = 10,
    price_units: int = 100,
    payment_units: int = -1000,
    executed_at: datetime | None = None,
    account_id_str: str = "2135909232",
) -> Operation:
    return Operation(
        operation_id=op_id,
        account_id=account_id_str,
        instrument_uid=instrument_uid,
        instrument_figi="FIGI-X",
        instrument_type=InstrumentType.SHARE,
        operation_type=operation_type,
        state=state,
        quantity=quantity,
        price=MoneyValue(units=price_units, nano=0, currency="rub"),
        payment=MoneyValue(units=payment_units, nano=0, currency="rub"),
        commission=MoneyValue(units=0, nano=-50_000_000, currency="rub"),  # -0.05
        executed_at=executed_at or datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
    )


# ── tests ─────────────────────────────────────────────────────────────


def test_upsert_idempotent(db_session_factory, setup) -> None:
    repo = OperationRepository()
    ops = [_make_op(op_id=f"op-{i}") for i in range(5)]

    with db_session_factory() as session:
        n1 = repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=ops,
        )
        session.commit()
    assert n1 == 5

    # Повторный sync с теми же операциями — не должно появиться дубликатов.
    with db_session_factory() as session:
        repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=ops,
        )
        session.commit()

    with db_session_factory() as session:
        total = session.query(OperationORM).count()
    assert total == 5


def test_upsert_updates_changed_fields(db_session_factory, setup) -> None:
    """Операция в state=PROGRESS, потом приходит обновление до EXECUTED."""
    repo = OperationRepository()

    progress = _make_op(op_id="op-1", state=OperationState.PROGRESS)
    with db_session_factory() as session:
        repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=[progress],
        )
        session.commit()

    executed = _make_op(op_id="op-1", state=OperationState.EXECUTED)
    with db_session_factory() as session:
        repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=[executed],
        )
        session.commit()

    with db_session_factory() as session:
        row = (
            session.query(OperationORM)
            .filter_by(operation_id="op-1")
            .one()
        )
    assert row.state == "executed"


def test_save_and_get_cursor(db_session_factory, setup) -> None:
    repo = OperationRepository()
    with db_session_factory() as session:
        assert repo.get_last_cursor(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
        ) in (None, "")

    with db_session_factory() as session:
        repo.save_cursor(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            cursor="next-cursor-123",
        )
        session.commit()

    with db_session_factory() as session:
        got = repo.get_last_cursor(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
        )
    assert got == "next-cursor-123"


def test_save_cursor_resets_failures_on_success(db_session_factory, setup) -> None:
    repo = OperationRepository()
    with db_session_factory() as session:
        conn = (
            session.query(BrokerConnection)
            .filter_by(account_id=setup["account_id"])
            .one()
        )
        conn.consecutive_failures = 5
        conn.circuit_open_until = datetime(2026, 5, 15, 0, 0)
        session.commit()

    with db_session_factory() as session:
        repo.save_cursor(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            cursor="c-2",
            last_sync_status="success",
        )
        session.commit()

    with db_session_factory() as session:
        conn = (
            session.query(BrokerConnection)
            .filter_by(account_id=setup["account_id"])
            .one()
        )
    assert conn.consecutive_failures == 0
    assert conn.circuit_open_until is None
    assert conn.last_sync_status == "success"
    assert conn.last_sync_at is not None


def test_fetch_for_instrument_chronological(db_session_factory, setup) -> None:
    repo = OperationRepository()
    base = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    ops = [
        _make_op(op_id="late", executed_at=base + timedelta(days=5)),
        _make_op(op_id="early", executed_at=base),
        _make_op(op_id="mid", executed_at=base + timedelta(days=2)),
    ]
    with db_session_factory() as session:
        repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=ops,
        )
        session.commit()

    with db_session_factory() as session:
        fetched = repo.fetch_for_instrument(
            session,
            account_id=setup["account_id"],
            instrument_uid="uid-X",
        )
    assert [op.operation_id for op in fetched] == ["early", "mid", "late"]
    # MoneyValue должен round-trip'нуться.
    assert fetched[0].payment is not None
    assert fetched[0].payment.to_decimal() == Decimal("-1000")
    assert fetched[0].commission is not None
    assert fetched[0].commission.to_decimal() == Decimal("-0.05")


def test_list_unique_instrument_uids_skips_null(db_session_factory, setup) -> None:
    repo = OperationRepository()
    ops = [
        _make_op(op_id="o1", instrument_uid="uid-A"),
        _make_op(op_id="o2", instrument_uid="uid-A"),  # dup uid
        _make_op(op_id="o3", instrument_uid="uid-B"),
    ]
    # PayIn без instrument_uid
    payin = Operation(
        operation_id="o-payin",
        account_id="2135909232",
        operation_type=OperationType.INPUT,
        state=OperationState.EXECUTED,
        executed_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
    )

    with db_session_factory() as session:
        repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=ops + [payin],
        )
        session.commit()

    with db_session_factory() as session:
        uids = repo.list_unique_instrument_uids(
            session, account_id=setup["account_id"]
        )
    assert sorted(uids) == ["uid-A", "uid-B"]


def test_count_by_account(db_session_factory, setup) -> None:
    repo = OperationRepository()
    ops = [_make_op(op_id=f"o{i}") for i in range(7)]
    with db_session_factory() as session:
        repo.upsert_many(
            session,
            account_id=setup["account_id"],
            broker_account_id=setup["broker_account_id"],
            operations=ops,
        )
        session.commit()

    with db_session_factory() as session:
        assert repo.count_by_account(session, account_id=setup["account_id"]) == 7

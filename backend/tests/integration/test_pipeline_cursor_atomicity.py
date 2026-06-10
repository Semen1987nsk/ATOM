"""SYNC-08: cursor сдвигается только после успешного FIFO+positions+health.

Инвариант: если процесс упал на любой пост-upsert стадии (FIFO matching,
mark-to-market, health audit и т.д.) — `BrokerConnection.sync_cursor` ДОЛЖЕН
остаться прежним. При следующем sync курсор вернётся к предыдущей точке и
заново перестроит trades/positions поверх уже сохранённых operations.

Раньше `_stage_upsert` коммитил курсор в той же транзакции что и upsert_many,
ДО FIFO-стадии. При падении на FIFO курсор уже был сдвинут — operations
сохранены, но trades/positions не построены, и следующий sync шёл с уже
обновлённого курсора, теряя возможность довосстановить.

После SYNC-08:
* `_stage_upsert` — только upsert операций (без курсора).
* `_stage_commit_cursor` — отдельный метод, вызывается ПОСЛЕ всех success-стадий.
"""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from application.sync.pipeline import SyncPipeline
from domain.entities import Instrument, Operation
from domain.enums import InstrumentType, OperationState, OperationType
from domain.value_objects import MoneyValue
from models import Account, Base, BrokerConnection, OperationORM, User


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_pipeline_cursor_atomicity.db"
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
def setup(db_session_factory) -> dict:
    """User + Account + BrokerConnection с pre-existing sync_cursor."""
    with db_session_factory() as session:
        user = User(email="atomicity@test.local", name="t", is_active=1)
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        session.add(account)
        session.flush()
        enc = TokenEncryptionService(
            active_keys={1: secrets.token_bytes(32)}, current_key_id=1
        )
        repo = TokenRepository(encryption=enc)
        conn = repo.store(
            session,
            account_id=account.id,
            broker_account_id="acc-1",
            plaintext_token="t.fake",
        )
        # Преднастроенный курсор: убедимся, что fallback на FIFO failure его НЕ сдвинет.
        conn.sync_cursor = "PREEXISTING_CURSOR_XYZ"
        session.commit()
        return {
            "account_id": account.id,
            "connection_id": conn.id,
            "initial_cursor": "PREEXISTING_CURSOR_XYZ",
        }


def _op(op_id: str, type_: OperationType, qty: int, price, executed_at) -> Operation:
    payment_sign = -1 if type_ == OperationType.BUY else 1
    return Operation(
        operation_id=op_id,
        account_id="acc-1",
        instrument_uid="uid-sber",
        instrument_figi="BBG004730N88",
        instrument_type=InstrumentType.SHARE,
        operation_type=type_,
        state=OperationState.EXECUTED,
        quantity=qty,
        price=MoneyValue.from_decimal(price, "rub"),
        payment=MoneyValue.from_decimal(payment_sign * price * qty, "rub"),
        executed_at=executed_at,
    )


@asynccontextmanager
async def _fake_async_client(_token):
    yield MagicMock()


def _make_fake_clients(ops_pages, instrument):
    fake_ops = MagicMock()
    page_iter = iter(ops_pages)

    async def fake_fetch(*args, **kwargs):
        try:
            page, cursor = next(page_iter)
        except StopIteration:
            return [], ""
        return page, cursor

    fake_ops.fetch_operations_cursor = fake_fetch
    fake_ops.get_portfolio_raw = AsyncMock(return_value=MagicMock(positions=[]))

    fake_instr = MagicMock()

    async def fake_get_instr(_uid):
        return instrument

    fake_instr.get_instrument_by_uid = fake_get_instr

    fake_md = MagicMock()
    fake_md.get_last_prices = AsyncMock(return_value={})
    return fake_ops, fake_instr, fake_md


def _patched_run(pipeline, fake_ops, fake_instr, fake_md, *, full_sync: bool):
    with patch(
        "application.sync.pipeline.client_factory.async_client",
        side_effect=_fake_async_client,
    ), patch(
        "application.sync.pipeline.TinkoffOperationsClient",
        return_value=fake_ops,
    ), patch(
        "application.sync.pipeline.TinkoffInstrumentsClient",
        return_value=fake_instr,
    ), patch(
        "application.sync.pipeline.TinkoffMarketDataClient",
        return_value=fake_md,
    ):
        return asyncio.run(pipeline.run(full_sync=full_sync))


def test_cursor_not_advanced_if_fifo_fails(db_session_factory, setup) -> None:
    """SYNC-08: при исключении в _stage_fifo_match cursor не сдвигается.

    Operations должны быть upsert'нуты (это safe — idempotent), но курсор
    остаётся прежним, чтобы при следующем sync можно было довосстановить
    FIFO/positions с той же точки.
    """
    instrument = Instrument(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        instrument_type=InstrumentType.SHARE,
    )
    base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
    ops_pages = [
        ([_op("op-1", OperationType.BUY, 10, 100, base)], "NEW_CURSOR_should_not_be_saved"),
    ]
    fake_ops, fake_instr, fake_md = _make_fake_clients(ops_pages, instrument)

    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_session_factory,
    )

    # Симулируем падение на FIFO-стадии: к этому моменту _stage_upsert уже
    # должен был вставить операции, но курсор НЕ должен быть сдвинут.
    with patch.object(
        pipeline, "_stage_fifo_match", side_effect=RuntimeError("boom-fifo")
    ):
        with pytest.raises(RuntimeError, match="boom-fifo"):
            _patched_run(
                pipeline, fake_ops, fake_instr, fake_md, full_sync=False
            )

    # Курсор должен остаться pre-existing значением.
    with db_session_factory() as session:
        conn = (
            session.query(BrokerConnection)
            .filter_by(id=setup["connection_id"])
            .one()
        )
        ops_count = session.query(OperationORM).count()

    assert conn.sync_cursor == setup["initial_cursor"], (
        f"курсор сдвинулся при FIFO failure: ожидали {setup['initial_cursor']!r}, "
        f"получили {conn.sync_cursor!r}"
    )
    # Статус ошибки должен быть выставлен через _save_error_state.
    assert conn.last_sync_status == "error", (
        f"last_sync_status должен быть 'error' после падения, got {conn.last_sync_status!r}"
    )
    # Operations должны быть upsert'нуты — это нормально, upsert идемпотентен,
    # а cursor останется на старой точке для повторного FIFO-прогона.
    assert ops_count == 1, (
        f"operations должны были быть upsert'нуты до FIFO стадии, got {ops_count}"
    )


def test_cursor_advanced_on_success(db_session_factory, setup) -> None:
    """SYNC-08 regression: при успешном sync курсор всё-таки сдвигается.

    Дополнительная защита: убедимся, что разделение методов не сломало
    happy-path — после полностью успешного pipeline новый cursor сохраняется.
    """
    instrument = Instrument(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        instrument_type=InstrumentType.SHARE,
    )
    base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
    ops_pages = [
        ([_op("op-1", OperationType.BUY, 10, 100, base)], "NEW_CURSOR_after_success"),
    ]
    fake_ops, fake_instr, fake_md = _make_fake_clients(ops_pages, instrument)

    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_session_factory,
    )
    report = _patched_run(pipeline, fake_ops, fake_instr, fake_md, full_sync=True)
    assert report.success

    with db_session_factory() as session:
        conn = (
            session.query(BrokerConnection)
            .filter_by(id=setup["connection_id"])
            .one()
        )
    assert conn.sync_cursor == "NEW_CURSOR_after_success"
    assert conn.last_sync_status == "success"

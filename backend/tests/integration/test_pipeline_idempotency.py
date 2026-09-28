"""
Integration-тесты идемпотентности `SyncPipeline` (PR 14).

Симулируем gRPC-клиент через моки и убеждаемся что:
* двойной прогон с теми же операциями не плодит дубликаты в БД,
* `sync_cursor` сохраняется после первого прогона,
* второй прогон с тем же cursor'ом ничего не вставляет (operations_synced=0).

Используем sqlite tmp_path БД — изолированно от прода.
"""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from application.sync.pipeline import SyncPipeline
from domain.entities import Instrument, Operation
from domain.enums import (
    InstrumentType,
    OperationState,
    OperationType,
)
from domain.value_objects import MoneyValue
from models import Account, Base, BrokerConnection, OperationORM, User
from models import Trade as TradeORM


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_pipeline_idemp.db"
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
    with db_session_factory() as session:
        user = User(email="p@test.local", name="t", is_active=1)
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
        session.commit()
        return {"account_id": account.id, "connection_id": conn.id}


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
    """Возвращает три mock-класса: Operations/Instruments/MarketData."""
    from unittest.mock import AsyncMock

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


def test_double_run_no_duplicates(db_session_factory, setup) -> None:
    """Два прогона с одним набором операций → операции не дублируются."""
    instrument = Instrument(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        instrument_type=InstrumentType.SHARE,
    )
    base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
    operations = [
        _op("op-buy", OperationType.BUY, 100, 270, base),
        _op(
            "op-sell",
            OperationType.SELL,
            100,
            275,
            base.replace(hour=12),
        ),
    ]
    ops_pages = [(operations, "cursor-1")]

    # Запоминаем экземпляры fake-классов между вызовами SyncPipeline.
    fake_ops, fake_instr, fake_md = _make_fake_clients(ops_pages, instrument)

    def _run_once() -> int:
        pipeline = SyncPipeline(
            account_id=setup["account_id"],
            broker_account_id="acc-1",
            token_plaintext="t.fake",
            session_factory=db_session_factory,
        )
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
            return asyncio.run(pipeline.run(full_sync=True))

    report1 = _run_once()
    assert report1.success
    assert report1.operations_total == 2

    # Сбрасываем итератор страниц — второй прогон будет «новый pull», но
    # вернёт те же операции.
    ops_pages2 = [(operations, "cursor-1")]
    fake_ops2, fake_instr2, fake_md2 = _make_fake_clients(ops_pages2, instrument)
    pipeline2 = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_session_factory,
    )
    with patch(
        "application.sync.pipeline.client_factory.async_client",
        side_effect=_fake_async_client,
    ), patch(
        "application.sync.pipeline.TinkoffOperationsClient",
        return_value=fake_ops2,
    ), patch(
        "application.sync.pipeline.TinkoffInstrumentsClient",
        return_value=fake_instr2,
    ), patch(
        "application.sync.pipeline.TinkoffMarketDataClient",
        return_value=fake_md2,
    ):
        report2 = asyncio.run(pipeline2.run(full_sync=False))
    assert report2.success

    with db_session_factory() as session:
        ops_count = session.query(OperationORM).count()
        trades_count = session.query(TradeORM).count()

    # Те же 2 операции, не 4. Trade-запись 1 (закрытая sell-операцией).
    assert ops_count == 2, f"expected 2 operations after dual sync, got {ops_count}"
    assert trades_count == 1


def test_cursor_saved_after_sync(db_session_factory, setup) -> None:
    instrument = Instrument(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        instrument_type=InstrumentType.SHARE,
    )
    base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
    ops_pages = [
        ([_op("op-1", OperationType.BUY, 10, 100, base)], "saved-cursor-xyz"),
    ]
    fake_ops, fake_instr, fake_md = _make_fake_clients(ops_pages, instrument)
    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_session_factory,
    )
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
        asyncio.run(pipeline.run(full_sync=True))

    with db_session_factory() as session:
        conn = (
            session.query(BrokerConnection)
            .filter_by(id=setup["connection_id"])
            .one()
        )
    assert conn.sync_cursor == "saved-cursor-xyz"
    assert conn.last_sync_status == "success"
    assert conn.last_sync_at is not None


def test_sync_schedules_mae_backfill_for_closed_trades(db_session_factory, setup) -> None:
    """MAE-05: после FIFO-пересборки закрытые сделки без MAE/MFE уходят в
    schedule_mae_mfe_backfill — иначе sync-сделки ждут значений до суток
    (nightly), а история старше 30 дней не получает их никогда."""
    instrument = Instrument(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        instrument_type=InstrumentType.SHARE,
    )
    base = datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc)
    operations = [
        _op("op-buy", OperationType.BUY, 100, 270, base),
        _op("op-sell", OperationType.SELL, 100, 275, base.replace(hour=12)),
    ]
    fake_ops, fake_instr, fake_md = _make_fake_clients([(operations, "c1")], instrument)

    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_session_factory,
    )
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
    ), patch(
        "import_service.schedule_mae_mfe_backfill"
    ) as mock_backfill:
        report = asyncio.run(pipeline.run(full_sync=True))

    assert report.success
    mock_backfill.assert_called_once()
    scheduled_ids = mock_backfill.call_args[0][0]
    with db_session_factory() as session:
        closed = (
            session.query(TradeORM)
            .filter(TradeORM.exit_at.isnot(None))
            .all()
        )
    assert len(closed) == 1
    assert scheduled_ids == [closed[0].id]

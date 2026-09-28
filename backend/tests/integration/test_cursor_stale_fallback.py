"""
Regression test для AU3+ (2026-05-19): cursor может вернуть batch старых
operations + next_cursor='', и SyncPipeline должен это распознать как stale
cursor и переключиться на from_dt-based fetch.

Real-world симптом этого бага: T-Bank cursor застрял на дате ~2 года назад,
incremental sync крутится в петле "получили 221 дубликат, inserted=0,
сохранили тот же cursor". Свежие SELL operations никогда не попадают в БД,
phantom_sweep пытается закрыть позиции fallback exit=entry → P&L 0 ₽.

Original AU3 ловил только empty batch. Здесь покрываем «не пустой, но
устаревший» сценарий.
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
    db_path = tmp_path / "test_cursor_stale.db"
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
    """Создаёт юзера/аккаунт/токен. Возвращает account_id и connection_id."""
    with db_session_factory() as session:
        user = User(email="stale@test.local", name="t", is_active=1)
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
            broker_account_id="acc-stale",
            plaintext_token="t.fake",
        )
        session.commit()
        return {"account_id": account.id, "connection_id": conn.id}


def _op(op_id: str, otype: OperationType, qty: int, price: float, executed_at: datetime) -> Operation:
    payment_sign = -1 if otype == OperationType.BUY else 1
    return Operation(
        operation_id=op_id,
        account_id="acc-stale",
        instrument_uid="uid-sber",
        instrument_figi="BBG004730N88",
        instrument_type=InstrumentType.SHARE,
        operation_type=otype,
        state=OperationState.EXECUTED,
        quantity=qty,
        price=MoneyValue.from_decimal(price, "rub"),
        payment=MoneyValue.from_decimal(payment_sign * price * qty, "rub"),
        executed_at=executed_at,
    )


@asynccontextmanager
async def _fake_async_client(_token):
    yield MagicMock()


def test_stale_cursor_returning_old_batch_triggers_fallback(
    db_session_factory, setup
) -> None:
    """
    Setup:
      - DB уже содержит свежую operation от 2026-05-15 (BUY 100 SBER @ 270).
      - sync_cursor='stuck-cursor' сохранён.
    Когда вызывается fetch_operations_cursor:
      - С cursor='stuck-cursor' возвращаем СТАРУЮ operation от 2024-09-10 (дубликат)
        + next_cursor=''. Это и есть симулированный stale cursor.
      - С cursor='' + from_dt должны вернуть свежую SELL от 2026-05-19 + next_cursor=''.
    Expected:
      - Pipeline должен распознать что batch_max < db_max → fallback.
      - SELL operation от 2026-05-19 попадает в БД.
      - Σ ops в БД = 3 (1 pre-existing BUY + 1 stale BUY дубликат идемпотентно
        upsert'нется в ту же строку + 1 SELL).
    """
    instrument = Instrument(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        instrument_type=InstrumentType.SHARE,
    )

    # 1) Pre-populate БД свежей operation. БД хранит naive UTC.
    fresh_buy_at_naive = datetime(2026, 5, 15, 10, 0)
    with db_session_factory() as session:
        session.add(
            OperationORM(
                account_id=setup["account_id"],
                broker_account_id="acc-stale",
                operation_id="pre-buy",
                instrument_uid="uid-sber",
                instrument_figi="BBG004730N88",
                instrument_type="share",
                operation_type="buy",
                state="executed",
                quantity=100,
                price_units=270,
                price_nano=0,
                price_currency="rub",
                payment_units=-27000,
                payment_nano=0,
                payment_currency="rub",
                executed_at=fresh_buy_at_naive,
            )
        )
        # И застаримим cursor
        conn = (
            session.query(BrokerConnection)
            .filter_by(id=setup["connection_id"])
            .one()
        )
        conn.sync_cursor = "stuck-cursor"
        session.commit()

    # 2) Симуляция Tinkoff API.
    old_op = _op(
        "old-2024",
        OperationType.BUY,
        1,
        100,
        datetime(2024, 9, 10, 12, 0, tzinfo=timezone.utc),
    )
    fresh_sell = _op(
        "fresh-sell",
        OperationType.SELL,
        100,
        275,
        datetime(2026, 5, 19, 6, 3, tzinfo=timezone.utc),
    )

    call_log: list[dict] = []

    async def fake_fetch(account_id, *, cursor, limit, from_dt=None, to_dt=None):
        call_log.append({"cursor": cursor, "from_dt": from_dt})
        if cursor == "stuck-cursor":
            # Stale batch: возвращаем старую operation + next_cursor='' (значит "история закончилась").
            return [old_op], ""
        if cursor == "" and from_dt is not None:
            # Fallback: возвращаем свежую SELL.
            return [fresh_sell], ""
        return [], ""

    fake_ops = MagicMock()
    fake_ops.fetch_operations_cursor = fake_fetch
    fake_ops.get_portfolio_raw = AsyncMock(return_value=MagicMock(positions=[]))

    fake_instr = MagicMock()

    async def fake_get_instr(_uid):
        return instrument

    fake_instr.get_instrument_by_uid = fake_get_instr

    fake_md = MagicMock()
    fake_md.get_last_prices = AsyncMock(return_value={})

    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-stale",
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
        report = asyncio.run(pipeline.run(full_sync=False))

    assert report.success, f"Pipeline failed: {report.error_message}"

    # Должен быть как минимум 1 вызов с stuck-cursor + 1 fallback с cursor=""
    assert len(call_log) >= 2, f"expected >=2 fetch calls, got {len(call_log)}: {call_log}"
    assert call_log[0]["cursor"] == "stuck-cursor"
    # Где-то в call_log должен быть вызов с пустым cursor И from_dt не None
    fallback_calls = [c for c in call_log if c["cursor"] == "" and c["from_dt"] is not None]
    assert fallback_calls, f"AU3+ fallback не сработал; calls: {call_log}"

    # SELL operation теперь в БД
    with db_session_factory() as session:
        op_ids = {
            o.operation_id
            for o in session.query(OperationORM)
            .filter(OperationORM.account_id == setup["account_id"])
            .all()
        }
    assert "fresh-sell" in op_ids, f"fresh-sell missing in DB, got: {op_ids}"

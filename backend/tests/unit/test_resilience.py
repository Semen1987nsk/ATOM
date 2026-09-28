"""
Unit-тесты PR 15 (resilience):

* tenacity retry на `fetch_operations_cursor`: транзиентная ошибка → успех
  после ретрая, нон-ретраяемая → проброс.
* `_save_error_state` + circuit breaker: 5 ошибок подряд → `circuit_open_until`.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from adapters.tinkoff.operations_client import TinkoffOperationsClient
from application.sync.pipeline import SyncPipeline
from domain.exceptions import (
    BrokerError,
    BrokerUnavailable,
    InstrumentNotFound,
    RateLimitExceeded,
    TokenInvalid,
)
from models import Account, Base, BrokerConnection, User


# ── tenacity retry ──────────────────────────────────────────────────


def test_retry_recovers_after_transient_failures(monkeypatch) -> None:
    """3 раза BrokerUnavailable → 4-я попытка успех."""
    services = MagicMock()
    call_counter = {"n": 0}

    async def flaky_get_operations(_request):
        call_counter["n"] += 1
        if call_counter["n"] <= 3:
            raise BrokerUnavailable("transient")
        # Возвращаем фейковый ответ.
        resp = MagicMock()
        resp.items = []
        resp.next_cursor = ""
        return resp

    services.operations.get_operations_by_cursor = flaky_get_operations
    client = TinkoffOperationsClient(services)

    # Ускоряем backoff чтобы тест не тянулся 60+ сек.
    monkeypatch.setattr(
        "adapters.tinkoff.operations_client.wait_exponential",
        lambda **kwargs: __import__("tenacity").wait_fixed(0.01),
    )
    monkeypatch.setattr(
        "adapters.tinkoff.operations_client.wait_random",
        lambda *a, **kw: __import__("tenacity").wait_fixed(0.01),
    )

    # Re-import чтобы перехватить новый _retry_policy.
    import importlib
    import adapters.tinkoff.operations_client as opmod

    importlib.reload(opmod)
    client = opmod.TinkoffOperationsClient(services)
    result = asyncio.run(client.fetch_operations_cursor("acc-1"))
    assert result == ([], "")
    assert call_counter["n"] == 4


def test_retry_does_not_recover_token_invalid() -> None:
    """TokenInvalid — не retryable, проброс с первой попытки."""
    services = MagicMock()
    call_counter = {"n": 0}

    async def bad_token(_request):
        call_counter["n"] += 1
        raise TokenInvalid("revoked")

    services.operations.get_operations_by_cursor = bad_token
    client = TinkoffOperationsClient(services)

    with pytest.raises(TokenInvalid):
        asyncio.run(client.fetch_operations_cursor("acc-1"))
    assert call_counter["n"] == 1  # без ретраев


def test_retry_does_not_recover_instrument_not_found() -> None:
    """InstrumentNotFound — non-retryable."""
    services = MagicMock()
    call_counter = {"n": 0}

    async def not_found(_request):
        call_counter["n"] += 1
        raise InstrumentNotFound("uid-xxx")

    services.operations.get_operations_by_cursor = not_found
    client = TinkoffOperationsClient(services)

    with pytest.raises(InstrumentNotFound):
        asyncio.run(client.fetch_operations_cursor("acc-1"))
    assert call_counter["n"] == 1


# ── circuit breaker ──────────────────────────────────────────────────


@pytest.fixture
def db_factory(tmp_path: Path):
    db_path = tmp_path / "test_resilience.db"
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
def setup(db_factory):
    with db_factory() as session:
        user = User(email="r@test.local", name="t", is_active=1)
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        session.add(account)
        session.flush()
        enc = TokenEncryptionService(active_keys={1: secrets.token_bytes(32)}, current_key_id=1)
        repo = TokenRepository(encryption=enc)
        conn = repo.store(
            session,
            account_id=account.id,
            broker_account_id="acc-1",
            plaintext_token="t.fake",
        )
        session.commit()
        return {"account_id": account.id, "connection_id": conn.id}


def test_circuit_breaker_opens_after_five_failures(db_factory, setup) -> None:
    """5 ошибок подряд → `circuit_open_until` устанавливается."""
    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_factory,
    )
    # 4 ошибки — circuit ещё закрыт.
    for _ in range(4):
        pipeline._save_error_state(BrokerUnavailable("blip"))
    with db_factory() as session:
        conn = session.query(BrokerConnection).filter_by(id=setup["connection_id"]).one()
        assert conn.consecutive_failures == 4
        assert conn.circuit_open_until is None

    # 5-я ошибка — circuit OPENS.
    pipeline._save_error_state(BrokerUnavailable("breaking point"))
    with db_factory() as session:
        conn = session.query(BrokerConnection).filter_by(id=setup["connection_id"]).one()
        assert conn.consecutive_failures == 5
        assert conn.circuit_open_until is not None
        # 15 минут вперёд (±небольшой epsilon на исполнение).
        delta = conn.circuit_open_until - datetime.utcnow()
        assert timedelta(minutes=14) < delta < timedelta(minutes=16)


def test_circuit_breaker_resets_on_success(db_factory, setup) -> None:
    """`OperationRepository.save_cursor(...status='success')` сбрасывает счётчик."""
    from adapters.persistence.operation_repo import OperationRepository

    pipeline = SyncPipeline(
        account_id=setup["account_id"],
        broker_account_id="acc-1",
        token_plaintext="t.fake",
        session_factory=db_factory,
    )
    for _ in range(3):
        pipeline._save_error_state(BrokerUnavailable("blip"))
    with db_factory() as session:
        conn = session.query(BrokerConnection).filter_by(id=setup["connection_id"]).one()
        assert conn.consecutive_failures == 3

    repo = OperationRepository()
    with db_factory() as session:
        repo.save_cursor(
            session,
            account_id=setup["account_id"],
            broker_account_id="acc-1",
            cursor="next",
            last_sync_status="success",
        )
        session.commit()

    with db_factory() as session:
        conn = session.query(BrokerConnection).filter_by(id=setup["connection_id"]).one()
        assert conn.consecutive_failures == 0
        assert conn.circuit_open_until is None

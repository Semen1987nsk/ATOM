"""
Integration-тесты `TinkoffSyncOrchestrator` (PR 14).

Тесты используют мок-pipeline (через patch'инг `SyncPipeline`), чтобы
проверять только логику orchestrator'а: выбор due-аккаунтов, semaphore,
bulkhead per-connection, обработку ошибок.

Полный pipeline-цикл (с реальным sandbox API) — отдельный suite
в `tests/sandbox/`.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from application.sync.orchestrator import TinkoffSyncOrchestrator, _ConnectionCtx
from application.sync.pipeline import SyncReport
from domain.exceptions import RateLimitExceeded, TokenInvalid
from models import Account, Base, BrokerConnection, User
from utils.datetime_utils import utc_now_naive


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_orchestrator.db"
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
def encryption() -> TokenEncryptionService:
    return TokenEncryptionService(
        active_keys={1: secrets.token_bytes(32)}, current_key_id=1
    )


@pytest.fixture
def token_repo(encryption) -> TokenRepository:
    return TokenRepository(encryption=encryption)


@pytest.fixture
def setup_two_connections(db_session_factory, token_repo) -> dict:
    """User + Account + два активных BrokerConnection."""
    with db_session_factory() as session:
        user = User(email="orch@test.local", name="t", is_active=1)
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        session.add(account)
        session.flush()

        conn_a = token_repo.store(
            session,
            account_id=account.id,
            broker_account_id="acc-A",
            plaintext_token="t.token_a",
        )
        conn_b = token_repo.store(
            session,
            account_id=account.id,
            broker_account_id="acc-B",
            plaintext_token="t.token_b",
        )
        session.commit()
        return {
            "account_id": account.id,
            "connection_a": conn_a.id,
            "connection_b": conn_b.id,
        }


def _success_report(account_id: int, broker_account_id: str) -> SyncReport:
    return SyncReport(
        account_id=account_id,
        broker_account_id=broker_account_id,
        started_at=utc_now_naive(),
        finished_at=utc_now_naive(),
        operations_total=10,
        operations_new_or_updated=10,
        instruments_resolved=2,
        pages_fetched=1,
        trades_built=3,
        positions_open=1,
        success=True,
        duration_sec=0.5,
    )


# ── tests ────────────────────────────────────────────────────────────


def test_run_due_picks_connections_without_last_sync(db_session_factory, token_repo, setup_two_connections) -> None:
    """Подключения без last_sync_at — сразу due."""
    captured = []

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            captured.append(self.kwargs["broker_account_id"])
            return _success_report(
                self.kwargs["account_id"], self.kwargs["broker_account_id"]
            )

    with patch("application.sync.orchestrator.SyncPipeline", FakePipeline):
        orchestrator = TinkoffSyncOrchestrator(
            token_repo=token_repo,
            session_factory=db_session_factory,
        )
        report = asyncio.run(orchestrator.run_due_accounts())

    assert report.accounts_considered == 2
    assert report.accounts_synced == 2
    assert sorted(captured) == ["acc-A", "acc-B"]


def test_run_due_skips_circuit_open(db_session_factory, token_repo, setup_two_connections) -> None:
    """Подключение с circuit_open_until > now — пропускается."""
    with db_session_factory() as session:
        conn = session.query(BrokerConnection).filter_by(
            id=setup_two_connections["connection_a"]
        ).one()
        conn.circuit_open_until = utc_now_naive() + timedelta(hours=1)
        session.commit()

    captured = []

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            captured.append(self.kwargs["broker_account_id"])
            return _success_report(
                self.kwargs["account_id"], self.kwargs["broker_account_id"]
            )

    with patch("application.sync.orchestrator.SyncPipeline", FakePipeline):
        orchestrator = TinkoffSyncOrchestrator(
            token_repo=token_repo,
            session_factory=db_session_factory,
        )
        report = asyncio.run(orchestrator.run_due_accounts())

    # acc-A пропущен (circuit), acc-B обработан.
    assert captured == ["acc-B"]
    assert report.accounts_considered == 1


def test_run_due_respects_sync_interval(db_session_factory, token_repo, setup_two_connections) -> None:
    """Если last_sync_at + interval > now — пропускаем."""
    with db_session_factory() as session:
        conn_a = session.query(BrokerConnection).filter_by(
            id=setup_two_connections["connection_a"]
        ).one()
        # Только что синкались, interval 60 мин — пропускаем.
        conn_a.last_sync_at = utc_now_naive() - timedelta(minutes=10)
        conn_a.sync_interval_minutes = 60
        # acc-B давно не синкался — должен быть due.
        conn_b = session.query(BrokerConnection).filter_by(
            id=setup_two_connections["connection_b"]
        ).one()
        conn_b.last_sync_at = utc_now_naive() - timedelta(hours=3)
        conn_b.sync_interval_minutes = 60
        session.commit()

    captured = []

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            captured.append(self.kwargs["broker_account_id"])
            return _success_report(
                self.kwargs["account_id"], self.kwargs["broker_account_id"]
            )

    with patch("application.sync.orchestrator.SyncPipeline", FakePipeline):
        orchestrator = TinkoffSyncOrchestrator(
            token_repo=token_repo,
            session_factory=db_session_factory,
        )
        asyncio.run(orchestrator.run_due_accounts())

    assert captured == ["acc-B"]


def test_token_invalid_deactivates_connection(db_session_factory, token_repo, setup_two_connections) -> None:
    """TokenInvalid → connection.is_active = False, token затирается."""

    class FailingPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            raise TokenInvalid("revoked")

    with patch("application.sync.orchestrator.SyncPipeline", FailingPipeline):
        orchestrator = TinkoffSyncOrchestrator(
            token_repo=token_repo,
            session_factory=db_session_factory,
        )
        report = asyncio.run(orchestrator.run_due_accounts())

    assert report.accounts_failed == 2

    with db_session_factory() as session:
        conns = session.query(BrokerConnection).all()
        for c in conns:
            assert c.is_active is False
            assert c.api_token == ""
            # SYNC-01: причина деактивации — человекочитаемая, UI показывает
            # её в ReconnectBanner через GET /broker/connections.
            assert c.last_sync_error == "deactivated: token_invalid"


def test_rate_limit_does_not_deactivate(db_session_factory, token_repo, setup_two_connections) -> None:
    """RateLimitExceeded — не деактивирует, retry на следующем тике."""

    class RateLimitedPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            raise RateLimitExceeded("slow down")

    with patch("application.sync.orchestrator.SyncPipeline", RateLimitedPipeline):
        orchestrator = TinkoffSyncOrchestrator(
            token_repo=token_repo,
            session_factory=db_session_factory,
        )
        report = asyncio.run(orchestrator.run_due_accounts())

    assert report.accounts_failed == 2

    with db_session_factory() as session:
        conns = session.query(BrokerConnection).all()
        for c in conns:
            # Соединение НЕ деактивировано (только увеличен failure-счётчик
            # через pipeline._save_error_state, но pipeline не вызывался —
            # ошибка из mock'а сразу пробросилась). is_active остаётся True.
            assert c.is_active is True


def test_concurrent_calls_dont_double_sync(db_session_factory, token_repo, setup_two_connections) -> None:
    """`_in_flight` set защищает от повторного запуска того же connection_id."""
    barrier = asyncio.Event()
    fire_count = {"value": 0}

    class SlowPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            fire_count["value"] += 1
            # Висим пока тест не разблокирует.
            await barrier.wait()
            return _success_report(
                self.kwargs["account_id"], self.kwargs["broker_account_id"]
            )

    async def scenario():
        with patch("application.sync.orchestrator.SyncPipeline", SlowPipeline):
            orchestrator = TinkoffSyncOrchestrator(
                token_repo=token_repo,
                session_factory=db_session_factory,
                max_concurrent=10,
            )
            # Два параллельных run_due_accounts вызова.
            task1 = asyncio.create_task(orchestrator.run_due_accounts())
            task2 = asyncio.create_task(orchestrator.run_due_accounts())
            await asyncio.sleep(0.05)
            barrier.set()  # отпускаем
            r1, r2 = await asyncio.gather(task1, task2)
            return r1, r2

    r1, r2 = asyncio.run(scenario())
    # Каждый pipeline запустился ровно по 1 разу на каждое подключение
    # (2 connections × 1 запуск = 2), потому что второй gather пропустил
    # их через `_in_flight`.
    assert fire_count["value"] == 2


def test_sync_one_account_manual_trigger(db_session_factory, token_repo, setup_two_connections) -> None:
    """`sync_one_account` для ручного trigger'а (UI / админка)."""

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, *, full_sync: bool = False):
            return _success_report(
                self.kwargs["account_id"], self.kwargs["broker_account_id"]
            )

    with patch("application.sync.orchestrator.SyncPipeline", FakePipeline):
        orchestrator = TinkoffSyncOrchestrator(
            token_repo=token_repo,
            session_factory=db_session_factory,
        )
        report = asyncio.run(
            orchestrator.sync_one_account(setup_two_connections["connection_a"])
        )
    assert report.success is True
    assert report.operations_total == 10


def test_sync_one_account_missing_id_raises(db_session_factory, token_repo) -> None:
    orchestrator = TinkoffSyncOrchestrator(
        token_repo=token_repo,
        session_factory=db_session_factory,
    )
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(orchestrator.sync_one_account(999_999))


# ── SYNC-05: IP cooldown gate wiring ─────────────────────────────────


def _ctx(connection_id: int) -> _ConnectionCtx:
    return _ConnectionCtx(
        connection_id=connection_id,
        account_id=connection_id,
        broker_account_id=f"acc-{connection_id}",
        api_token_ciphertext="cipher",
        sync_cursor=None,
        sync_interval_minutes=60,
    )


@pytest.mark.asyncio
async def test_run_skips_entirely_when_gate_open(monkeypatch) -> None:
    class _OpenGate:
        async def is_open(self):
            return True

        async def open(self):
            return 60

        async def clear(self):
            return None

    orch = TinkoffSyncOrchestrator(cooldown_gate=_OpenGate())
    # _select_due_connection_ids НЕ должен вызываться при открытом gate
    called = {"select": False}
    monkeypatch.setattr(
        orch,
        "_select_due_connection_ids",
        lambda: called.__setitem__("select", True) or [],
    )
    report = await orch.run_due_accounts()
    assert called["select"] is False
    assert report.accounts_considered == 0


@pytest.mark.asyncio
async def test_gate_opens_when_distinct_connections_rate_limited(monkeypatch) -> None:
    opened = {"n": 0}

    class _Gate:
        async def is_open(self):
            return False

        async def open(self):
            opened["n"] += 1
            return 60

        async def clear(self):
            return None

    orch = TinkoffSyncOrchestrator(cooldown_gate=_Gate())
    monkeypatch.setattr(orch, "_select_due_connection_ids", lambda: [1, 2])
    monkeypatch.setattr(orch, "_load_connection", lambda cid: _ctx(cid))

    async def _boom(ctx):
        raise RateLimitExceeded(message="ip cooldown", code="RESOURCE_EXHAUSTED")

    monkeypatch.setattr(orch, "_sync", _boom)

    report = await orch.run_due_accounts()
    assert opened["n"] == 1  # 2 различных коннекшна ≥ threshold(2) → gate открыт
    assert report.accounts_failed == 2


@pytest.mark.asyncio
async def test_gate_not_opened_below_threshold(monkeypatch) -> None:
    """Один rate-limited коннекшн (< threshold) НЕ открывает global gate —
    для одиночного throttle есть per-connection circuit, не IP-cooldown."""
    counts = {"open": 0, "clear": 0}

    class _Gate:
        async def is_open(self):
            return False

        async def open(self):
            counts["open"] += 1
            return 60

        async def clear(self):
            counts["clear"] += 1
            return None

    orch = TinkoffSyncOrchestrator(cooldown_gate=_Gate())
    monkeypatch.setattr(orch, "_select_due_connection_ids", lambda: [1])
    monkeypatch.setattr(orch, "_load_connection", lambda cid: _ctx(cid))

    async def _boom(ctx):
        raise RateLimitExceeded(message="single throttle", code="RESOURCE_EXHAUSTED")

    monkeypatch.setattr(orch, "_sync", _boom)

    report = await orch.run_due_accounts()
    assert counts["open"] == 0  # 1 < threshold(2) → gate НЕ открыт
    assert counts["clear"] == 1  # чистый IP-сигнал → сброс эскалации
    assert report.accounts_failed == 1

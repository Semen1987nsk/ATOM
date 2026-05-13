"""
Integration-тесты `TokenRepository` с реальной БД (in-memory SQLite через
существующий `database.SessionLocal` или ad-hoc engine).

Проверяем:

* store/get round-trip — plaintext не попадает в БД,
* rotate — повторный store обновляет ту же запись,
* deactivate — затирает api_token, is_active=False,
* audit log пишется в `token_audit_log` без значения токена,
* при ротации мастер-ключа старые записи всё ещё расшифровываются.

Для изоляции от прод-БД создаём отдельный SQLite-файл в tmp_path.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_audit import TokenAuditRecorder
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from models import Account, Base, BrokerConnection, TokenAuditLogORM, User


@pytest.fixture
def db_session_factory(tmp_path: Path):
    """Изолированная SQLite-БД на каждый тест в `tmp_path/test.db`."""
    db_path = tmp_path / "test_token_repo.db"
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
def setup_account(db_session_factory) -> int:
    """Создаём минимальный User + Account, чтобы FK BrokerConnection.account_id работал."""
    with db_session_factory() as session:
        user = User(
            email=f"u-{secrets.token_hex(4)}@test.local",
            name="Test",
            is_active=1,
        )
        session.add(user)
        session.flush()
        account = Account(
            user_id=user.id,
            name="Тестовый счёт",
            currency="RUB",
        )
        session.add(account)
        session.flush()
        account_id = account.id
        session.commit()
    return account_id


@pytest.fixture
def encryption() -> TokenEncryptionService:
    return TokenEncryptionService(
        active_keys={1: secrets.token_bytes(32)},
        current_key_id=1,
    )


@pytest.fixture
def repo(encryption, db_session_factory) -> TokenRepository:
    # Используем session_factory из изолированной БД для audit log.
    return TokenRepository(
        encryption=encryption,
        audit=TokenAuditRecorder(session_factory=db_session_factory),
    )


# ── store / get ────────────────────────────────────────────────────────


def test_store_and_get_roundtrip(repo, db_session_factory, setup_account) -> None:
    plain = "t." + "X" * 86  # реалистичная длина Tinkoff токена
    with db_session_factory() as session:
        conn = repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token=plain,
        )
        session.commit()
        connection_id = conn.id

    # Проверяем что в БД лежит шифротекст, не plaintext.
    with db_session_factory() as session:
        row = session.query(BrokerConnection).filter_by(id=connection_id).one()
        assert row.api_token != plain
        assert row.api_token != ""
        assert row.key_id == 1
        assert row.is_active is True
        assert plain not in row.api_token

    # Расшифровка через repo.
    with db_session_factory() as session:
        decrypted = repo.get_decrypted(
            session, account_id=setup_account, broker_account_id="2000000"
        )
    assert decrypted == plain


def test_get_returns_none_for_inactive(repo, db_session_factory, setup_account) -> None:
    with db_session_factory() as session:
        repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.original",
        )
        repo.deactivate(session, account_id=setup_account, broker_account_id="2000000")
        session.commit()

    with db_session_factory() as session:
        assert repo.get_decrypted(session, account_id=setup_account) is None


def test_get_returns_none_when_no_connection(repo, db_session_factory) -> None:
    with db_session_factory() as session:
        assert repo.get_decrypted(session, account_id=999) is None


# ── rotate ────────────────────────────────────────────────────────────


def test_rotate_updates_existing(repo, db_session_factory, setup_account) -> None:
    with db_session_factory() as session:
        first = repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.first",
        )
        first_id = first.id
        session.commit()

    with db_session_factory() as session:
        second = repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.second",
        )
        session.commit()
        # Та же запись, не новая.
        assert second.id == first_id

    with db_session_factory() as session:
        decrypted = repo.get_decrypted(session, account_id=setup_account)
    assert decrypted == "t.second"


def test_rotate_resets_failure_counters(repo, db_session_factory, setup_account) -> None:
    """После rotate consecutive_failures и circuit_open_until сбрасываются."""
    with db_session_factory() as session:
        first = repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.first",
        )
        first.consecutive_failures = 7
        first.last_sync_error = "some error"
        first_id = first.id
        session.commit()

    with db_session_factory() as session:
        repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.second",
        )
        session.commit()

    with db_session_factory() as session:
        row = session.query(BrokerConnection).filter_by(id=first_id).one()
        assert row.consecutive_failures == 0
        assert row.last_sync_error is None
        assert row.circuit_open_until is None


# ── deactivate ─────────────────────────────────────────────────────────


def test_deactivate_clears_token(repo, db_session_factory, setup_account) -> None:
    with db_session_factory() as session:
        conn = repo.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.something",
        )
        connection_id = conn.id
        session.commit()

    with db_session_factory() as session:
        ok = repo.deactivate(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            reason="test",
        )
        session.commit()
        assert ok is True

    with db_session_factory() as session:
        row = session.query(BrokerConnection).filter_by(id=connection_id).one()
        assert row.is_active is False
        assert row.api_token == ""
        assert "deactivated" in (row.last_sync_error or "")


def test_deactivate_returns_false_if_nothing_active(repo, db_session_factory) -> None:
    with db_session_factory() as session:
        assert repo.deactivate(session, account_id=999, reason="x") is False


# ── audit log ──────────────────────────────────────────────────────────


def test_log_usage_writes_row(repo, db_session_factory, setup_account) -> None:
    repo.log_usage(
        account_id=setup_account,
        method="get_accounts",
        endpoint="invest-public-api.tinkoff.ru:443",
        status_code=0,
        latency_ms=123,
        user_id=42,
    )
    with db_session_factory() as session:
        rows = session.query(TokenAuditLogORM).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.account_id == setup_account
        assert row.method == "get_accounts"
        assert row.status_code == 0
        assert row.latency_ms == 123
        # SHA-256 hex длиной 64.
        assert row.user_id_hash and len(row.user_id_hash) == 64
        # Никаких следов токена в audit.
        assert "t." not in (row.error_detail or "")


def test_log_usage_trims_long_error_detail(repo, db_session_factory, setup_account) -> None:
    long_detail = "X" * 2000
    repo.log_usage(
        account_id=setup_account,
        method="get_portfolio",
        endpoint="invest-public-api.tinkoff.ru:443",
        status_code=8,
        latency_ms=10,
        error_detail=long_detail,
    )
    with db_session_factory() as session:
        row = session.query(TokenAuditLogORM).one()
        assert row.error_detail is not None
        assert len(row.error_detail) <= 512


# ── key rotation across repo ───────────────────────────────────────────


def test_can_decrypt_after_key_rotation(db_session_factory, setup_account) -> None:
    """Записали при key_id=1, потом ключ ротирован, старый в active_keys."""
    key1 = secrets.token_bytes(32)
    key2 = secrets.token_bytes(32)

    enc_v1 = TokenEncryptionService(active_keys={1: key1}, current_key_id=1)
    repo_v1 = TokenRepository(encryption=enc_v1, audit=TokenAuditRecorder(session_factory=db_session_factory))

    with db_session_factory() as session:
        repo_v1.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.rotated",
        )
        session.commit()

    # Эмулируем рестарт после ротации: оба ключа активны, current=2.
    enc_v2 = TokenEncryptionService(
        active_keys={1: key1, 2: key2}, current_key_id=2
    )
    repo_v2 = TokenRepository(encryption=enc_v2, audit=TokenAuditRecorder(session_factory=db_session_factory))

    with db_session_factory() as session:
        decrypted = repo_v2.get_decrypted(session, account_id=setup_account)
    assert decrypted == "t.rotated"


def test_decrypt_fails_if_master_key_removed(db_session_factory, setup_account) -> None:
    """Если старый MASTER_KEY_<N>_B64 убран из env — получим TokenEncryptionError."""
    key1 = secrets.token_bytes(32)
    key2 = secrets.token_bytes(32)

    repo_v1 = TokenRepository(
        encryption=TokenEncryptionService(active_keys={1: key1}, current_key_id=1),
        audit=TokenAuditRecorder(session_factory=db_session_factory),
    )
    with db_session_factory() as session:
        repo_v1.store(
            session,
            account_id=setup_account,
            broker_account_id="2000000",
            plaintext_token="t.will_be_lost",
        )
        session.commit()

    repo_v2 = TokenRepository(
        encryption=TokenEncryptionService(active_keys={2: key2}, current_key_id=2),
        audit=TokenAuditRecorder(session_factory=db_session_factory),
    )
    with db_session_factory() as session:
        with pytest.raises(TokenEncryptionError):
            repo_v2.get_decrypted(session, account_id=setup_account)

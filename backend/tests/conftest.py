# Test configuration for ATOM backend

import pytest
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
import models
from rate_limiter import reset_rate_limiter_storage

# Test database (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(autouse=True)
def reset_rate_limiter_between_tests():
    """Изолирует состояние in-memory rate limiter между тестами."""
    reset_rate_limiter_storage()
    try:
        yield
    finally:
        reset_rate_limiter_storage()


@pytest.fixture(autouse=True)
def restore_config_settings_singleton():
    """Восстанавливает идентичность `config.settings` после тестов, которые
    делают `importlib.reload(config)` (test_config_*, test_worker_role и т.п.).

    Reload пересоздаёт `config.settings`, но `main` и прочие модули держат
    ссылку на ИСХОДНЫЙ объект (`from config import settings` при импорте).
    Если не восстановить — последующие тесты, читающие `config.settings`
    (напр. TestDocsGating monkeypatch'ит DEBUG), патчат новый объект, а
    `main._docs_guard` читает старый → cross-file flake.
    """
    import config

    orig = config.settings
    try:
        yield
    finally:
        if config.settings is not orig:
            config.settings = orig


@pytest.fixture(autouse=True)
def reset_stream_manager_locks():
    """Чистит module-global `stream_manager` между тестами.

    `stream_manager._account_locks` хранит `asyncio.Lock`-объекты, привязанные
    к event-loop'у того теста, где были созданы. Тесты с собственным
    `asyncio.run()` (новый loop) переиспользуют stale-локи → RuntimeError
    'Lock is bound to a different event loop'. Очистка перед/после теста
    гарантирует, что локи создаются заново в текущем loop'е.
    """
    from application.sync.stream_manager import stream_manager

    stream_manager._account_locks.clear()
    stream_manager._tasks.clear()
    try:
        yield
    finally:
        stream_manager._account_locks.clear()
        stream_manager._tasks.clear()

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_trade_data():
    """Sample trade data for tests."""
    return {
        "account_id": 1,
        "symbol": "TEST",
        "direction": models.TradeDirection.LONG,
        "entry_price": 100.0,
        "quantity": 10,
        "entry_at": "2025-01-01T10:00:00",
        "commission": 1.0
    }

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

"""
API Integration Tests for ATOM Backend

Tests for auth, trades, and stats endpoints using FastAPI TestClient.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import Base, User, Account, Trade, TradeDirection
from database import get_db
import auth_service

# Test database (in-memory SQLite with StaticPool for thread safety)
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_app():
    """Create fresh database and app for each test"""
    engine = create_engine(
        TEST_DATABASE_URL, 
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    db_session = TestingSessionLocal()
    
    yield {"client": TestClient(app), "db": db_session}
    
    db_session.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_app):
    """Create a test user with account"""
    db = test_app["db"]
    hashed_password = auth_service.get_password_hash("testpass123")
    user = User(
        email="test@example.com",
        name="Test User",
        hashed_password=hashed_password,
        is_active=1,
        is_admin=0
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    account = Account(
        user_id=user.id,
        name="Test Account",
        balance=0,
        currency="RUB"
    )
    db.add(account)
    db.commit()
    
    return user


@pytest.fixture
def auth_headers(test_user):
    """Get authorization headers for test user"""
    token = auth_service.create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email}
    )
    return {"Authorization": f"Bearer {token}"}


# ==================== ROOT TESTS ====================

class TestRoot:
    """Tests for root endpoints"""
    
    def test_root(self, test_app):
        """Should return welcome message"""
        client = test_app["client"]
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "ATOM" in data["message"]
    
    def test_health_check(self, test_app):
        """Should return healthy status"""
        client = test_app["client"]
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_db_check(self, test_app):
        """Should confirm database connection"""
        client = test_app["client"]
        response = client.get("/db-check")
        assert response.status_code == 200
        assert "connected" in response.json()["status"].lower()


# ==================== AUTH TESTS ====================

class TestAuth:
    """Tests for authentication endpoints"""
    
    def test_register_success(self, test_app):
        """Should register new user successfully"""
        client = test_app["client"]
        response = client.post("/auth/register", json={
            "email": "newuser@example.com",
            "password": "password123",
            "name": "New User"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_register_duplicate_email(self, test_app, test_user):
        """Should reject duplicate email"""
        client = test_app["client"]
        response = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
            "name": "Duplicate"
        })
        assert response.status_code == 400
        assert "зарегистрирован" in response.json()["detail"].lower()
    
    def test_register_weak_password(self, test_app):
        """Should reject weak password"""
        client = test_app["client"]
        response = client.post("/auth/register", json={
            "email": "weak@example.com",
            "password": "123",
            "name": "Weak"
        })
        assert response.status_code == 422
    
    def test_login_success(self, test_app, test_user):
        """Should login successfully with correct credentials"""
        client = test_app["client"]
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "testpass123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
    
    def test_login_wrong_password(self, test_app, test_user):
        """Should reject wrong password"""
        client = test_app["client"]
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
    
    def test_login_nonexistent_user(self, test_app):
        """Should reject nonexistent user"""
        client = test_app["client"]
        response = client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "password123"
        })
        assert response.status_code == 401
    
    def test_get_current_user(self, test_app, test_user, auth_headers):
        """Should return current user info"""
        client = test_app["client"]
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
    
    def test_get_current_user_no_auth(self, test_app):
        """Should reject request without auth"""
        client = test_app["client"]
        response = client.get("/auth/me")
        assert response.status_code == 401
    
    def test_update_profile(self, test_app, test_user, auth_headers):
        """Should update user profile"""
        client = test_app["client"]
        response = client.put("/auth/me", 
            headers=auth_headers,
            json={"name": "Updated Name"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"


# ==================== TRADES TESTS ====================

class TestTrades:
    """Tests for trades endpoints"""
    
    def test_create_trade(self, test_app, test_user, auth_headers):
        """Should create new trade"""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        
        response = client.post("/trades/", 
            headers=auth_headers,
            json={
                "symbol": "SBER",
                "direction": "long",
                "entry_price": 250.0,
                "quantity": 10,
                "entry_at": "2025-01-01T10:00:00",
                "account_id": account.id
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "SBER"
        assert data["direction"] == "long"
    
    def test_get_trades(self, test_app, test_user, auth_headers):
        """Should return trades list"""
        client = test_app["client"]
        response = client.get("/trades/", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_delete_trade(self, test_app, test_user, auth_headers):
        """Should delete trade"""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        
        from datetime import datetime
        trade = Trade(
            account_id=account.id,
            symbol="TEST",
            direction=TradeDirection.LONG,
            entry_price=100.0,
            quantity=10,
            entry_at=datetime(2025, 1, 1, 10, 0)
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        
        response = client.delete(f"/trades/{trade.id}", headers=auth_headers)
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()
    
    def test_delete_trade_not_found(self, test_app, test_user, auth_headers):
        """Should return 404 for non-existent trade"""
        client = test_app["client"]
        response = client.delete("/trades/99999", headers=auth_headers)
        assert response.status_code == 404


# ==================== STATS TESTS ====================

class TestStats:
    """Tests for statistics endpoints"""
    
    def test_get_stats_empty(self, test_app, test_user, auth_headers):
        """Should return zero stats when no trades"""
        client = test_app["client"]
        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_trades"] == 0
        assert data["total_pnl"] == 0
    
    def test_get_stats_with_trades(self, test_app, test_user, auth_headers):
        """Should calculate stats from trades"""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        
        from datetime import datetime
        trades = [
            Trade(account_id=account.id, symbol="SBER", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 1, 10, 0),
                  exit_price=110, exit_at=datetime(2025, 1, 1, 11, 0), pnl=100, net_pnl=95),
            Trade(account_id=account.id, symbol="GAZP", direction=TradeDirection.LONG,
                  entry_price=200, quantity=5, entry_at=datetime(2025, 1, 2, 10, 0),
                  exit_price=190, exit_at=datetime(2025, 1, 2, 11, 0), pnl=-50, net_pnl=-55),
        ]
        for t in trades:
            db.add(t)
        db.commit()
        
        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_trades"] == 2
        assert data["profitable_trades"] == 1
        assert data["total_pnl"] == 40  # 95 - 55
    
    def test_get_tags(self, test_app, test_user, auth_headers):
        """Should return tag statistics"""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        
        from datetime import datetime
        trade = Trade(
            account_id=account.id, symbol="TEST", direction=TradeDirection.LONG,
            entry_price=100, quantity=10, entry_at=datetime(2025, 1, 1, 10, 0),
            pnl=100, tags=["trend", "breakout"]
        )
        db.add(trade)
        db.commit()
        
        response = client.get("/tags/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(t["tag"] == "trend" for t in data)


# ==================== BLOG TESTS ====================

class TestBlog:
    """Tests for blog endpoints"""
    
    def test_get_articles(self, test_app):
        """Should return articles list"""
        client = test_app["client"]
        response = client.get("/blog/articles")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_categories(self, test_app):
        """Should return blog categories"""
        client = test_app["client"]
        response = client.get("/blog/categories")
        assert response.status_code == 200
        categories = response.json()
        assert len(categories) > 0
        assert any(c["id"] == "news" for c in categories)


# ==================== ADMIN TESTS ====================

class TestAdmin:
    """Tests for admin endpoints"""
    
    def test_admin_requires_auth(self, test_app):
        """Should require authentication"""
        client = test_app["client"]
        response = client.get("/admin/stats")
        assert response.status_code == 401
    
    def test_admin_requires_admin_role(self, test_app, test_user, auth_headers):
        """Should require admin role"""
        client = test_app["client"]
        response = client.get("/admin/stats", headers=auth_headers)
        assert response.status_code == 403  # test_user is not admin
    
    def test_admin_access_for_admin(self, test_app):
        """Should allow access for admin users"""
        client = test_app["client"]
        db = test_app["db"]
        
        admin = User(
            email="admin@example.com",
            name="Admin",
            hashed_password=auth_service.get_password_hash("adminpass"),
            is_active=1,
            is_admin=1
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        token = auth_service.create_access_token(
            data={"sub": str(admin.id), "email": admin.email}
        )
        admin_headers = {"Authorization": f"Bearer {token}"}
        
        response = client.get("/admin/stats", headers=admin_headers)
        assert response.status_code == 200


# ==================== MARKET TESTS ====================

class TestMarket:
    """Tests for market data endpoints"""
    
    def test_get_prices(self, test_app):
        """Should return prices (may be empty if MOEX unavailable)"""
        client = test_app["client"]
        response = client.get("/market/prices?tickers=SBER,GAZP")
        assert response.status_code == 200
        assert "prices" in response.json()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

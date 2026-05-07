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
from models import Base, User, Account, Trade, TradeDirection, CapitalOperation, BalanceSnapshot
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
        assert response.headers.get("X-Request-ID")

    def test_root_echoes_request_id_header(self, test_app):
        """Should echo client-provided request id for correlation"""
        client = test_app["client"]
        response = client.get("/", headers={"X-Request-ID": "test-request-123"})
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == "test-request-123"
    
    def test_health_check(self, test_app):
        """Liveness probe — лёгкая проверка процесса. Возвращает 'alive'."""
        client = test_app["client"]
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_check(self, test_app):
        """Readiness probe с проверкой DB (и Redis, если включён)."""
        client = test_app["client"]
        response = client.get("/ready")
        # В тестовом окружении DB подключена → ready=200, status='ready'
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"]["ok"] is True
    
    def test_db_check(self, test_app):
        """Should confirm database connection"""
        client = test_app["client"]
        response = client.get("/db-check")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data["status"].lower()
        assert data["connected"] is True


# ==================== AUTH TESTS ====================

class TestAuth:
    """Tests for authentication endpoints"""

    @staticmethod
    def _csrf_headers(client) -> dict:
        csrf_token = client.cookies.get(auth_service.CSRF_COOKIE_NAME)
        assert csrf_token
        return {auth_service.CSRF_HEADER_NAME: csrf_token}
    
    def test_register_success(self, test_app):
        """Should register new user successfully (password ≥ 12 chars per OWASP 2024)."""
        client = test_app["client"]
        response = client.post("/auth/register", json={
            "email": "newuser@example.com",
            "password": "Strong-Password-123",
            "name": "New User",
            "pd_consent": True,  # 152-ФЗ ст. 9: обязательное согласие
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
            "password": "Strong-Password-123",
            "name": "Duplicate",
            "pd_consent": True,
        })
        assert response.status_code == 400
        assert "зарегистрирован" in response.json()["detail"].lower()

    def test_register_weak_password(self, test_app):
        """Should reject weak password"""
        client = test_app["client"]
        response = client.post("/auth/register", json={
            "email": "weak@example.com",
            "password": "123",
            "name": "Weak",
            "pd_consent": True,
        })
        assert response.status_code == 422
        assert response.json()["request_id"]
        assert response.headers.get("X-Request-ID") == response.json()["request_id"]

    def test_register_without_pd_consent_rejected(self, test_app):
        """152-ФЗ: registration must fail without explicit pd_consent."""
        client = test_app["client"]
        # Полное отсутствие поля → 422 (Pydantic)
        response = client.post("/auth/register", json={
            "email": "noconsent@example.com",
            "password": "Strong-Password-123",
            "name": "NoConsent",
        })
        assert response.status_code == 422

    def test_register_with_false_pd_consent_rejected(self, test_app):
        """152-ФЗ: explicit pd_consent=false must be rejected at endpoint level."""
        client = test_app["client"]
        response = client.post("/auth/register", json={
            "email": "falseconsent@example.com",
            "password": "Strong-Password-123",
            "name": "False",
            "pd_consent": False,
        })
        assert response.status_code == 400
        assert "согласие" in response.json()["detail"].lower()
    
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
        assert response.cookies.get(auth_service.ACCESS_TOKEN_COOKIE_NAME)
        assert response.cookies.get(auth_service.REFRESH_TOKEN_COOKIE_NAME)
        assert response.cookies.get(auth_service.CSRF_COOKIE_NAME)
    
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

    def test_get_current_user_from_cookie(self, test_app, test_user):
        """Should authenticate using httpOnly access cookie without Authorization header"""
        client = test_app["client"]
        access_token, _ = auth_service.create_token_pair(test_user.id, test_user.email)
        client.cookies.set(auth_service.ACCESS_TOKEN_COOKIE_NAME, access_token)

        response = client.get("/auth/me")
        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"
    
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

    def test_update_profile_cookie_auth_requires_csrf(self, test_app, test_user):
        """Should reject cookie-auth state change without CSRF header"""
        client = test_app["client"]
        login_response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "testpass123"
        })
        assert login_response.status_code == 200

        response = client.put("/auth/me", json={"name": "Updated Name"})
        assert response.status_code == 403
        assert response.json()["error"] == "csrf_validation_failed"

    def test_update_profile_cookie_auth_with_csrf(self, test_app, test_user):
        """Should allow cookie-auth state change with valid CSRF header"""
        client = test_app["client"]
        login_response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "testpass123"
        })
        assert login_response.status_code == 200

        response = client.put(
            "/auth/me",
            json={"name": "Updated Name"},
            headers=self._csrf_headers(client),
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_change_password_success(self, test_app, test_user, auth_headers):
        """Should change password when current password is correct"""
        client = test_app["client"]
        response = client.post(
            "/auth/change-password",
            headers=auth_headers,
            json={
                "old_password": "testpass123",
                "new_password": "newpass456"
            }
        )
        assert response.status_code == 200
        assert "успешно" in response.json()["message"].lower()

    def test_change_password_rejects_same_password(self, test_app, test_user, auth_headers):
        """Should reject using the same password again"""
        client = test_app["client"]
        response = client.post(
            "/auth/change-password",
            headers=auth_headers,
            json={
                "old_password": "testpass123",
                "new_password": "testpass123"
            }
        )
        assert response.status_code == 400
        assert "отличаться" in response.json()["detail"].lower()

    def test_refresh_tokens_from_cookie(self, test_app, test_user):
        """Should refresh token pair using refresh cookie without request body"""
        client = test_app["client"]
        _, refresh_token = auth_service.create_token_pair(test_user.id, test_user.email)
        client.cookies.set(auth_service.REFRESH_TOKEN_COOKIE_NAME, refresh_token)
        csrf_token = auth_service.create_csrf_token()
        client.cookies.set(auth_service.CSRF_COOKIE_NAME, csrf_token)

        refresh_response = client.post(
            "/auth/refresh",
            headers={auth_service.CSRF_HEADER_NAME: csrf_token},
        )
        assert refresh_response.status_code == 200
        assert refresh_response.cookies.get(auth_service.ACCESS_TOKEN_COOKIE_NAME)
        assert refresh_response.cookies.get(auth_service.REFRESH_TOKEN_COOKIE_NAME)
        assert refresh_response.cookies.get(auth_service.CSRF_COOKIE_NAME)

    def test_logout_clears_cookie_session(self, test_app, test_user):
        """Should clear auth cookies and invalidate cookie-based session"""
        client = test_app["client"]
        access_token, refresh_token = auth_service.create_token_pair(test_user.id, test_user.email)
        csrf_token = auth_service.create_csrf_token()
        client.cookies.set(auth_service.ACCESS_TOKEN_COOKIE_NAME, access_token, domain="testserver.local", path="/")
        client.cookies.set(auth_service.REFRESH_TOKEN_COOKIE_NAME, refresh_token, domain="testserver.local", path="/")
        client.cookies.set(auth_service.CSRF_COOKIE_NAME, csrf_token, domain="testserver.local", path="/")

        logout_response = client.post(
            "/auth/logout",
            headers={auth_service.CSRF_HEADER_NAME: csrf_token},
        )
        assert logout_response.status_code == 204

        me_response = client.get("/auth/me")
        assert me_response.status_code == 401


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

    def test_get_stats_drawdown_uses_starting_balance(self, test_app, test_user, auth_headers):
        """Drawdown percent should be computed from account starting balance, not from zero-based PnL only."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 1000

        from datetime import datetime
        trades = [
            Trade(account_id=account.id, symbol="SBER", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 1, 10, 0),
                  exit_price=110, exit_at=datetime(2025, 1, 1, 11, 0), pnl=100, net_pnl=95),
            Trade(account_id=account.id, symbol="GAZP", direction=TradeDirection.LONG,
                  entry_price=200, quantity=5, entry_at=datetime(2025, 1, 2, 10, 0),
                  exit_price=190, exit_at=datetime(2025, 1, 2, 11, 0), pnl=-50, net_pnl=-55),
        ]
        for trade in trades:
            db.add(trade)
        db.commit()

        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["max_drawdown_abs"] == 55
        assert data["max_drawdown_pct"] == 5.02

    def test_get_stats_exposes_current_drawdown_and_win_loss_metrics(self, test_app, test_user, auth_headers):
        """Stats endpoint should expose current drawdown and win/loss metrics from net PnL values."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 1000

        from datetime import datetime
        trades = [
            Trade(account_id=account.id, symbol="AAA", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 1, 10, 0),
                  exit_price=112, exit_at=datetime(2025, 1, 1, 11, 0), pnl=120, net_pnl=120),
            Trade(account_id=account.id, symbol="BBB", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 2, 10, 0),
                  exit_price=97, exit_at=datetime(2025, 1, 2, 11, 0), pnl=-30, net_pnl=-30),
            Trade(account_id=account.id, symbol="CCC", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 3, 10, 0),
                  exit_price=98, exit_at=datetime(2025, 1, 3, 11, 0), pnl=-20, net_pnl=-20),
            Trade(account_id=account.id, symbol="DDD", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 4, 10, 0),
                  exit_price=105, exit_at=datetime(2025, 1, 4, 11, 0), pnl=50, net_pnl=50),
            Trade(account_id=account.id, symbol="EEE", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 5, 10, 0),
                  exit_price=99, exit_at=datetime(2025, 1, 5, 11, 0), pnl=-10, net_pnl=-10),
            Trade(account_id=account.id, symbol="FFF", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 6, 10, 0),
                  exit_price=108, exit_at=datetime(2025, 1, 6, 11, 0), pnl=80, net_pnl=80),
            Trade(account_id=account.id, symbol="GGG", direction=TradeDirection.LONG,
                  entry_price=100, quantity=10, entry_at=datetime(2025, 1, 7, 10, 0),
                  exit_price=96, exit_at=datetime(2025, 1, 7, 11, 0), pnl=-40, net_pnl=-40),
        ]
        for trade in trades:
            db.add(trade)
        db.commit()

        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["current_drawdown_pct"] == 3.36
        assert data["avg_win"] == 83.33
        assert data["avg_loss"] == 25.0
        assert data["largest_win"] == 120
        assert data["largest_loss"] == -40

    def test_get_stats_exposes_streaks_and_tail_ratio(self, test_app, test_user, auth_headers):
        """Stats endpoint should expose streak metrics and exact tail-ratio values from ordered closed trades."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()

        from datetime import datetime, timedelta
        pnls = [100, 80, 60, 40, 20, 10, -5, -10, -20, -50]
        for index, pnl in enumerate(pnls, start=1):
            entry_at = datetime(2025, 1, index, 10, 0)
            exit_at = entry_at + timedelta(hours=1)
            trade = Trade(
                account_id=account.id,
                symbol=f"T{index}",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=entry_at,
                exit_price=100 + pnl / 10,
                exit_at=exit_at,
                pnl=pnl,
                net_pnl=pnl,
            )
            db.add(trade)
        db.commit()

        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["max_win_streak"] == 6
        assert data["max_loss_streak"] == 4
        assert data["current_streak"] == 4
        assert data["current_streak_type"] == "LOSS"
        assert data["tail_ratio"] == 2.0

    def test_get_stats_exposes_calmar_risk_r_distribution_duration_and_monte_carlo(self, test_app, test_user, auth_headers):
        """Stats endpoint should expose the next analytics batch with correct deterministic values and valid Monte Carlo contract."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 1000

        from datetime import datetime, timedelta
        trades = [
            ("A", 100, 50, datetime(2025, 1, 1, 10, 0), 2.0),
            ("B", -50, 50, datetime(2025, 2, 10, 10, 0), 3.5),
            ("C", -30, 50, datetime(2025, 3, 20, 10, 0), 1.0),
            ("D", 80, 40, datetime(2025, 4, 25, 10, 0), 1.0),
            ("E", 100, 50, datetime(2025, 5, 30, 10, 0), 1.5),
            ("F", 50, 25, datetime(2025, 7, 5, 10, 0), 2.0),
            ("G", -20, 20, datetime(2025, 8, 12, 10, 0), 1.0),
            ("H", 120, 60, datetime(2025, 9, 18, 10, 0), 4.0),
            ("I", -40, 40, datetime(2025, 10, 24, 10, 0), 1.5),
            ("J", 90, 45, datetime(2025, 12, 1, 10, 0), 2.5),
        ]
        for symbol, net_pnl, risk_amount, entry_at, duration_hours in trades:
            exit_at = entry_at + timedelta(hours=duration_hours)
            trade = Trade(
                account_id=account.id,
                symbol=symbol,
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=entry_at,
                exit_price=100 + net_pnl / 10,
                exit_at=exit_at,
                pnl=net_pnl,
                net_pnl=net_pnl,
                risk_amount=risk_amount,
            )
            db.add(trade)
        db.commit()

        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["calmar_ratio"]["calmar_ratio"] == 6.11
        assert data["calmar_ratio"]["cagr_pct"] == 44.44
        assert data["calmar_ratio"]["max_drawdown_pct"] == 7.27
        assert data["calmar_ratio"]["rating"] == "Исключительно"

        assert data["risk_of_ruin"]["risk_of_ruin_pct"] == 0.0
        assert data["risk_of_ruin"]["message"] == "OK"

        assert data["r_distribution"]["pct_positive_r"] == 60.0
        assert data["r_distribution"]["pct_above_1r"] == 60.0
        assert data["r_distribution"]["pct_above_2r"] == 60.0

        assert data["trade_duration"]["avg_duration_hours"] == 2.0
        assert data["trade_duration"]["avg_win_duration_hours"] == 2.2
        assert data["trade_duration"]["avg_loss_duration_hours"] == 1.8
        assert data["trade_duration"]["median_duration_hours"] == 1.8
        assert data["trade_duration"]["total_closed_trades"] == 10

        assert data["monte_carlo"]["simulations_run"] == 1000
        assert 0 <= data["monte_carlo"]["ruin_probability"] <= 100
        assert data["monte_carlo"]["worst_case_5pct"] <= data["monte_carlo"]["median_return"] <= data["monte_carlo"]["best_case_95pct"]

    def test_get_stats_exposes_time_patterns_mae_mfe_equity_tags_and_balances(self, test_app, test_user, auth_headers):
        """Stats endpoint should expose exact aggregate structures for time patterns, MAE/MFE, equity, tags and balances."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 1000

        from datetime import datetime, timedelta
        trades = [
            Trade(
                account_id=account.id,
                symbol="AAA",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=datetime(2025, 1, 6, 10, 0),
                exit_price=110,
                exit_at=datetime(2025, 1, 6, 12, 0),
                pnl=100,
                net_pnl=95,
                mae_price=98,
                mfe_price=112,
                tags=["trend", "breakout"],
            ),
            Trade(
                account_id=account.id,
                symbol="BBB",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=datetime(2025, 1, 6, 11, 0),
                exit_price=101,
                exit_at=datetime(2025, 1, 6, 13, 30),
                pnl=10,
                net_pnl=-5,
                mae_price=97,
                mfe_price=105,
                tags=["breakout"],
            ),
            Trade(
                account_id=account.id,
                symbol="CCC",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=datetime(2025, 2, 4, 10, 0),
                exit_price=107,
                exit_at=datetime(2025, 2, 4, 11, 0),
                pnl=70,
                net_pnl=70,
                mae_price=99,
                mfe_price=108,
                tags=["trend"],
            ),
        ]
        for trade in trades:
            db.add(trade)
        db.commit()

        response = client.get("/stats/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["initial_balance"] == 1000.0
        assert data["current_balance"] == 1160.0
        assert data["equity_curve"] == [
            {"date": "2025-01-06 12:00", "balance": 1095.0},
            {"date": "2025-01-06 13:30", "balance": 1090.0},
            {"date": "2025-02-04 11:00", "balance": 1160.0},
        ]
        assert data["tag_stats"] == [
            {"tag": "trend", "pnl": 165.0, "win_rate": 100.0, "count": 2},
            {"tag": "breakout", "pnl": 90.0, "win_rate": 50.0, "count": 2},
        ]

        assert data["time_patterns"]["day_stats"] == [
            {"day": "Пн", "total_pnl": 90.0, "trades": 2, "win_rate": 50.0},
            {"day": "Вт", "total_pnl": 70.0, "trades": 1, "win_rate": 100.0},
        ]
        assert data["time_patterns"]["hour_stats"] == [
            {"hour": "10:00", "total_pnl": 165.0, "trades": 2, "win_rate": 100.0},
            {"hour": "11:00", "total_pnl": -5.0, "trades": 1, "win_rate": 0.0},
        ]
        assert data["time_patterns"]["month_stats"] == [
            {"month": "Янв", "total_pnl": 90.0, "trades": 2, "win_rate": 50.0},
            {"month": "Фев", "total_pnl": 70.0, "trades": 1, "win_rate": 100.0},
        ]
        assert data["time_patterns"]["best_day"]["day"] == "Пн"
        assert data["time_patterns"]["worst_day"]["day"] == "Вт"

        assert data["mae_mfe_analysis"]["avg_mae_pct"] == 2.0
        assert data["mae_mfe_analysis"]["avg_mfe_pct"] == 8.33
        assert data["mae_mfe_analysis"]["avg_efficiency"] == 63.6
        assert data["mae_mfe_analysis"]["avg_edge_ratio"] == 5.22
        assert data["mae_mfe_analysis"]["trades_analyzed"] == 3
        assert data["mae_mfe_analysis"]["winners_vs_losers"]["winners"]["count"] == 2
        assert data["mae_mfe_analysis"]["winners_vs_losers"]["losers"]["count"] == 1
        assert data["mae_mfe_analysis"]["optimal_stop_pct"] == 2.5
        assert data["mae_mfe_analysis"]["trades_above_optimal_stop"] == 1
        assert data["mae_mfe_analysis"]["entry_quality_score"] == 60
        assert data["mae_mfe_analysis"]["exit_quality_score"] == 64

    def test_get_stats_keeps_account_initial_balance_and_exposes_period_start_balance(self, test_app, test_user, auth_headers):
        """Filtered stats should preserve account initial balance and expose a separate period baseline."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 1000

        from datetime import datetime
        trades = [
            Trade(
                account_id=account.id,
                symbol="PREV1",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=datetime(2025, 1, 1, 10, 0),
                exit_price=110,
                exit_at=datetime(2025, 1, 1, 11, 0),
                pnl=100,
                net_pnl=100,
            ),
            Trade(
                account_id=account.id,
                symbol="PREV2",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=datetime(2025, 1, 2, 10, 0),
                exit_price=100,
                exit_at=datetime(2025, 1, 2, 11, 0),
                pnl=0,
                net_pnl=0,
            ),
            Trade(
                account_id=account.id,
                symbol="FILTERED",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=10,
                entry_at=datetime(2025, 1, 3, 10, 0),
                exit_price=98,
                exit_at=datetime(2025, 1, 3, 11, 0),
                pnl=-20,
                net_pnl=-20,
            ),
        ]
        for trade in trades:
            db.add(trade)
        db.commit()

        filtered_trade = db.query(Trade).filter(
            Trade.account_id == account.id,
            Trade.symbol == "FILTERED",
        ).first()

        response = client.get(f"/stats/?start_trade_id={filtered_trade.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["initial_balance"] == 1000.0
        assert data["period_start_balance"] == 1100.0
        assert data["current_balance"] == 1080.0
        assert data["period_end_balance"] == 1080.0
        assert data["total_pnl"] == -20.0
        assert data["total_roi"] == -1.82

    def test_get_stats_period_start_balance_uses_net_deposit_at_filter_date(self, test_app, test_user, auth_headers):
        """Period start balance must exclude deposits/withdrawals that happen after the filter start."""
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 1300

        from datetime import datetime
        db.add_all([
            CapitalOperation(
                account_id=account.id,
                broker_id="dep-before",
                operation_type="deposit",
                amount=1000,
                currency="RUB",
                date=datetime(2025, 1, 1, 9, 0),
                description="OPERATION_TYPE_INPUT",
            ),
            CapitalOperation(
                account_id=account.id,
                broker_id="dep-after",
                operation_type="deposit",
                amount=500,
                currency="RUB",
                date=datetime(2025, 1, 4, 9, 0),
                description="OPERATION_TYPE_INPUT",
            ),
        ])

        trades = [
            Trade(
                account_id=account.id,
                symbol="PREV",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=1,
                entry_at=datetime(2025, 1, 1, 10, 0),
                exit_price=200,
                exit_at=datetime(2025, 1, 1, 11, 0),
                pnl=100,
                net_pnl=100,
            ),
            Trade(
                account_id=account.id,
                symbol="START",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=1,
                entry_at=datetime(2025, 1, 3, 10, 0),
                exit_price=80,
                exit_at=datetime(2025, 1, 3, 11, 0),
                pnl=-20,
                net_pnl=-20,
            ),
        ]
        for trade in trades:
            db.add(trade)
        db.commit()

        start_trade = db.query(Trade).filter(Trade.account_id == account.id, Trade.symbol == "START").first()
        response = client.get(f"/stats/?start_trade_id={start_trade.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["initial_balance"] == 1300.0
        assert data["period_start_balance"] == 1100.0
        assert data["period_end_balance"] == 1580.0
        assert data["current_balance"] == 1580.0
        assert data["total_roi"] == -1.82


class TestDeposits:
    """Tests for deposit endpoints"""

    def test_deposits_balance_prefers_capital_operations_over_synthetic_initial(self, test_app, test_user, auth_headers):
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        account.initial_balance = 800

        from datetime import datetime
        db.add_all([
            CapitalOperation(
                account_id=account.id,
                broker_id="dep-1",
                operation_type="deposit",
                amount=1000,
                currency="RUB",
                date=datetime(2025, 1, 1, 10, 0),
                description="OPERATION_TYPE_INPUT",
            ),
            CapitalOperation(
                account_id=account.id,
                broker_id="wd-1",
                operation_type="withdrawal",
                amount=200,
                currency="RUB",
                date=datetime(2025, 1, 2, 10, 0),
                description="OPERATION_TYPE_OUTPUT",
            ),
            Trade(
                account_id=account.id,
                symbol="TEST",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=1,
                entry_at=datetime(2025, 1, 3, 10, 0),
                exit_price=150,
                exit_at=datetime(2025, 1, 3, 11, 0),
                pnl=50,
                net_pnl=50,
            ),
        ])
        db.commit()

        response = client.get("/deposits/balance", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["net_deposit"] == 800.0
        assert data["total_deposits"] == 1000.0
        assert data["total_withdrawals"] == 200.0
        assert data["journal_pnl"] == 50.0
        assert data["current_balance"] == 850.0
        assert data["local_current_balance"] == 850.0
        assert data["balance_source"] == "journal"

        history_response = client.get("/deposits/history", headers=auth_headers)
        assert history_response.status_code == 200
        history = history_response.json()
        assert len(history) == 2
        assert history[0]["source"] == "broker"
        assert history[0]["can_delete"] is False
        assert history[1]["source"] == "broker"
        assert history[1]["can_delete"] is False

    def test_broker_net_deposit_endpoint_returns_true_net_deposit(self, test_app, test_user, auth_headers):
        client = test_app["client"]
        db = test_app["db"]
        account = db.query(Account).filter(Account.user_id == test_user.id).first()

        from datetime import datetime
        from models import BrokerConnection, BrokerType

        db.add(BrokerConnection(
            account_id=account.id,
            broker=BrokerType.TINKOFF,
            api_token="test-token",
            broker_account_id="broker-account",
            is_active=True,
        ))
        db.add_all([
            CapitalOperation(
                account_id=account.id,
                broker_id="dep-1",
                operation_type="deposit",
                amount=1000,
                currency="RUB",
                date=datetime(2025, 1, 1, 10, 0),
                description="OPERATION_TYPE_INPUT",
            ),
            CapitalOperation(
                account_id=account.id,
                broker_id="wd-1",
                operation_type="withdrawal",
                amount=300,
                currency="RUB",
                date=datetime(2025, 1, 2, 10, 0),
                description="OPERATION_TYPE_OUTPUT",
            ),
            Trade(
                account_id=account.id,
                symbol="TEST",
                direction=TradeDirection.LONG,
                entry_price=100,
                quantity=1,
                entry_at=datetime(2025, 1, 3, 10, 0),
                exit_price=140,
                exit_at=datetime(2025, 1, 3, 11, 0),
                pnl=40,
                net_pnl=35,
                commission=5,
            ),
        ])
        db.commit()

        response = client.get("/broker/net-deposit", headers=auth_headers, params={"date": "2025-01-05T00:00:00"})
        assert response.status_code == 200
        data = response.json()

        assert data["net_deposit"] == 700.0
        assert data["equity_on_date"] == 735.0

    def test_import_balance_report_saves_historical_snapshots(self, test_app, test_user, auth_headers, monkeypatch):
        client = test_app["client"]
        db = test_app["db"]

        from datetime import datetime

        monkeypatch.setattr(
            "routers.deposits.import_service.parse_account_balance",
            lambda contents, filename: {
                "initial_balance": 55000.0,
                "final_balance": 62000.0,
                "deposits": None,
                "withdrawals": None,
                "currency": "RUB",
                "period_start": datetime(2025, 12, 1, 0, 0),
                "period_end": datetime(2025, 12, 31, 23, 59),
            },
        )

        response = client.post(
            "/deposits/import-balance-report",
            headers=auth_headers,
            files={"file": ("report.xlsx", b"fake-xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["snapshots"]) == 2

        account = db.query(Account).filter(Account.user_id == test_user.id).first()
        snapshots = db.query(BalanceSnapshot).filter(
            BalanceSnapshot.account_id == account.id,
        ).order_by(BalanceSnapshot.date.asc()).all()

        assert len(snapshots) == 2
        assert float(snapshots[0].balance) == 55000.0
        assert float(snapshots[1].balance) == 62000.0
        assert snapshots[0].source == "balance_report:report.xlsx"
    
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

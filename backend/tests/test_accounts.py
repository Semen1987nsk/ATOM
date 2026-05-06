"""
Tests for /accounts/ (multi-account CRUD + active-switch).
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from models import Base, User, Account  # noqa: E402
from database import get_db  # noqa: E402
import auth_service  # noqa: E402


@pytest.fixture(scope="function")
def test_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
def user_with_account(test_app):
    db = test_app["db"]
    user = User(
        email="acc@example.com",
        name="Acc User",
        hashed_password=auth_service.get_password_hash("testpass1234"),
        is_active=1,
        settings={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    account = Account(
        user_id=user.id, name="Основной", initial_balance=Decimal("100000"),
        balance=Decimal("100000"), currency="RUB",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"user": user, "account": account}


@pytest.fixture
def auth_headers(user_with_account):
    user = user_with_account["user"]
    token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


class TestAccountsList:
    def test_list_returns_user_accounts(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        r = client.get("/accounts/", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["name"] == "Основной"
        assert body[0]["is_active"] is True  # единственный → активный

    def test_list_isolated_from_other_user(self, test_app, user_with_account, auth_headers):
        """Другой юзер не видит чужие счета."""
        db = test_app["db"]
        other = User(
            email="other@example.com", name="Other",
            hashed_password=auth_service.get_password_hash("testpass1234"),
            is_active=1, settings={},
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        Account_ = Account(user_id=other.id, name="Other Acc", initial_balance=Decimal("0"), currency="RUB")
        db.add(Account_)
        db.commit()
        token = auth_service.create_access_token(data={"sub": str(other.id), "email": other.email})
        r = test_app["client"].get("/accounts/", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        names = {a["name"] for a in r.json()}
        assert "Основной" not in names


class TestAccountsCreate:
    def test_create_account(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        r = client.post("/accounts/", headers=auth_headers, json={
            "name": "ИИС типа А",
            "currency": "RUB",
            "initial_balance": 400000,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "ИИС типа А"
        assert body["initial_balance"] == 400000.0
        # Список теперь содержит 2 счёта
        r2 = client.get("/accounts/", headers=auth_headers)
        assert len(r2.json()) == 2

    def test_create_validates_name(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        r = client.post("/accounts/", headers=auth_headers, json={"name": ""})
        assert r.status_code == 422


class TestAccountsActivate:
    def test_activate_switches_default(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        # Создаём второй
        r = client.post("/accounts/", headers=auth_headers, json={"name": "Срочный", "initial_balance": 0})
        new_id = r.json()["id"]
        # Активируем второй
        r = client.post(f"/accounts/{new_id}/activate", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == new_id
        assert r.json()["is_active"] is True
        # В списке ровно один активный — новый
        r = client.get("/accounts/", headers=auth_headers)
        actives = [a for a in r.json() if a["is_active"]]
        assert len(actives) == 1
        assert actives[0]["id"] == new_id

    def test_activate_404_for_other_users_account(self, test_app, user_with_account, auth_headers):
        db = test_app["db"]
        other = User(
            email="other@example.com", name="Other",
            hashed_password=auth_service.get_password_hash("testpass1234"),
            is_active=1, settings={},
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        other_acc = Account(user_id=other.id, name="OtherAcc", initial_balance=Decimal("0"), currency="RUB")
        db.add(other_acc)
        db.commit()
        db.refresh(other_acc)
        r = test_app["client"].post(f"/accounts/{other_acc.id}/activate", headers=auth_headers)
        assert r.status_code == 404


class TestAccountsRename:
    def test_rename(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        acc_id = user_with_account["account"].id
        r = client.patch(f"/accounts/{acc_id}", headers=auth_headers, json={"name": "Прокачанный"})
        assert r.status_code == 200
        assert r.json()["name"] == "Прокачанный"


class TestAccountsDelete:
    def test_cannot_delete_last_account(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        acc_id = user_with_account["account"].id
        r = client.delete(f"/accounts/{acc_id}", headers=auth_headers)
        assert r.status_code == 400

    def test_delete_keeps_user_with_at_least_one(self, test_app, user_with_account, auth_headers):
        client = test_app["client"]
        # Создаём 2-й
        r2 = client.post("/accounts/", headers=auth_headers, json={"name": "Aux", "initial_balance": 0})
        aux_id = r2.json()["id"]
        # Удаляем первый
        first_id = user_with_account["account"].id
        r = client.delete(f"/accounts/{first_id}", headers=auth_headers)
        assert r.status_code == 204
        # В списке остался только aux, и он активный
        rl = client.get("/accounts/", headers=auth_headers).json()
        assert len(rl) == 1
        assert rl[0]["id"] == aux_id
        assert rl[0]["is_active"] is True

    def test_delete_active_switches_active(self, test_app, user_with_account, auth_headers):
        """Если удаляем активный — переключаемся на оставшийся, не падаем."""
        client = test_app["client"]
        first_id = user_with_account["account"].id
        # active по умолчанию = первый
        r2 = client.post("/accounts/", headers=auth_headers, json={"name": "Second", "initial_balance": 0})
        second_id = r2.json()["id"]
        # Активируем first явно
        client.post(f"/accounts/{first_id}/activate", headers=auth_headers)
        # Удаляем активный
        r = client.delete(f"/accounts/{first_id}", headers=auth_headers)
        assert r.status_code == 204
        # Active теперь second
        rl = client.get("/accounts/", headers=auth_headers).json()
        assert len(rl) == 1
        assert rl[0]["id"] == second_id
        assert rl[0]["is_active"] is True

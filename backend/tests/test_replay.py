"""
Tests for /trades/{id}/replay (Trade Replay endpoint).

Mock'аем MoexService.get_candles, чтобы тесты не зависели от сети /
доступности MOEX ISS (CI без интернета не должен ронять прогон).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from models import Base, User, Account, Trade, TradeDirection  # noqa: E402
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
def user_with_trade(test_app):
    db = test_app["db"]
    user = User(
        email="replay@example.com",
        name="Replay User",
        hashed_password=auth_service.get_password_hash("testpass1234"),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    account = Account(user_id=user.id, name="Acc", initial_balance=Decimal("100000"), currency="RUB")
    db.add(account)
    db.commit()
    db.refresh(account)

    entry_at = datetime(2026, 4, 1, 10, 30)
    exit_at = datetime(2026, 4, 1, 14, 0)
    trade = Trade(
        account_id=account.id,
        symbol="SBER",
        direction=TradeDirection.LONG,
        entry_price=Decimal("300.00"),
        exit_price=Decimal("305.50"),
        quantity=Decimal("100"),
        entry_at=entry_at,
        exit_at=exit_at,
        stop_loss=Decimal("294.00"),
        take_profit=Decimal("312.00"),
        mae_price=Decimal("298.50"),
        mfe_price=Decimal("306.20"),
        pnl=Decimal("550"),
        net_pnl=Decimal("540"),
        currency="RUB",
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)

    return {"user": user, "account": account, "trade": trade}


@pytest.fixture
def auth_headers(user_with_trade):
    user = user_with_trade["user"]
    token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────

class _FakeMoex:
    def __init__(self, candles=None, fail=False):
        self.candles = candles or []
        self.fail = fail
        self.last_call = None

    def auto_interval(self, span):
        # Не используем — endpoint всё равно вызовет get_candles напрямую.
        return "10m"

    async def get_candles(self, ticker, interval, start, end):
        # SYNC-04 (Task 1.3): MoexService.get_candles стал async.
        # Fake тоже async, чтобы await в роутере не падал.
        self.last_call = (ticker, interval, start, end)
        if self.fail:
            raise RuntimeError("network down")
        return list(self.candles)


def _sample_candles(n=5):
    base = datetime(2026, 4, 1, 10, 0)
    return [
        {
            "t": (base + timedelta(minutes=i * 10)).strftime("%Y-%m-%d %H:%M:%S"),
            "o": 300 + i * 0.5,
            "h": 301 + i * 0.5,
            "l": 299 + i * 0.5,
            "c": 300.5 + i * 0.5,
            "v": 1000 + i * 100,
        }
        for i in range(n)
    ]


# ──────────────────────────────────────────────────────────────────
#  Tests
# ──────────────────────────────────────────────────────────────────


class TestReplay:
    def test_replay_returns_candles_and_markers(self, test_app, user_with_trade, auth_headers):
        client = test_app["client"]
        trade_id = user_with_trade["trade"].id
        fake = _FakeMoex(candles=_sample_candles(5))
        with patch("routers.replay.get_moex_service", return_value=fake):
            r = client.get(f"/trades/{trade_id}/replay", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["trade_id"] == trade_id
        assert body["symbol"] == "SBER"
        assert body["direction"].lower() == "long"
        assert body["is_open"] is False
        assert len(body["candles"]) == 5
        # Все 6 маркеров должны прийти (entry, exit, sl, tp, mae, mfe).
        marker_types = {m["type"] for m in body["markers"]}
        assert marker_types == {"entry", "exit", "sl", "tp", "mae", "mfe"}
        # Цены маркеров — те, что в БД.
        prices = {m["type"]: m["price"] for m in body["markers"]}
        assert prices["entry"] == 300.0
        assert prices["exit"] == 305.5
        assert prices["sl"] == 294.0
        assert prices["tp"] == 312.0
        assert prices["mae"] == 298.5
        assert prices["mfe"] == 306.2

    def test_replay_404_for_other_users_trade(self, test_app, user_with_trade):
        """Нельзя достать чужую сделку — изоляция по account_id."""
        client = test_app["client"]
        # Создаём другого юзера + аккаунт в той же сессии.
        db = test_app["db"]
        other = User(
            email="other@example.com",
            name="Other",
            hashed_password=auth_service.get_password_hash("testpass1234"),
            is_active=1,
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        Account_ = Account(user_id=other.id, name="other", initial_balance=Decimal("0"), currency="RUB")
        db.add(Account_)
        db.commit()

        token = auth_service.create_access_token(data={"sub": str(other.id), "email": other.email})
        headers = {"Authorization": f"Bearer {token}"}
        trade_id = user_with_trade["trade"].id  # принадлежит первому юзеру
        with patch("routers.replay.get_moex_service", return_value=_FakeMoex(_sample_candles())):
            r = client.get(f"/trades/{trade_id}/replay", headers=headers)
        assert r.status_code == 404

    def test_replay_404_for_nonexistent_trade(self, test_app, user_with_trade, auth_headers):
        client = test_app["client"]
        with patch("routers.replay.get_moex_service", return_value=_FakeMoex(_sample_candles())):
            r = client.get("/trades/99999/replay", headers=auth_headers)
        assert r.status_code == 404

    def test_replay_explicit_interval_passes_through(self, test_app, user_with_trade, auth_headers):
        client = test_app["client"]
        trade_id = user_with_trade["trade"].id
        fake = _FakeMoex(candles=_sample_candles())
        with patch("routers.replay.get_moex_service", return_value=fake):
            r = client.get(f"/trades/{trade_id}/replay?interval=1h", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["interval"] == "1h"
        assert body["interval_auto"] is False
        # Параметр должен дойти до moex.get_candles
        assert fake.last_call is not None
        ticker, interval, _, _ = fake.last_call
        assert ticker == "SBER"
        assert interval == "1h"

    def test_replay_empty_candles_returns_note(self, test_app, user_with_trade, auth_headers):
        """Если MOEX ничего не отдал — endpoint не падает, кладёт human-readable note."""
        client = test_app["client"]
        trade_id = user_with_trade["trade"].id
        with patch("routers.replay.get_moex_service", return_value=_FakeMoex(candles=[])):
            r = client.get(f"/trades/{trade_id}/replay", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["candles"] == []
        assert body["note"]
        # Маркеры всё ещё должны быть, чтобы хотя бы цены показать.
        assert len(body["markers"]) == 6

    def test_replay_open_trade_uses_now_as_anchor(self, test_app, user_with_trade, auth_headers):
        """Для открытой сделки exit_at=None → range_end ≈ now."""
        db = test_app["db"]
        trade = user_with_trade["trade"]
        trade.exit_at = None
        trade.exit_price = None
        db.commit()
        client = test_app["client"]
        fake = _FakeMoex(candles=_sample_candles())
        with patch("routers.replay.get_moex_service", return_value=fake):
            r = client.get(f"/trades/{trade.id}/replay", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["is_open"] is True
        # Маркер exit отсутствует, но entry/sl/tp/mae/mfe — есть.
        marker_types = {m["type"] for m in body["markers"]}
        assert "exit" not in marker_types
        assert "entry" in marker_types

    def test_replay_unauthenticated(self, test_app, user_with_trade):
        client = test_app["client"]
        r = client.get(f"/trades/{user_with_trade['trade'].id}/replay")
        assert r.status_code in (401, 403)

    def test_replay_markers_in_msk_scale(self, test_app, user_with_trade, auth_headers):
        """MAE-02: маркеры и окно — в шкале свечей ISS (naive-МСК).

        В БД entry_at = 2026-04-01 10:30 UTC. Свечи MOEX в МСК, фронт строит
        ось по new Date() для обеих величин → маркер обязан прийти как
        13:30 (МСК), иначе он встаёт на 3 часа левее свечи входа."""
        client = test_app["client"]
        trade_id = user_with_trade["trade"].id
        fake = _FakeMoex(candles=_sample_candles(5))
        with patch("routers.replay.get_moex_service", return_value=fake):
            r = client.get(f"/trades/{trade_id}/replay", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()

        entry_marker = next(m for m in body["markers"] if m["type"] == "entry")
        # 10:30 UTC = 13:30 МСК
        assert entry_marker["t"].startswith("2026-04-01T13:30"), entry_marker["t"]
        exit_marker = next(m for m in body["markers"] if m["type"] == "exit")
        # 14:00 UTC = 17:00 МСК
        assert exit_marker["t"].startswith("2026-04-01T17:00"), exit_marker["t"]

        # Окно запроса свечей к ISS — тоже МСК (pad 60 минут от 13:30/17:00)
        _, _, start, end = fake.last_call
        assert start.hour == 12 and start.minute == 30, start
        assert end.hour == 18 and end.minute == 0, end

"""PERF-07: fingerprint — 1 aggregate SQL, без загрузки всех Trade-rows.

Проверяет:
- `routers.stats._get_trades_state_fingerprint(db, account_id)` делает один
  aggregate SQL (max+count), без полного скана Trade-таблицы.
- Fingerprint меняется при INSERT нового трейда.
- Fingerprint меняется при DELETE существующего трейда.
- Fingerprint стабилен на повторных вызовах без изменений.

Контекст: до PERF-07 fingerprint считался по уже загруженному `list[Trade]`,
что заставляло `/stats/` грузить ВСЕ трейды даже при cache hit. После
PERF-07 fingerprint строится дешёвым SQL'ем ДО загрузки трейдов.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from models import Account, Base, Trade, TradeDirection, User


# ─────────────────────────────────────────────────────────────────────
# Local fixtures — изолированный engine, чтобы повесить event-listener
# на конкретный engine (db_session из global conftest держит свой).
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def fp_db():
    """Session + engine pair — engine нужен для event-listener'а."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield {"engine": engine, "session": session}
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def seed_account(fp_db):
    """Создаёт User + Account + 5 закрытых трейдов."""
    db = fp_db["session"]
    user = User(
        email="fp@test.com",
        hashed_password="x",
        is_active=1,
        is_admin=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    acc = Account(
        user_id=user.id, name="Main", currency="RUB", initial_balance=Decimal("100000")
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    base = datetime(2026, 1, 1, 10, 0)
    for i in range(5):
        entry = base + timedelta(hours=i)
        db.add(
            Trade(
                account_id=acc.id,
                symbol=f"S{i:03d}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("101"),
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=10000 + i,
                commission=Decimal("0"),
                pnl=Decimal("10"),
                net_pnl=Decimal("10"),
            )
        )
    db.commit()
    return acc


@pytest.fixture
def insert_trade(fp_db):
    """Хелпер: создать новый Trade для аккаунта."""
    db = fp_db["session"]

    def _insert(account_id: int):
        next_idx = db.query(Trade).filter(Trade.account_id == account_id).count() + 100
        t = Trade(
            account_id=account_id,
            symbol=f"NEW{next_idx}",
            direction=TradeDirection.LONG,
            entry_price=Decimal("200"),
            exit_price=Decimal("210"),
            quantity=Decimal("5"),
            entry_at=datetime(2026, 2, 1, 10, 0),
            exit_at=datetime(2026, 2, 1, 11, 0),
            currency="RUB",
            data_source="manual",
            position_id=99999 + next_idx,
            commission=Decimal("0"),
            pnl=Decimal("50"),
            net_pnl=Decimal("50"),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return t

    return _insert


@pytest.fixture
def query_counter(fp_db):
    """Считает все SQL-запросы на engine'е."""
    engine = fp_db["engine"]
    counts = {"n": 0, "statements": []}

    def _count(conn, cursor, statement, parameters, context, executemany):
        counts["n"] += 1
        counts["statements"].append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    yield counts
    event.remove(engine, "before_cursor_execute", _count)


# ─────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────


def test_fingerprint_uses_single_aggregate_query(fp_db, seed_account, query_counter):
    """PERF-07: один aggregate SQL, не полный скан."""
    from routers.stats import _get_trades_state_fingerprint

    # Прогреваем доступ к атрибутам (после commit() в seed_account сессия
    # expired — первое чтение account_id выстрелит лишний SELECT по Account).
    account_id = seed_account.id

    # Сбрасываем счётчик ПОСЛЕ всех setup'ных запросов.
    query_counter["n"] = 0
    query_counter["statements"].clear()

    fp = _get_trades_state_fingerprint(fp_db["session"], account_id=account_id)

    assert isinstance(fp, str)
    assert fp != ""
    assert query_counter["n"] == 1, (
        f"Ожидался 1 SQL-запрос, получили {query_counter['n']}:\n"
        + "\n---\n".join(query_counter["statements"])
    )
    # Убеждаемся, что это именно aggregate, а не SELECT всех trades.
    stmt = query_counter["statements"][0].lower()
    assert "max(" in stmt and "count(" in stmt, (
        f"Ожидали aggregate (max+count), получили:\n{stmt}"
    )
    # Не должно быть полного скана колонок trades.
    assert "trades.symbol" not in stmt, f"fingerprint грузит лишние колонки:\n{stmt}"


def test_fingerprint_changes_after_trade_insert(fp_db, seed_account, insert_trade):
    """Новый INSERT → fingerprint изменился."""
    from routers.stats import _get_trades_state_fingerprint

    fp1 = _get_trades_state_fingerprint(fp_db["session"], account_id=seed_account.id)
    insert_trade(account_id=seed_account.id)
    fp2 = _get_trades_state_fingerprint(fp_db["session"], account_id=seed_account.id)

    assert fp1 != fp2


def test_fingerprint_stable_without_changes(fp_db, seed_account):
    """Повторный вызов без изменений → тот же fingerprint."""
    from routers.stats import _get_trades_state_fingerprint

    fp1 = _get_trades_state_fingerprint(fp_db["session"], account_id=seed_account.id)
    fp2 = _get_trades_state_fingerprint(fp_db["session"], account_id=seed_account.id)

    assert fp1 == fp2


def test_fingerprint_changes_after_trade_delete(fp_db, seed_account):
    """DELETE → count меняется → fingerprint меняется."""
    from routers.stats import _get_trades_state_fingerprint

    db = fp_db["session"]
    fp1 = _get_trades_state_fingerprint(db, account_id=seed_account.id)

    victim = db.query(Trade).filter(Trade.account_id == seed_account.id).first()
    db.delete(victim)
    db.commit()

    fp2 = _get_trades_state_fingerprint(db, account_id=seed_account.id)
    assert fp1 != fp2


def test_fingerprint_isolated_by_account(fp_db, seed_account, insert_trade):
    """Изменение трейдов одного аккаунта не должно ломать fingerprint другого."""
    from routers.stats import _get_trades_state_fingerprint

    db = fp_db["session"]
    other_user = User(
        email="fp-other@test.com", hashed_password="x", is_active=1, is_admin=0
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    other_acc = Account(
        user_id=other_user.id, name="Other", currency="RUB", initial_balance=Decimal("0")
    )
    db.add(other_acc)
    db.commit()
    db.refresh(other_acc)

    fp_other_before = _get_trades_state_fingerprint(db, account_id=other_acc.id)
    insert_trade(account_id=seed_account.id)
    fp_other_after = _get_trades_state_fingerprint(db, account_id=other_acc.id)

    assert fp_other_before == fp_other_after


# ─────────────────────────────────────────────────────────────────────
# Integration: проверяем, что /stats/ на cache hit НЕ грузит трейды.
# Это главное практическое следствие PERF-07: fingerprint считается ДО
# `query.all()`, поэтому при hit'е dispatcher не делает SELECT * FROM trades.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def stats_client():
    """FastAPI TestClient + изолированный engine + auth-токен."""
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool

    from main import app
    from database import get_db
    import auth_service

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = SessionLocal()

    user = User(
        email="perf07@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
        is_admin=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    acc = Account(
        user_id=user.id, name="Main", currency="RUB", initial_balance=Decimal("100000")
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    base = datetime(2026, 1, 1, 10, 0)
    # Чередуем wins/losses, чтобы analytics не давала NaN/None (profit_factor,
    # sortino_ratio падают на одной стороне).
    for i in range(20):
        entry = base + timedelta(hours=i)
        pnl_val = Decimal("100") if i % 2 == 0 else Decimal("-50")
        db.add(
            Trade(
                account_id=acc.id,
                symbol=f"S{i:03d}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("101"),
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=20000 + i,
                commission=Decimal("0"),
                pnl=pnl_val,
                net_pnl=pnl_val,
            )
        )
    db.commit()

    token = auth_service.create_access_token({"sub": str(user.id)})

    # Чистим module-global stats_cache между тестами, чтобы первый запрос
    # реально шёл по miss-пути.
    from services.stats_cache import stats_cache
    stats_cache.clear()

    try:
        yield {
            "client": TestClient(app),
            "db": db,
            "engine": engine,
            "token": token,
            "account_id": acc.id,
        }
    finally:
        stats_cache.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def test_stats_cache_hit_does_not_load_trades(stats_client):
    """PERF-07 главный кейс: на cache hit `query.all()` для Trade не выполняется.

    Шаги:
    1. Первый GET /stats/ — miss → грузим трейды (видим SELECT с trades.symbol).
    2. Второй GET /stats/ с теми же параметрами — hit → SELECT trades.* не должно
       быть; только дешёвый aggregate-fingerprint + чтение Account.

    Если кто-то откатит PERF-07 (вернёт fingerprint=по trades) — этот тест
    отловит регрессию: cache hit станет тащить все trades.
    """
    client = stats_client["client"]
    token = stats_client["token"]
    engine = stats_client["engine"]
    headers = {"Authorization": f"Bearer {token}"}

    # Прогрев: первый запрос (cache miss).
    resp1 = client.get("/stats/", headers=headers)
    assert resp1.status_code == 200, resp1.text

    # Теперь подключаем слушатель — фиксируем все SELECT'ы при cache-hit.
    captured = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        resp2 = client.get("/stats/", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert resp2.status_code == 200, resp2.text

    # Cache HIT: НЕ должно быть SELECT'а полных trade-rows.
    full_trade_selects = [
        s for s in captured
        if "trades.symbol" in s.lower() and "from trades" in s.lower()
    ]
    assert not full_trade_selects, (
        "На cache hit /stats/ не должен загружать все Trade-rows, но получили:\n"
        + "\n---\n".join(full_trade_selects)
    )
    # Sanity: aggregate-fingerprint SQL должен быть.
    has_aggregate = any(
        "count(trades.id)" in s.lower() and "max(trades.id)" in s.lower()
        for s in captured
    )
    assert has_aggregate, (
        "Ожидался aggregate-fingerprint SQL, выполненные SQL:\n"
        + "\n---\n".join(captured)
    )

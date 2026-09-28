"""Sprint 6.5 Batch 3 — PNL-01 / PNL-02 на /stats/advanced и /stats/benchmark.

PNL-01: /stats/benchmark падал с 500 (TypeError) для юзеров с историей >= 90
дней: `calculate_calmar_ratio(cagr_pct or 0, ...)` передавал float туда, где
сигнатура ждёт List[float] (len(float) → TypeError).

PNL-02: drawdown baseline в обоих эндпойнтах был `equity[0]` — PnL ПЕРВОЙ
сделки (кумулятив от 0), а не капитал. Канон (как в /stats/) — net deposits
через `get_net_deposits_baseline_from_db`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from fastapi.testclient import TestClient

from main import app
from models import Account, Base, OperationORM, Trade, TradeDirection, User
from database import get_db
import auth_service


@pytest.fixture
def client_with_db():
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
    try:
        yield {"client": TestClient(app), "db": db_session}
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def _setup_user(db):
    u = User(
        email="pnl0102-stats@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
        is_admin=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(
        user_id=u.id, name="Main", currency="RUB", initial_balance=Decimal("0")
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, acc, token


DEPOSIT = 100_000.0
# pnls по порядку entry_at; equity: 1000, 500, 2500, 1000, 4000.
PNLS = [1000, -500, 2000, -1500, 3000]
# Просадка от депозитного baseline 100_000:
#   peak 102_500 → дно 101_000 → dd = 1500 / 102500 = 1.46 %.
EXPECTED_DD_PCT = round(1500 / 102500 * 100, 2)  # 1.46
# Просадка от БАГНУТОГО baseline equity[0]=1000:
#   peak 3500 → дно 2000 → dd = 1500 / 3500 = 42.86 %.
BUGGY_DD_PCT = round(1500 / 3500 * 100, 2)  # 42.86


def _seed_net_deposit(db, account_id: int, amount: float = DEPOSIT):
    db.add(
        OperationORM(
            account_id=account_id,
            broker_account_id="test-broker-acc",
            operation_id="op-deposit-1",
            operation_type="input",  # OperationType.INPUT → NET_DEPOSIT
            state="executed",
            quantity=0,
            payment_units=int(amount),
            payment_nano=0,
            payment_currency="rub",
            executed_at=datetime(2025, 12, 30, 10, 0),
        )
    )
    db.commit()


def _seed_long_history_trades(db, account_id: int):
    """5 закрытых трейдов, история > 90 дней (триггер CAGR-ветки)."""
    entry_dates = [
        datetime(2026, 1, 1, 10, 0),
        datetime(2026, 1, 20, 10, 0),
        datetime(2026, 2, 10, 10, 0),
        datetime(2026, 3, 5, 10, 0),
        datetime(2026, 4, 15, 10, 0),  # 104 дня от первой → >= 90
    ]
    for i, (entry, pnl) in enumerate(zip(entry_dates, PNLS)):
        db.add(
            Trade(
                account_id=account_id,
                symbol=f"TST{i:02d}",
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=50000 + i,
                commission=Decimal("0"),
                pnl=Decimal(str(pnl)),
                net_pnl=Decimal(str(pnl)),
            )
        )
    db.commit()


def test_benchmark_no_500_for_long_history(client_with_db):
    """PNL-01: /stats/benchmark не должен падать 500 при истории >= 90 дней.

    cagr_pct становится не-нулевым float → старый код передавал его в
    calculate_calmar_ratio(trades_pnl=...) → len(float) → TypeError → 500.
    """
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_net_deposit(db, acc.id)
    _seed_long_history_trades(db, acc.id)

    resp = client.get(
        "/stats/benchmark",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = {item["name"]: item for item in body.get("items", [])}
    # calmar должен присутствовать и быть числом (CAGR>0, DD>0 → определён).
    assert "calmar" in items, f"calmar отсутствует в items: {sorted(items)}"
    assert isinstance(items["calmar"]["user_value"], (int, float))


def test_benchmark_max_drawdown_uses_deposit_baseline(client_with_db):
    """PNL-02: max_drawdown_pct в /stats/benchmark — от net-deposits baseline."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_net_deposit(db, acc.id)
    _seed_long_history_trades(db, acc.id)

    resp = client.get(
        "/stats/benchmark",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    items = {item["name"]: item for item in resp.json().get("items", [])}
    dd = items["max_drawdown_pct"]["user_value"]
    assert dd == pytest.approx(EXPECTED_DD_PCT, abs=0.05), (
        f"ожидался dd от депозитного baseline ~{EXPECTED_DD_PCT}%, "
        f"получено {dd}% (багнутый baseline=первая сделка дал бы ~{BUGGY_DD_PCT}%)"
    )


def test_advanced_baseline_includes_initial_balance_anchor(client_with_db):
    """I1 (ADR-0010): baseline в /stats/advanced = net_deposits + initial_balance.

    Восстановленный стартовый якорь (broker-счёт с неполной историей) сдвигает
    drawdown-baseline вверх → max_drawdown_pct падает. Без якоря (предыдущий код)
    baseline = только net_deposits и просадка завышена.
    """
    db = client_with_db["db"]
    client = client_with_db["client"]
    u, acc, token = _setup_user(db)
    # Якорь 50_000 поверх депозита 100_000 → baseline 150_000.
    acc.initial_balance = Decimal("50000")
    acc.initial_balance_source = "inferred_anchor"
    db.commit()
    _seed_net_deposit(db, acc.id)
    _seed_long_history_trades(db, acc.id)

    resp = client.get("/stats/advanced", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    items = resp.json().get("items", {})
    cagr = items.get("cagr_pct")
    mar = items.get("mar_ratio")
    assert cagr is not None and cagr > 0
    # baseline = 150_000: peak 152_500 → дно 151_000 → dd = 1500/152500 = 0.98%.
    anchored_dd_pct = round(1500 / 152500 * 100, 2)
    expected_mar = round(cagr / anchored_dd_pct, 2)
    # baseline без якоря (100_000) дал бы EXPECTED_DD_PCT=1.46% и другой MAR.
    no_anchor_mar = round(cagr / EXPECTED_DD_PCT, 2)
    assert mar == pytest.approx(expected_mar, abs=0.05), (
        f"ожидался mar от anchored baseline ~{expected_mar}, получено {mar} "
        f"(без якоря дал бы ~{no_anchor_mar})"
    )


def test_advanced_mar_ratio_uses_deposit_baseline(client_with_db):
    """PNL-02: /stats/advanced — dd_stats от net-deposits baseline.

    dd_stats не возвращается напрямую, но mar_ratio = cagr_pct / max_dd_pct —
    по нему видно какой baseline ушёл в calculate_drawdown_stats.
    """
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_net_deposit(db, acc.id)
    _seed_long_history_trades(db, acc.id)

    resp = client.get(
        "/stats/advanced",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json().get("items", {})
    cagr = items.get("cagr_pct")
    mar = items.get("mar_ratio")
    assert cagr is not None and cagr > 0, f"ожидался CAGR > 0, получено {cagr!r}"
    assert mar is not None, "mar_ratio не должен быть None при CAGR>0 и DD>0"
    expected_mar = round(cagr / EXPECTED_DD_PCT, 2)
    buggy_mar = round(cagr / BUGGY_DD_PCT, 2)
    assert mar == pytest.approx(expected_mar, abs=0.05), (
        f"ожидался mar от депозитного baseline ~{expected_mar}, получено {mar} "
        f"(багнутый baseline=первая сделка дал бы ~{buggy_mar})"
    )

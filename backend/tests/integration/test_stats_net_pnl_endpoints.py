"""Sprint 4 — endpoint-уровневые тесты на корректность P&L аналитики.

MATH-05: profit_factor при отсутствии loss-трейдов должен быть None (UNDEFINED),
а не 0. Семантически 0 = "плохой PF", тогда как all-winners = идеальный (infinity)
и должен представляться как UNDEFINED (None) — так же, как в
`analytics.calculate_advanced_stats`.

MATH-01 (Batch 2): analytics-эндпойнты должны использовать NET-pnl (после
комиссий) для всех агрегатов вместо GROSS-pnl. Канон:
`float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))`.
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
from models import Account, Base, Trade, TradeDirection, User
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
        email="math05-stats@test.com",
        hashed_password=auth_service.get_password_hash("pass1234"),
        is_active=1,
        is_admin=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    acc = Account(
        user_id=u.id, name="Main", currency="RUB", initial_balance=Decimal("100000")
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, acc, token


def _seed_all_winner_trades(db, account_id: int, n: int = 4):
    """Создаёт N закрытых winning трейдов с заполненными mae/mfe_price.

    Все pnl > 0, ни одного убыточного — это триггер для MATH-05.
    """
    base = datetime(2026, 1, 1, 10, 0)
    for i in range(n):
        entry = base + timedelta(hours=i)
        entry_price = Decimal("100")
        exit_price = Decimal("110")  # +10% — winner
        # mae_price < entry (просадка в просадке для long), mfe_price > exit (макс. рост)
        mae_price = Decimal("98")
        mfe_price = Decimal("112")
        pnl = Decimal("100")  # +100 на трейд
        db.add(
            Trade(
                account_id=account_id,
                symbol=f"WIN{i:02d}",
                direction=TradeDirection.LONG,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=20000 + i,
                commission=Decimal("0"),
                pnl=pnl,
                net_pnl=pnl,
                mae_price=mae_price,
                mfe_price=mfe_price,
            )
        )
    db.commit()


def _seed_mixed_trades(db, account_id: int):
    """Винеры + лузер — проверка что обычный путь (PF=число) не сломан."""
    base = datetime(2026, 1, 1, 10, 0)
    rows = [
        # (symbol, exit_price, pnl)
        ("MIX01", Decimal("110"), Decimal("100")),
        ("MIX02", Decimal("110"), Decimal("100")),
        ("MIX03", Decimal("90"), Decimal("-50")),  # лузер
    ]
    for i, (sym, exit_price, pnl) in enumerate(rows):
        entry = base + timedelta(hours=i)
        db.add(
            Trade(
                account_id=account_id,
                symbol=sym,
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=exit_price,
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=30000 + i,
                commission=Decimal("0"),
                pnl=pnl,
                net_pnl=pnl,
                mae_price=Decimal("98"),
                mfe_price=Decimal("112"),
            )
        )
    db.commit()


def test_mae_mfe_analysis_profit_factor_undefined_for_all_winners(client_with_db):
    """MATH-05: при отсутствии loss-трейдов profit_factor == None (UNDEFINED), не 0."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_all_winner_trades(db, acc.id, n=4)

    resp = client.get(
        "/stats/mae-mfe-analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # group_by=overall возвращает поля _analyze_trades_mae_mfe на top-level.
    assert body.get("profit_factor") is None, (
        f"expected None (UNDEFINED) при all-winners, got {body.get('profit_factor')!r}"
    )
    # Sanity: winrate должен быть 100%, losses=0
    assert body.get("losses") == 0
    assert body.get("wins") == 4


def test_mae_mfe_analysis_profit_factor_numeric_when_losses_exist(client_with_db):
    """Регрессия: смешанный набор (винеры+лузер) даёт числовой PF, не None."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_mixed_trades(db, acc.id)

    resp = client.get(
        "/stats/mae-mfe-analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    pf = body.get("profit_factor")
    assert pf is not None, "PF должен быть числом когда есть лузеры"
    # Wins=200, losses=50 → PF=4.0
    assert pf == pytest.approx(4.0, rel=1e-3), f"expected ~4.0, got {pf}"


# ============================================================================
# MATH-01 (Sprint 4 Batch 2) — NET-pnl migration в analytics-эндпойнтах
# ============================================================================


def _seed_high_commission_trades(
    db,
    account_id: int,
    *,
    symbol: str = "SBER",
    n: int = 5,
    gross_pnl: Decimal = Decimal("1000"),
    commission: Decimal = Decimal("600"),
):
    """Сеет N закрытых winning трейдов с большой commission.

    GROSS pnl = 1000, commission = 600, NET pnl = 400. Дельта (gross−net)=600
    на трейд — отличается достаточно, чтобы любой случайный round/clamp не
    мог скрыть подмену GROSS на NET.
    """
    net_pnl = gross_pnl - commission
    base = datetime(2026, 2, 1, 10, 0)
    for i in range(n):
        entry = base + timedelta(hours=i)
        db.add(
            Trade(
                account_id=account_id,
                symbol=symbol,
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                quantity=Decimal("10"),
                entry_at=entry,
                exit_at=entry + timedelta(minutes=30),
                currency="RUB",
                data_source="manual",
                position_id=40000 + i,
                commission=commission,
                pnl=gross_pnl,
                net_pnl=net_pnl,
                mae_price=Decimal("98"),
                mfe_price=Decimal("112"),
            )
        )
    db.commit()


def test_mae_mfe_analysis_uses_net_pnl_not_gross(client_with_db):
    """MATH-01 (Task 2.1): /stats/mae-mfe-analysis?group_by=overall → total_pnl должен быть NET-сумма."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    # 5 трейдов: gross=1000 → net=400 каждый. Σgross=5000, Σnet=2000.
    _seed_high_commission_trades(db, acc.id, n=5)

    resp = client.get(
        "/stats/mae-mfe-analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # _analyze_trades_mae_mfe возвращает total_pnl на top-level при group_by=overall.
    # NET-based: Σ = 5 × 400 = 2000.
    # GROSS-based: Σ = 5 × 1000 = 5000.
    assert body.get("total_pnl") == pytest.approx(2000, rel=0.01), (
        f"NET-based total_pnl=2000 ожидался, получено {body.get('total_pnl')} "
        f"(похоже на GROSS=5000)"
    )
    # avg_win должен тоже считаться от NET.
    assert body.get("avg_win") == pytest.approx(400, rel=0.01), (
        f"NET-based avg_win=400 ожидался, получено {body.get('avg_win')}"
    )


def test_mae_mfe_by_symbol_uses_net_pnl(client_with_db):
    """MATH-01 (Task 2.2): /stats/mae-mfe-by-symbol per-symbol total_pnl должен быть NET."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_high_commission_trades(db, acc.id, symbol="SBER", n=5)

    resp = client.get(
        "/stats/mae-mfe-by-symbol",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    symbols = body.get("symbols", [])
    sber = next((s for s in symbols if s["symbol"] == "SBER"), None)
    assert sber is not None, f"SBER должен быть в symbols, got {symbols}"
    # 5 × net 400 = 2000 (NET), vs 5000 (GROSS).
    assert sber["total_pnl"] == pytest.approx(2000, rel=0.01), (
        f"NET total_pnl=2000 ожидался, получено {sber['total_pnl']} (похоже на GROSS=5000)"
    )


def test_mae_mfe_by_symbol_filter_by_direction_uses_net_pnl(client_with_db):
    """MATH-01 (Task 2.2): по-направлению `by_direction.long.pnl` при single-symbol тоже NET."""
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_high_commission_trades(db, acc.id, symbol="GAZP", n=4)

    resp = client.get(
        "/stats/mae-mfe-by-symbol?symbol=GAZP",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    symbols = body.get("symbols", [])
    assert len(symbols) == 1
    by_dir = symbols[0].get("by_direction", {})
    long_pnl = by_dir.get("long", {}).get("pnl")
    # 4 × net 400 = 1600 (NET), vs 4000 (GROSS).
    assert long_pnl == pytest.approx(1600, rel=0.01), (
        f"NET long pnl=1600 ожидался, получено {long_pnl} (похоже на GROSS=4000)"
    )


def test_advanced_stats_use_net_pnl_in_dict_bindings(client_with_db):
    """MATH-01 (Task 2.3): /stats/advanced передаёт NET в analytics calls.

    Канарейка: `tax_visibility.realized_ytd` = сумма Σ pnl всех закрытых в
    этом году. Все 5 трейдов в 2026-02 → попадают в YTD только если
    `datetime.utcnow().year == 2026`. Чтобы тест был годо-независимым,
    проверяем через `period_breakdown.yearly.best.pnl` — это Σ всех pnl за год
    (один лучший год, у нас он 2026).
    """
    db = client_with_db["db"]
    client = client_with_db["client"]
    _, acc, token = _setup_user(db)
    _seed_high_commission_trades(db, acc.id, n=5)

    resp = client.get(
        "/stats/advanced",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body.get("items", {})
    period_breakdown = items.get("period_breakdown", {})
    yearly = period_breakdown.get("yearly", {})
    best = yearly.get("best", {})
    # 5 трейдов в одном году. NET sum = 2000, GROSS sum = 5000.
    assert best.get("pnl") == pytest.approx(2000, rel=0.01), (
        f"NET period_breakdown.yearly.best.pnl=2000 ожидался, "
        f"получено {best.get('pnl')} (похоже на GROSS=5000)"
    )


# ============================================================================
# ADR-0010 Task 4 — anchored broker account: headline / ROI / drawdown
# ============================================================================


def test_anchor_broker_account_stats(client_with_db):
    """ADR-0010 Task 4: anchored broker account shows correct headline/ROI/drawdown.

    Setup: initial_balance=99095 (anchor), one CapitalOperation deposit 8556,
    one OperationORM INPUT 8556, one closed futures trade pnl=-70754/net_pnl=-74713.
    last_portfolio_value=32938.

    Expected after edits:
      - cash_truth_pnl = last_portfolio_value - (raw_deposits + initial_balance)
                       = 32938 - (8556 + 99095) = 32938 - 107651 = -74713
      - period_start_balance_reliable = True
      - period_start_balance = account_initial_balance + starting_net_deposit
                             = 99095 + 8556 = 107651
      - total_roi is not None

    Equity-curve equality: same curve whether initial_balance=99095 or 0.
    (anchor only moves the % base, not the curve itself)
    """
    from decimal import Decimal as D
    from datetime import datetime

    db = client_with_db["db"]
    client = client_with_db["client"]

    from models import User, Account, Trade, TradeDirection, CapitalOperation, OperationORM
    import auth_service as _auth

    u = User(
        email="anchor-test@test.com",
        hashed_password=_auth.get_password_hash("pass1234"),
        is_active=1,
        is_admin=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    acc = Account(
        user_id=u.id,
        name="AnchorBroker",
        currency="RUB",
        initial_balance=D("99095"),
        initial_balance_source="inferred_anchor",
        last_portfolio_value=D("32938"),  # triggers is_broker_user = True
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    token = _auth.create_access_token({"sub": str(u.id)})

    # CapitalOperation deposit 8556 — используется get_net_deposit_as_of
    # (has_broker_capital_operations → True → queries CapitalOperation.operation_type=="deposit")
    cap_op = CapitalOperation(
        account_id=acc.id,
        date=datetime(2026, 1, 2),
        amount=D("8556"),
        operation_type="deposit",
    )
    db.add(cap_op)

    # OperationORM input 8556 — используется для raw_deposits в headline
    # operation_type должен совпадать с OperationType.INPUT.value = "input"
    op = OperationORM(
        account_id=acc.id,
        broker_account_id="test-broker-acc-1",
        operation_id="op-anchor-test-001",
        operation_type="input",
        state="executed",
        quantity=0,
        payment_units=8556,
        payment_nano=0,
        payment_currency="RUB",
        executed_at=datetime(2026, 1, 2, 10, 0),
    )
    db.add(op)

    # Closed futures trade: pnl=-70754, net_pnl=-74713
    trade = Trade(
        account_id=acc.id,
        symbol="RIM6",
        direction=TradeDirection.LONG,
        entry_price=D("200000"),
        exit_price=D("170000"),
        quantity=D("1"),
        entry_at=datetime(2026, 1, 3, 10, 0),
        exit_at=datetime(2026, 1, 3, 15, 0),
        currency="RUB",
        data_source="broker",
        position_id=99001,
        commission=D("3959"),
        pnl=D("-70754"),
        net_pnl=D("-74713"),
    )
    db.add(trade)
    db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    # --- Call with anchor ---
    resp1 = client.get("/stats/", headers=headers)
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()

    assert abs(body1["cash_truth_pnl"] - (-74713)) < 2, (
        f"cash_truth_pnl: {body1['cash_truth_pnl']}"
    )
    assert body1["period_start_balance_reliable"] is True, (
        f"reliable: {body1['period_start_balance_reliable']}"
    )
    assert abs(body1["period_start_balance"] - 107651) < 2, (
        f"period_start_balance: {body1['period_start_balance']}"
    )
    assert body1["total_roi"] is not None, (
        "total_roi must not be None for anchored account"
    )

    equity1 = body1.get("equity_curve", [])

    # --- Remove anchor (set initial_balance=0) and call again ---
    acc.initial_balance = D("0")
    db.commit()

    resp2 = client.get("/stats/", headers=headers)
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    equity2 = body2.get("equity_curve", [])

    # Equity curve MUST be equal — anchor moves only the % base, not the curve
    assert equity1 == equity2, (
        f"EQUITY CURVE SHIFTED by anchor change!\n"
        f"With anchor: {equity1}\n"
        f"Without anchor: {equity2}"
    )

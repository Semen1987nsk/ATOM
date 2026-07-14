"""MATH-09: пороги reconcile_journal_vs_cash должны совпадать с pnl_health_service (5/25%)."""
import os
import sys
from decimal import Decimal
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import Account, Base, OperationORM, Trade, TradeDirection, User


def test_reconcile_thresholds_match_pnl_health_service():
    from tools.reconcile_journal_vs_cash import THRESHOLD_OK_PCT, THRESHOLD_WARN_PCT
    from services.pnl_health_service import THRESHOLD_OK_PCT as HEALTH_OK
    from services.pnl_health_service import THRESHOLD_WARNING_PCT as HEALTH_WARN
    assert THRESHOLD_OK_PCT == HEALTH_OK == Decimal("5.0")
    assert THRESHOLD_WARN_PCT == HEALTH_WARN == Decimal("25.0")


@pytest.fixture
def mem_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


_op_counter = 0


def _make_op(session, acc_id, op_type, payment_units, executed_at):
    global _op_counter
    _op_counter += 1
    session.add(OperationORM(
        account_id=acc_id,
        broker_account_id="B1",
        operation_id=f"rec_op_{_op_counter}",
        operation_type=op_type,
        state="executed",
        payment_units=int(payment_units),
        payment_nano=0,
        executed_at=executed_at,
    ))


def _seed_anchor_account(session):
    """Seed: portfolio=32938, initial_balance=99095, net_deposit=8556, net_pnl=-74713."""
    global _op_counter
    _op_counter = 0
    u = User(email="rec_anchor@test.com", hashed_password="x", is_active=1)
    session.add(u)
    session.commit()

    acc = Account(
        user_id=u.id,
        name="AnchorAcc",
        currency="RUB",
        initial_balance=Decimal("99095"),
        last_portfolio_value=Decimal("32938"),
    )
    session.add(acc)
    session.commit()

    # One NET_DEPOSIT op of 8556.
    _make_op(session, acc.id, "input", 8556, datetime(2026, 6, 24))

    # Closed trade: net_pnl = -74713.
    session.add(Trade(
        account_id=acc.id,
        symbol="MXI",
        direction=TradeDirection.LONG,
        entry_price=Decimal("1"),
        quantity=Decimal("1"),
        instrument_type_v2="futures",
        entry_at=datetime(2026, 1, 5),
        exit_at=datetime(2026, 2, 5),
        pnl=Decimal("-70754"),
        net_pnl=Decimal("-74713"),
    ))
    session.commit()
    return acc


def _seed_zero_anchor_account(session):
    """Seed: portfolio=20000, initial_balance=0, net_deposit=25000, net_pnl=-5000."""
    global _op_counter
    u = User(email="rec_zero@test.com", hashed_password="x", is_active=1)
    session.add(u)
    session.commit()

    acc = Account(
        user_id=u.id,
        name="ZeroAnchorAcc",
        currency="RUB",
        initial_balance=Decimal("0"),
        last_portfolio_value=Decimal("20000"),
    )
    session.add(acc)
    session.commit()

    _make_op(session, acc.id, "input", 25000, datetime(2026, 1, 10))

    session.add(Trade(
        account_id=acc.id,
        symbol="SBER",
        direction=TradeDirection.LONG,
        entry_price=Decimal("300"),
        quantity=Decimal("10"),
        instrument_type_v2="share",
        entry_at=datetime(2026, 1, 11),
        exit_at=datetime(2026, 1, 20),
        pnl=Decimal("-5000"),
        net_pnl=Decimal("-5000"),
    ))
    session.commit()
    return acc


def test_reconcile_account_subtracts_initial_balance_anchor(mem_session):
    """ADR-0010: initial_balance должен вычитаться из cash_pnl в all-time режиме.

    Expected: cash_pnl = 32938 - 8556 - 99095 = -74713.
    Without the fix cash_pnl would be 32938 - 8556 = 24382.
    """
    from tools.reconcile_journal_vs_cash import reconcile_account

    acc = _seed_anchor_account(mem_session)
    result = reconcile_account(acc.id, session=mem_session)

    cash = result["cash"]
    assert abs(Decimal(str(cash["total"])) - Decimal("-74713")) < Decimal("1"), (
        f"Expected cash_pnl ~ -74713, got {cash['total']}"
    )
    assert "initial_balance" in cash, "cash dict must expose initial_balance (anchor)"
    assert abs(Decimal(str(cash["initial_balance"])) - Decimal("99095")) < Decimal("1")


def test_reconcile_account_zero_anchor_unchanged(mem_session):
    """initial_balance=0 must leave cash_pnl = portfolio - net_deposits."""
    from tools.reconcile_journal_vs_cash import reconcile_account

    acc = _seed_zero_anchor_account(mem_session)
    result = reconcile_account(acc.id, session=mem_session)

    cash = result["cash"]
    # 20000 - 25000 - 0 = -5000
    assert abs(Decimal(str(cash["total"])) - Decimal("-5000")) < Decimal("1"), (
        f"Expected cash_pnl ~ -5000, got {cash['total']}"
    )


def test_reconcile_account_baseline_mode_ignores_anchor(mem_session):
    """In baseline-date mode the anchor must NOT be applied (would double-count)."""
    from tools.reconcile_journal_vs_cash import reconcile_account

    acc = _seed_anchor_account(mem_session)
    # baseline_date with initial_portfolio_value=0 -> baseline_offset=0 -> cash_pnl = portfolio - deposits
    result = reconcile_account(
        acc.id,
        session=mem_session,
        baseline_date=datetime(2026, 1, 1),
        initial_portfolio_value=Decimal("0"),
    )
    cash = result["cash"]
    # 32938 - 8556 - baseline_offset(0) - anchor(0 in baseline mode) = 24382
    assert abs(Decimal(str(cash["total"])) - Decimal("24382")) < Decimal("1"), (
        f"Expected 24382 in baseline mode, got {cash['total']}"
    )

"""Integration: anchor service against seeded in-memory DB (ADR-0010).

Покрывает: incomplete-history+healthy-futures -> anchored; complete-history ->
no-anchor; pv*1000 -> blocked; freeze на re-sync; manual-priority.

Seed adjustments vs brief:
- OperationORM requires broker_account_id (NOT NULL) and operation_id (NOT NULL)
  -> added broker_account_id="B1" and unique operation_id per row.
- PositionORM requires instrument_type (NOT NULL) and avg_entry_price (NOT NULL)
  -> added instrument_type="futures", avg_entry_price=Decimal("0").
- Trade requires symbol (NOT NULL), direction (NOT NULL), entry_price (NOT NULL),
  quantity (NOT NULL) -> added symbol="MXI", direction=TradeDirection.LONG,
  entry_price=Decimal("1"), quantity=Decimal("1").
"""
import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import Account, Base, OperationORM, PositionORM, Trade, TradeDirection, User
from services.opening_anchor_service import autoset_inferred_anchor


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _money(units):
    return int(units), 0


def _account(session, *, portfolio):
    u = User(email="anchor@test.com", hashed_password="x", is_active=1)
    session.add(u)
    session.commit()
    acc = Account(user_id=u.id, name="Main", currency="RUB", initial_balance=Decimal("0"))
    acc.last_portfolio_value = Decimal(str(portfolio))
    session.add(acc)
    session.commit()
    return acc


_op_counter = 0


def _op(session, acc_id, op_type, payment_units, executed_at):
    global _op_counter
    _op_counter += 1
    units, nano = _money(payment_units)
    session.add(OperationORM(
        account_id=acc_id,
        broker_account_id="B1",
        operation_id=f"op_{_op_counter}",
        operation_type=op_type,
        state="executed",
        payment_units=units,
        payment_nano=nano,
        executed_at=executed_at,
    ))


def _seed_acc2(session, *, first_op_type="buy"):
    global _op_counter
    _op_counter = 0
    from datetime import datetime
    acc = _account(session, portfolio=32938)
    # Стартовая операция — НЕ депозит -> incomplete history.
    _op(session, acc.id, first_op_type, -93030, datetime(2026, 1, 5))
    # Депозиты позже (24-26 июня), нетто +8556 (упрощённо одной операцией).
    _op(session, acc.id, "input", 8556, datetime(2026, 6, 24))
    # Варм-маржа: нетто -86799 (accruing + writing_off).
    _op(session, acc.id, "accruing_varmargin", 10000, datetime(2026, 2, 1))
    _op(session, acc.id, "writing_off_varmargin", -96799, datetime(2026, 3, 1))
    # Закрытый фьючерсный трейд: body -70754, net -74713 (с учётом fee distribution).
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
    # Открытая фьючерсная позиция: осевшая ВМ -7920, unrealized 0 (для простоты).
    session.add(PositionORM(
        account_id=acc.id,
        instrument_uid="u-mxi",
        instrument_type="futures",
        avg_entry_price=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        var_margin_rub=Decimal("-7920"),
    ))
    session.commit()
    return acc


def test_incomplete_history_healthy_futures_anchors(session):
    acc = _seed_acc2(session)
    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "inferred_anchor"
    session.refresh(acc)
    assert abs(Decimal(str(acc.initial_balance)) - Decimal("99095")) < Decimal("1")
    assert acc.initial_balance_source == "inferred_anchor"


def test_complete_history_does_not_anchor(session):
    acc = _seed_acc2(session, first_op_type="input")  # первая op = депозит
    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "complete"
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("0")
    assert acc.initial_balance_source == "complete"


def test_pv_x1000_bug_is_blocked_not_hidden(session):
    acc = _seed_acc2(session)
    # Раздуваем body закрытого фьючерса в 1000x — телескоп-гейт обязан заблокировать.
    t = session.query(Trade).filter(Trade.account_id == acc.id).first()
    t.pnl = Decimal("-70754000")
    session.commit()
    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "inferred_blocked"
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("0")
    assert acc.initial_balance_source == "inferred_blocked"


def test_anchor_frozen_on_resync(session):
    acc = _seed_acc2(session)
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    first_value = Decimal(str(acc.initial_balance))
    # Меняется портфель (новый sync) — якорь НЕ должен пересчитаться.
    acc.last_portfolio_value = Decimal("50000")
    session.commit()
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == first_value


def test_manual_source_never_overwritten(session):
    acc = _seed_acc2(session)
    acc.initial_balance = Decimal("123456")
    acc.initial_balance_source = "manual"
    session.commit()
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("123456")
    assert acc.initial_balance_source == "manual"


def test_anchored_account_not_wiped_when_candidate_drops_below_min(session):
    """M1 (ADR-0010 §5): уже поставленный inferred_anchor НЕ обнуляется, если
    кандидат позже просел ≤ ANCHOR_MIN (убыточный счёт восстанавливается к
    безубытку). До фикса G1 возвращал source='complete' → service-заморозка
    (key: source != 'complete') пропускала запись → initial_balance перетирался в 0.
    Теперь G1 → 'inferred_skipped' → заморозка держится."""
    acc = _seed_acc2(session)
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert acc.initial_balance_source == "inferred_anchor"
    anchored_value = Decimal(str(acc.initial_balance))
    assert anchored_value > Decimal("0")

    # Журнал восстановился к безубытку (net_pnl закрытого трейда → +24400):
    # candidate = 32938 - 8556 - 24400 = -18 ≤ ANCHOR_MIN.
    t = session.query(Trade).filter(Trade.account_id == acc.id).first()
    t.net_pnl = Decimal("24400")
    session.commit()

    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "inferred_anchor"  # заморозка вернула текущий якорь
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == anchored_value
    assert acc.initial_balance_source == "inferred_anchor"

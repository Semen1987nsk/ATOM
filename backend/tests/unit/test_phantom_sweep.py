"""Tests для close_phantom_trades — закрытие open Trade rows без matching Position."""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from models import Base, TradeDirection
from application.sync.phantom_sweep import close_phantom_trades


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _make_open_trade(session, instrument_uid: str, qty: int = 10, entry: Decimal = Decimal("100")):
    trade = models.Trade(
        account_id=1, symbol="SYM-" + instrument_uid,
        instrument_uid=instrument_uid, instrument_figi="figi-" + instrument_uid,
        asset_type="futures",
        direction=TradeDirection.LONG, quantity=qty,
        entry_price=entry, exit_price=None,
        entry_at=datetime(2026, 5, 1, 10, 0), exit_at=None,
        pnl=None, net_pnl=None,
        commission=Decimal("5"),
        entry_value=entry * qty,
    )
    session.add(trade)
    return trade


def test_closes_open_trade_without_position(session):
    """Phantom: open Trade + Position table имеет ДРУГИЕ uids → sweep закрывает."""
    live = models.PositionORM(
        account_id=1, instrument_uid="real-uid", instrument_type="futures",
        quantity=5, avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("25"),
    )
    session.add(live)
    phantom = _make_open_trade(session, "phantom-uid", qty=10, entry=Decimal("100"))
    session.commit()

    now = datetime(2026, 5, 19, 14, 0)
    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=now,
    )

    assert count == 1
    session.refresh(phantom)
    assert phantom.exit_at == now
    assert phantom.exit_price == Decimal("100")  # no last_known, fallback на entry
    assert phantom.exit_reason == "phantom_sweep"
    assert "phantom_sweep" in (phantom.tags or [])


def test_no_sweep_when_position_exists(session):
    """Trade open + matching Position → НЕ sweep."""
    live = models.PositionORM(
        account_id=1, instrument_uid="uid-A", instrument_type="futures",
        quantity=10, avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("50"),
    )
    trade = _make_open_trade(session, "uid-A", qty=10, entry=Decimal("100"))
    session.add(live)
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 0
    session.refresh(trade)
    assert trade.exit_at is None
    assert trade.exit_reason is None


def test_uses_last_known_price_when_available(session):
    """Если для phantom uid в Position есть current_price (qty=0 closed) — используем его."""
    stale_pos = models.PositionORM(
        account_id=1, instrument_uid="closed-uid", instrument_type="futures",
        quantity=0,  # qty=0 — позиция закрыта
        avg_entry_price=Decimal("100"), current_price=Decimal("110"),
        unrealized_pnl=Decimal("0"),
    )
    other_live = models.PositionORM(
        account_id=1, instrument_uid="other-uid", instrument_type="futures",
        quantity=5, avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("25"),
    )
    phantom = _make_open_trade(session, "closed-uid", qty=10, entry=Decimal("100"))
    session.add_all([stale_pos, other_live])
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 1
    session.refresh(phantom)
    # last_known_price нашёл stale_pos.current_price = 110
    assert phantom.exit_price == Decimal("110")
    # body_pnl = (110 - 100) * 10 * 1 = 100
    # net_pnl = 100 - 5 commission = 95
    assert phantom.pnl == Decimal("100")
    assert phantom.net_pnl == Decimal("95")


def test_short_direction_inverts_body_pnl(session):
    """SHORT phantom → body_pnl = -(exit - entry) × qty × pv (зеркально LONG)."""
    other_live = models.PositionORM(
        account_id=1, instrument_uid="other", instrument_type="futures",
        quantity=1, avg_entry_price=Decimal("100"),
        current_price=Decimal("100"), unrealized_pnl=Decimal("0"),
    )
    phantom = models.Trade(
        account_id=1, symbol="SHORT-SYM",
        instrument_uid="short-uid", instrument_figi="figi-short",
        asset_type="futures",
        direction=TradeDirection.SHORT, quantity=10,
        entry_price=Decimal("100"), exit_price=None,
        entry_at=datetime(2026, 5, 1), exit_at=None,
        pnl=None, net_pnl=None,
        commission=Decimal("0"),
        entry_value=Decimal("1000"),
    )
    session.add_all([other_live, phantom])
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 1
    session.refresh(phantom)
    # exit = entry (fallback) = 100, body = -(100-100)*10*1 = 0
    assert phantom.pnl == Decimal("0")


def test_skip_sweep_when_no_positions_but_recent_ops(session):
    """Tinkoff blip: Position table пуста, но в Operations есть recent ops → skip."""
    now = datetime(2026, 5, 19, 14, 0)
    op = models.OperationORM(
        operation_id="op-recent", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-1000, payment_nano=0,
        executed_at=now,  # recent
    )
    phantom = _make_open_trade(session, "blip-uid")
    session.add(op)
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=now,
    )
    assert count == 0
    session.refresh(phantom)
    assert phantom.exit_at is None  # NOT swept


def test_idempotent_already_closed_trade_untouched(session):
    """Идемпотентность: повторный запуск не трогает уже закрытые Trade."""
    other_live = models.PositionORM(
        account_id=1, instrument_uid="other", instrument_type="futures",
        quantity=1, avg_entry_price=Decimal("100"),
        current_price=Decimal("100"), unrealized_pnl=Decimal("0"),
    )
    already_closed = models.Trade(
        account_id=1, symbol="CLOSED-SYM",
        instrument_uid="closed-trade", instrument_figi="figi-x",
        asset_type="futures",
        direction=TradeDirection.LONG, quantity=5,
        entry_price=Decimal("100"), exit_price=Decimal("105"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 10),
        pnl=Decimal("25"), net_pnl=Decimal("20"),
        commission=Decimal("5"),
        entry_value=Decimal("500"),
    )
    session.add_all([other_live, already_closed])
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 0
    session.refresh(already_closed)
    assert already_closed.exit_at == datetime(2026, 5, 10)  # unchanged
    assert already_closed.exit_price == Decimal("105")

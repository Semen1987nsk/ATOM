"""Phase 10 (2026-05-17): unit tests для P&L Health Check сервиса."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from services import pnl_health_service
from services.pnl_health_service import (
    STALE_AFTER_DAYS,
    THRESHOLD_OK_PCT,
    THRESHOLD_WARNING_PCT,
    _status_from_diff_pct,
    is_stale,
)


# ── Status threshold tests ────────────────────────────────────────────


def test_status_ok_below_five_percent():
    assert _status_from_diff_pct(Decimal("0.0"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("4.99"), Decimal("100000")) == "ok"


def test_status_warning_between_five_and_twentyfive():
    assert _status_from_diff_pct(Decimal("5.0"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("24.99"), Decimal("100000")) == "warning"


def test_status_investigate_above_twentyfive_percent():
    assert _status_from_diff_pct(Decimal("25.0"), Decimal("100000")) == "investigate"
    assert _status_from_diff_pct(Decimal("100.0"), Decimal("100000")) == "investigate"


def test_status_na_when_cash_truth_is_zero():
    """Если |cash_pnl| < 1 ₽ — статус 'na' независимо от diff_pct."""
    assert _status_from_diff_pct(Decimal("99.0"), Decimal("0")) == "na"
    assert _status_from_diff_pct(Decimal("0.0"), Decimal("0.5")) == "na"
    assert _status_from_diff_pct(Decimal("50.0"), Decimal("0.99")) == "na"


def test_status_negative_diff_uses_absolute():
    assert _status_from_diff_pct(Decimal("-4.0"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("-10.0"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("-30.0"), Decimal("100000")) == "investigate"


# ── is_stale tests ────────────────────────────────────────────────────


def test_is_stale_when_at_is_none():
    acc = models.Account(id=1, name="test", last_pnl_health_at=None)
    assert is_stale(acc) is True


def test_is_stale_after_threshold_days():
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    acc = models.Account(
        id=1, name="test",
        last_pnl_health_at=now - timedelta(days=STALE_AFTER_DAYS + 1),
    )
    assert is_stale(acc, now=now) is True


def test_is_stale_recent_check_not_stale():
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    acc = models.Account(
        id=1, name="test",
        last_pnl_health_at=now - timedelta(hours=1),
    )
    assert is_stale(acc, now=now) is False


# ── PnLHealthResult / persistence tests ───────────────────────────────


@pytest.fixture
def in_memory_session():
    """Изолированная in-memory SQLite session с применённой схемой."""
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_compute_health_missing_account_returns_na(in_memory_session):
    """compute_health() для несуществующего account → status='na'."""
    result = pnl_health_service.compute_health(in_memory_session, account_id=999)
    assert result.status == "na"
    assert result.journal_pnl == Decimal(0)
    assert result.cash_pnl == Decimal(0)


def test_compute_health_zero_state_account(in_memory_session):
    """Account с last_portfolio_value=0, без trades → cash_pnl=0 → status='na'."""
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="empty", last_portfolio_value=Decimal(0))
    in_memory_session.add(user)
    in_memory_session.add(acc)
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert result.status == "na"
    assert result.cash_pnl == Decimal(0)
    assert result.duration_ms >= 0


def test_persist_health_updates_account_fields(in_memory_session):
    """persist_health() заполняет все last_pnl_health_* колонки."""
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="test", last_portfolio_value=Decimal(0))
    in_memory_session.add(user)
    in_memory_session.add(acc)
    in_memory_session.commit()

    result = pnl_health_service.compute_and_persist(in_memory_session, account_id=1)

    # Re-fetch
    in_memory_session.expire_all()
    acc_after = in_memory_session.get(models.Account, 1)
    assert acc_after.last_pnl_health_at is not None
    assert acc_after.last_pnl_health_status == result.status
    assert acc_after.last_pnl_health_diff_pct is not None
    assert acc_after.last_pnl_health_diff_rub is not None
    assert acc_after.last_pnl_health_breakdown is not None
    assert "journal_pnl" in acc_after.last_pnl_health_breakdown


def test_to_breakdown_json_contains_all_fields():
    """to_breakdown_json() возвращает все ожидаемые ключи для UI."""
    result = pnl_health_service.PnLHealthResult(
        account_id=1,
        journal_pnl=Decimal("-100"),
        cash_pnl=Decimal("-101"),
        diff_rub=Decimal("1"),
        diff_pct=Decimal("0.99"),
        status="ok",
        components={"closed": Decimal("-50"), "unrealized": Decimal("-51")},
        computed_at=datetime(2026, 5, 17, 12, 0),
        duration_ms=42,
    )
    data = result.to_breakdown_json()
    assert data["status"] == "ok"
    assert data["journal_pnl"] == -100.0
    assert data["cash_pnl"] == -101.0
    assert data["diff_rub"] == 1.0
    assert data["diff_pct"] == 0.99
    assert "components" in data
    assert data["components"]["closed"] == -50.0
    assert data["duration_ms"] == 42


def test_threshold_constants_match_spec():
    """ADR-0008: пороги слоя 3 (клиринг-band) = ADR-0007 (5/25)."""
    assert THRESHOLD_OK_PCT == Decimal("5.0")
    assert THRESHOLD_WARNING_PCT == Decimal("25.0")


# ── Phase 6.3 (2026-05-18): cash-anchored health check ────────────────


def test_journal_proxy_is_realized_plus_unrealized_only(in_memory_session):
    """Phase 6.3: journal_pnl proxy = Σ Trade.net_pnl(closed) + Σ Position.unrealized_pnl.
    БЕЗ account_level_adjustments — это и есть «как считает Дневник сделок».
    Health check сравнивает per-trade tracking sum против broker cash truth."""
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(
        id=1, user_id=1, name="profitable",
        last_portfolio_value=Decimal("105000"),
    )
    in_memory_session.add(user)
    in_memory_session.add(acc)

    # Insert one closed trade net_pnl=+3000 and one open position unrealized=+2000.
    closed = models.Trade(
        account_id=1, symbol="LKOH", direction="LONG",
        entry_price=100, exit_price=103, quantity=1000,
        pnl=Decimal("3000"), net_pnl=Decimal("2900"), commission=Decimal("100"),
        entry_at=datetime(2026, 5, 1, 10, 0),
        exit_at=datetime(2026, 5, 10, 16, 0),
    )
    open_pos = models.PositionORM(
        account_id=1, instrument_uid="uid-1", instrument_type="share",
        quantity=10, avg_entry_price=Decimal("200"),
        unrealized_pnl=Decimal("2000"),
    )
    # NET_DEPOSIT operation +100,000
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="input",
        state="executed", payment_units=100000, payment_nano=0,
        executed_at=datetime(2026, 4, 1),
    )
    # Non-deposit ops so layer-1 cash reconstruction sees full history.
    # buy LKOH -100_000, sell LKOH +103_000, accruing_varmargin +2_000 → non_dep=5_000
    op_buy = models.OperationORM(
        operation_id="op-buy-lkoh", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-100000, payment_nano=0, executed_at=datetime(2026, 5, 1),
    )
    op_sell = models.OperationORM(
        operation_id="op-sell-lkoh", account_id=1, broker_account_id="ba-1",
        operation_type="sell", state="executed",
        payment_units=103000, payment_nano=0, executed_at=datetime(2026, 5, 10),
    )
    op_vm = models.OperationORM(
        operation_id="op-vm-1", account_id=1, broker_account_id="ba-1",
        operation_type="accruing_varmargin", state="executed",
        payment_units=2000, payment_nano=0, executed_at=datetime(2026, 5, 11),
    )
    in_memory_session.add(closed)
    in_memory_session.add(open_pos)
    in_memory_session.add(op)
    in_memory_session.add(op_buy)
    in_memory_session.add(op_sell)
    in_memory_session.add(op_vm)
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, account_id=1)

    # journal_pnl = closed.net_pnl + open.unrealized_pnl = 2900 + 2000 = 4900
    assert result.journal_pnl == Decimal("4900")
    # cash_pnl = portfolio 105_000 − deposits 100_000 = 5_000
    assert result.cash_pnl == Decimal("5000")
    # diff = -100 (journal undershoots cash by 100), residual_pct = 2% → mismatch
    assert result.diff_rub == Decimal("-100")
    assert abs(result.diff_pct - Decimal("2.0")) < Decimal("0.01")
    assert result.status == "ok"   # ADR-0008: 2% within 5% OK band


def test_health_status_ok_when_small_residual(in_memory_session):
    """С small natural_residual (<0.5% от cash_truth) status='ok'."""
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(
        id=1, user_id=1, name="ok-attribution",
        last_portfolio_value=Decimal("100000"),
    )
    in_memory_session.add(user)
    in_memory_session.add(acc)

    closed = models.Trade(
        account_id=1, symbol="GAZP", direction="LONG",
        entry_price=100, exit_price=110, quantity=99,
        pnl=Decimal("990"), net_pnl=Decimal("990"),
        commission=Decimal("0"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 2),
    )
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="input",
        state="executed", payment_units=99000, payment_nano=0,
        executed_at=datetime(2026, 4, 1),
    )
    # Non-deposit ops so layer-1 cash reconstruction sees full history.
    # buy GAZP -9_900, sell GAZP +10_890 → non_dep=990, residual=10 ≤ 100₽ tolerance
    op_buy = models.OperationORM(
        operation_id="op-buy-gazp", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-9900, payment_nano=0, executed_at=datetime(2026, 5, 1),
    )
    op_sell = models.OperationORM(
        operation_id="op-sell-gazp", account_id=1, broker_account_id="ba-1",
        operation_type="sell", state="executed",
        payment_units=10890, payment_nano=0, executed_at=datetime(2026, 5, 2),
    )
    in_memory_session.add(closed)
    in_memory_session.add(op)
    in_memory_session.add(op_buy)
    in_memory_session.add(op_sell)
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    # cash_truth = 100_000 - 99_000 = 1_000
    # journal = 990 (closed only, no open positions)
    # residual = 10₽ = 1% от cash_truth → warning
    assert result.cash_pnl == Decimal("1000")
    assert result.journal_pnl == Decimal("990")
    assert result.status == "ok"   # ADR-0008: 1% < 5% OK band
    assert abs(result.diff_pct - Decimal("1.0")) < Decimal("0.01")


def test_health_includes_layer_components(in_memory_session):
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("105000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    closed = models.Trade(
        account_id=1, symbol="LKOH", direction="LONG",
        entry_price=100, exit_price=103, quantity=1000,
        pnl=Decimal("3000"), net_pnl=Decimal("2900"), commission=Decimal("100"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 10),
    )
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1),
    )
    in_memory_session.add(closed); in_memory_session.add(op)
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert "clearing_adjustment" in result.components
    assert "layers" in result.components
    layers = result.components["layers"]
    assert "ratio_sanity" in layers and "cash_reconstruction" in layers
    assert "trade_outliers" in layers


def test_health_flags_unknown_op_with_cash(in_memory_session):
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("100000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    in_memory_session.add(models.OperationORM(
        operation_id="op-d", account_id=1, broker_account_id="ba",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1)))
    in_memory_session.add(models.OperationORM(
        operation_id="op-x", account_id=1, broker_account_id="ba",
        operation_type="totally_new_2099", state="executed",
        payment_units=-500, payment_nano=0, executed_at=datetime(2026, 4, 2)))
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert result.components["layers"]["unknown_types"] in ("warning", "red")
    assert "totally_new_2099" in str(result.components.get("unknown_types_detail", ""))


def test_health_surfaces_last_reconciliation(in_memory_session):
    import json
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("100000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    in_memory_session.add(models.OperationORM(
        operation_id="op", account_id=1, broker_account_id="ba",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1)))
    in_memory_session.add(models.ReconciliationRunORM(
        account_id=1, user_id=1, status="break", breaks_count=1,
        period_start=datetime(2026, 1, 1), period_end=datetime(2026, 5, 20),
        started_at=datetime(2026, 5, 20), finished_at=datetime(2026, 5, 20),
        metrics=json.dumps({"trade_count": {"ours": "5", "broker": "6", "status": "hard"}})))
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert result.components["layers"]["three_way_recon"] in ("break", "warning", "ok")


def test_health_clearing_adjustment_closes_identity_to_cash(in_memory_session):
    """clearing_adjustment must satisfy: closed + unrealized + clearing_adjustment == cash_pnl."""
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("105000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    closed = models.Trade(
        account_id=1, symbol="LKOH", direction="LONG",
        entry_price=100, exit_price=103, quantity=1000,
        pnl=Decimal("3000"), net_pnl=Decimal("2900"), commission=Decimal("100"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 10),
    )
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1),
    )
    in_memory_session.add(closed); in_memory_session.add(op)
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    ca = Decimal(str(result.components["clearing_adjustment"]))
    # identity: journal (closed+unrealized) + clearing_adjustment == cash
    assert abs(result.journal_pnl + ca - result.cash_pnl) < Decimal("0.01")
    # sign: clearing_adjustment == cash - journal
    assert abs(ca - (result.cash_pnl - result.journal_pnl)) < Decimal("0.01")


# ── ADR-0010: effective deposits (anchor) tests ────────────────────────


def test_anchor_corrects_cash_pnl_and_badge(in_memory_session):
    """ADR-0010: с initial_balance(anchor) cash_pnl = portfolio − net_dep − anchor,
    badge diff_pct схлопывается (без якоря cash_pnl=24382, diff_pct=406%; с якорём ~0)."""
    u = models.User(email="h@test.com", hashed_password="x", is_active=1)
    in_memory_session.add(u)
    in_memory_session.commit()
    acc = models.Account(
        user_id=u.id, name="M", currency="RUB",
        initial_balance=Decimal("99095"),
        initial_balance_source="inferred_anchor",
        last_portfolio_value=Decimal("32938"),
    )
    in_memory_session.add(acc)
    in_memory_session.commit()
    in_memory_session.add(models.OperationORM(
        operation_id="op-anchor-deposit",
        account_id=acc.id,
        broker_account_id="ba-anchor",
        operation_type="input",
        state="executed",
        payment_units=8556,
        payment_nano=0,
        executed_at=datetime(2026, 2, 1),
    ))
    in_memory_session.add(models.Trade(
        account_id=acc.id,
        symbol="MXI",
        instrument_type_v2="futures",
        direction="LONG",
        entry_price=Decimal("32000"),
        exit_price=Decimal("31000"),
        quantity=1,
        pnl=Decimal("-70754"),
        net_pnl=Decimal("-74713"),
        commission=Decimal("3959"),
        entry_at=datetime(2026, 1, 10),
        exit_at=datetime(2026, 2, 5),
    ))
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, acc.id)
    # cash_pnl = 32938 − 8556 − 99095 = −74713 → equals journal → diff ~0.
    assert abs(result.cash_pnl - Decimal("-74713")) < Decimal("1")
    assert result.diff_pct < Decimal("25")


def test_layer4_outlier_uses_effective_deposits_not_raw(in_memory_session):
    """ADR-0010: layer4 trade_outliers base = effective_deposits (net_deposits + anchor).
    A trade whose |net_pnl| > 0.5*net_deposits but < 0.5*effective_deposits must NOT be flagged.
    Shape: net_deposits=10000, initial_balance=90000 (effective=100000),
           closed trade net_pnl=-30000 (>0.5*10000=5000 but <0.5*100000=50000) → NOT outlier."""
    u = models.User(email="layer4@test.com", hashed_password="x", is_active=1)
    in_memory_session.add(u)
    in_memory_session.commit()
    acc = models.Account(
        user_id=u.id, name="layer4-anchor", currency="RUB",
        initial_balance=Decimal("90000"),
        initial_balance_source="inferred_anchor",
        last_portfolio_value=Decimal("70000"),
    )
    in_memory_session.add(acc)
    in_memory_session.commit()
    # net_deposits = 10000 via one input operation
    in_memory_session.add(models.OperationORM(
        operation_id="op-layer4-dep",
        account_id=acc.id,
        broker_account_id="ba-layer4",
        operation_type="input",
        state="executed",
        payment_units=10000,
        payment_nano=0,
        executed_at=datetime(2026, 3, 1),
    ))
    # closed trade net_pnl=-30000: |−30000| > 0.5*10000=5000 (raw → outlier)
    #                               but |−30000| < 0.5*100000=50000 (effective → NOT outlier)
    in_memory_session.add(models.Trade(
        account_id=acc.id,
        symbol="FUTURES_XYZ",
        direction="LONG",
        entry_price=Decimal("100"),
        exit_price=Decimal("70"),
        quantity=1,
        pnl=Decimal("-30000"),
        net_pnl=Decimal("-30000"),
        commission=Decimal("0"),
        entry_at=datetime(2026, 3, 2),
        exit_at=datetime(2026, 3, 10),
    ))
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, acc.id)
    outlier_symbols = result.components.get("outlier_symbols", [])
    assert "FUTURES_XYZ" not in outlier_symbols, (
        f"Layer4 used raw net_deposits instead of effective_deposits; "
        f"outlier_symbols={outlier_symbols}"
    )

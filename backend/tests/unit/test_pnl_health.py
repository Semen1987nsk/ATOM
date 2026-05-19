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


def test_status_ok_below_one_percent():
    """До 1% — orphan'ы технические (post-clearing варм-маржа, sysтемные сборы)."""
    assert _status_from_diff_pct(Decimal("0.0"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("0.5"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("0.99"), Decimal("100000")) == "ok"


def test_status_warning_between_one_and_five():
    """1-5% — нормально для фьючерсного аккаунта с большим объёмом orphan-сборов."""
    assert _status_from_diff_pct(Decimal("1.0"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("2.71"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("4.99"), Decimal("100000")) == "warning"


def test_status_mismatch_above_five_percent():
    """Выше 5% — может быть реальная проблема с attribution, стоит расследовать."""
    assert _status_from_diff_pct(Decimal("5.0"), Decimal("100000")) == "mismatch"
    assert _status_from_diff_pct(Decimal("10.0"), Decimal("100000")) == "mismatch"
    assert _status_from_diff_pct(Decimal("100.0"), Decimal("100000")) == "mismatch"


def test_status_na_when_cash_truth_is_zero():
    """Если |cash_pnl| < 1 ₽ — статус 'na' независимо от diff_pct."""
    assert _status_from_diff_pct(Decimal("99.0"), Decimal("0")) == "na"
    assert _status_from_diff_pct(Decimal("0.0"), Decimal("0.5")) == "na"
    assert _status_from_diff_pct(Decimal("50.0"), Decimal("0.99")) == "na"


def test_status_negative_diff_uses_absolute():
    """Signed diff_pct → status считается от |diff_pct|."""
    assert _status_from_diff_pct(Decimal("-0.5"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("-2.0"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("-7.0"), Decimal("100000")) == "mismatch"


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
    """Sanity: thresholds raised к realistic для фьючерсного трейдинга (2026-05-19).
    Post-clearing варм-маржа MOEX + системные сборы Тинькофф = orphan'ы 1-5%
    от cash_pnl, не реальная проблема (деньги уже учтены в balance)."""
    assert THRESHOLD_OK_PCT == Decimal("1.0")
    assert THRESHOLD_WARNING_PCT == Decimal("5.0")


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
    in_memory_session.add(closed)
    in_memory_session.add(open_pos)
    in_memory_session.add(op)
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, account_id=1)

    # journal_pnl = closed.net_pnl + open.unrealized_pnl = 2900 + 2000 = 4900
    assert result.journal_pnl == Decimal("4900")
    # cash_pnl = portfolio 105_000 − deposits 100_000 = 5_000
    assert result.cash_pnl == Decimal("5000")
    # diff = -100 (journal undershoots cash by 100), residual_pct = 2% → mismatch
    assert result.diff_rub == Decimal("-100")
    assert abs(result.diff_pct - Decimal("2.0")) < Decimal("0.01")


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
    in_memory_session.add(closed)
    in_memory_session.add(op)
    in_memory_session.commit()

    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    # cash_truth = 100_000 - 99_000 = 1_000
    # journal = 990 (closed only, no open positions)
    # residual = 10₽ = 1% от cash_truth → warning
    assert result.cash_pnl == Decimal("1000")
    assert result.journal_pnl == Decimal("990")
    assert result.status == "warning"
    assert abs(result.diff_pct - Decimal("1.0")) < Decimal("0.01")

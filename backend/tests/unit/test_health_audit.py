"""
Unit-тесты SyncHealthAuditor (PR 20).

Стратегия: используем in-memory SQLite через testcontainers-style fixture
(SessionLocal с :memory: SQLite). На неё заливаем синтетические Trade'ы,
Instrument'ы, OperationORM, и проверяем что каждая check_id ловит свой
кейс. Голова тестов — фабрики «битых» записей.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.sync.health_audit import (
    SEVERITY_ERROR,
    SEVERITY_OK,
    SEVERITY_WARNING,
    SyncHealthAuditor,
)
from models import (
    Account,
    Base,
    BrokerConnection,
    BrokerType,
    InstrumentORM,
    OperationORM,
    Trade,
    TradeDirection,
    User,
)
from utils.datetime_utils import utc_now_naive


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def session():
    """Изолированная in-memory SQLite БД на каждый тест."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    # Минимальный user + account + broker_connection.
    user = User(email="t@t.t", hashed_password="x", is_active=True, is_admin=False)
    s.add(user)
    s.flush()
    acc = Account(user_id=user.id, name="Main")
    s.add(acc)
    s.flush()
    conn = BrokerConnection(
        account_id=acc.id,
        broker=BrokerType.TINKOFF,
        api_token="encrypted",
        broker_account_id="2135909232",
        is_active=True,
        consecutive_failures=0,
    )
    s.add(conn)
    s.flush()
    yield s
    s.close()
    engine.dispose()


def _add_instrument(session, uid: str, ticker: str, name: str = "Test Co") -> None:
    session.add(
        InstrumentORM(
            uid=uid,
            ticker=ticker,
            figi="BBG-" + uid[:8],
            name=name,
            instrument_type="share",
            lot=1,
            currency="rub",
        )
    )


def _add_trade(
    session,
    account_id: int,
    *,
    symbol: str = "SBER",
    instrument_uid: str = "uid-sber",
    direction: TradeDirection = TradeDirection.LONG,
    entry_price: Decimal = Decimal("100"),
    exit_price: Decimal | None = Decimal("110"),
    quantity: Decimal = Decimal("10"),
    entry_at: datetime | None = None,
    exit_at: datetime | None = None,
    pnl: Decimal | None = Decimal("100"),
    entry_value: Decimal | None = Decimal("1000"),
    exit_value: Decimal | None = Decimal("1100"),
    asset_name: str | None = "Test Co",
    holding_time_minutes: int | None = 60,
    currency: str = "rub",
    instrument_type_v2: str = "share",
    data_source: str = "tinkoff_v2",
    operations: list | None = None,
) -> Trade:
    if entry_at is None:
        entry_at = datetime(2026, 5, 13, 10, 0)
    if exit_at is None and exit_price is not None:
        exit_at = datetime(2026, 5, 13, 11, 0)
    t = Trade(
        account_id=account_id,
        symbol=symbol,
        instrument_uid=instrument_uid,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_at=entry_at,
        exit_at=exit_at,
        pnl=pnl,
        entry_value=entry_value,
        exit_value=exit_value,
        asset_name=asset_name,
        holding_time_minutes=holding_time_minutes,
        currency=currency,
        instrument_type_v2=instrument_type_v2,
        data_source=data_source,
        operations=operations or [],
    )
    session.add(t)
    session.flush()
    return t


# ── tests ────────────────────────────────────────────────────────────


class TestCleanAccount:
    def test_empty_account_is_ok(self, session) -> None:
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        assert report.status == SEVERITY_OK
        assert report.total_trades_checked == 0
        assert report.issues == []

    def test_clean_trade_no_issues(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER", "Сбер")
        _add_trade(session, account_id=1)
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        assert report.status == SEVERITY_OK
        assert report.trades_with_issues == 0
        assert report.total_trades_checked == 1


class TestStructureChecks:
    def test_missing_asset_name_warning(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        _add_trade(session, account_id=1, asset_name=None)
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "missing_asset_name" in ids
        assert report.status == SEVERITY_WARNING

    def test_missing_entry_value_error(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        _add_trade(session, account_id=1, entry_value=None)
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "missing_entry_value" in ids
        assert report.status == SEVERITY_ERROR

    def test_ticker_mismatch_error(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER", "Сбер")
        # Symbol = "WRONG" не совпадает с Instrument.ticker = "SBER".
        _add_trade(session, account_id=1, symbol="WRONG")
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "ticker_mismatch" in ids


class TestConsistencyChecks:
    def test_pnl_sign_diverges_for_share(self, session) -> None:
        """LONG share с pnl=+100, но exit_value < entry_value → диверж."""
        _add_instrument(session, "uid-sber", "SBER")
        _add_trade(
            session,
            account_id=1,
            direction=TradeDirection.LONG,
            entry_value=Decimal("1000"),
            exit_value=Decimal("900"),  # exit меньше — должен быть loss
            pnl=Decimal("100"),  # но pnl положительный → диверж
            instrument_type_v2="share",
        )
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "pnl_sign_diverges_from_payments" in ids

    def test_pnl_pct_anomaly_warning(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        _add_trade(
            session,
            account_id=1,
            entry_value=Decimal("1000"),
            exit_value=Decimal("11000"),
            pnl=Decimal("10000"),  # 1000% — аномалия
            instrument_type_v2="share",
        )
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "pnl_pct_anomaly" in ids

    def test_pnl_sign_not_checked_for_futures(self, session) -> None:
        """У фьючерсов варм-маржа добавляется к pnl, поэтому формула
        sign(pnl) ?= sign(exit-entry) не должна применяться."""
        _add_instrument(session, "uid-fut", "ETH6")
        _add_trade(
            session,
            account_id=1,
            symbol="ETH6",
            instrument_uid="uid-fut",
            entry_value=Decimal("100000"),
            exit_value=Decimal("90000"),  # loss по price
            pnl=Decimal("50000"),  # но profit из-за варм-маржи
            instrument_type_v2="futures",
        )
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        # У фьючерсов ОК даже когда (exit-entry) и pnl разных знаков.
        assert "pnl_sign_diverges_from_payments" not in ids

    def test_weird_currency_warning(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        _add_trade(session, account_id=1, currency="XYZ")
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "weird_currency" in ids

    def test_entry_after_exit_error(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        _add_trade(
            session,
            account_id=1,
            entry_at=datetime(2026, 5, 13, 12, 0),
            exit_at=datetime(2026, 5, 13, 10, 0),  # exit РАНЬШЕ entry
        )
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "entry_after_exit" in ids


class TestBrokerStateChecks:
    def test_circuit_open_long_triggers(self, session) -> None:
        conn = session.query(BrokerConnection).first()
        conn.circuit_open_until = utc_now_naive() + timedelta(hours=5)
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=conn.account_id, broker_account_id=conn.broker_account_id
        )
        ids = {i.check_id for i in report.issues}
        assert "circuit_open_long" in ids

    def test_circuit_short_does_not_trigger(self, session) -> None:
        conn = session.query(BrokerConnection).first()
        # Меньше 2h — не error.
        conn.circuit_open_until = utc_now_naive() + timedelta(minutes=30)
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=conn.account_id, broker_account_id=conn.broker_account_id
        )
        ids = {i.check_id for i in report.issues}
        assert "circuit_open_long" not in ids

    def test_consecutive_failures_high_warning(self, session) -> None:
        conn = session.query(BrokerConnection).first()
        conn.consecutive_failures = 5
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=conn.account_id, broker_account_id=conn.broker_account_id
        )
        ids = {i.check_id for i in report.issues}
        assert "consecutive_failures_high" in ids


class TestPositionMismatchChecks:
    def test_position_diff_detected(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        from models import PositionORM
        session.add(
            PositionORM(
                account_id=1,
                instrument_uid="uid-sber",
                instrument_type="share",
                quantity=10,
                avg_entry_price=Decimal("100"),
                current_price=Decimal("110"),
                unrealized_pnl=Decimal("100"),
                currency="rub",
                last_priced_at=utc_now_naive(),
            )
        )
        session.commit()
        auditor = SyncHealthAuditor()
        # У Тинькова другая позиция (uid-other).
        report = auditor.audit_account(
            session,
            account_id=1,
            broker_account_id="2135909232",
            live_position_uids={"uid-other"},
        )
        ids = {i.check_id for i in report.issues}
        assert "position_count_mismatch_with_tinkoff" in ids

    def test_position_match_no_issue(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        from models import PositionORM
        session.add(
            PositionORM(
                account_id=1,
                instrument_uid="uid-sber",
                instrument_type="share",
                quantity=10,
                avg_entry_price=Decimal("100"),
                currency="rub",
                last_priced_at=utc_now_naive(),
            )
        )
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session,
            account_id=1,
            broker_account_id="2135909232",
            live_position_uids={"uid-sber"},
        )
        ids = {i.check_id for i in report.issues}
        assert "position_count_mismatch_with_tinkoff" not in ids


class TestCanceledOpsCheck:
    def test_canceled_op_attached_to_trade_error(self, session) -> None:
        """Если canceled op попала в Trade.operations — это ERROR."""
        _add_instrument(session, "uid-sber", "SBER")
        # Добавим canceled-операцию.
        session.add(
            OperationORM(
                account_id=1,
                broker_account_id="2135909232",
                operation_id="op-cancel-1",
                instrument_uid="uid-sber",
                operation_type="buy",
                state="canceled",
                quantity=10,
                executed_at=datetime(2026, 5, 13, 9, 0),
            )
        )
        # И Trade со ссылкой на эту op.
        _add_trade(
            session,
            account_id=1,
            operations=[
                {"role": "entry", "operation_id": "op-cancel-1"},
                {"role": "exit", "operation_id": "op-normal"},
            ],
        )
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        ids = {i.check_id for i in report.issues}
        assert "canceled_ops_in_fifo" in ids
        assert report.status == SEVERITY_ERROR


class TestHealthReportProperties:
    def test_main_issue_picks_error_over_warning(self, session) -> None:
        _add_instrument(session, "uid-sber", "SBER")
        # asset_name=None → warning, ticker mismatch → error
        _add_trade(session, account_id=1, asset_name=None, symbol="WRONG")
        session.commit()
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        # Главная — error.
        assert report.status == SEVERITY_ERROR
        assert report.main_issue == "ticker_mismatch"

    def test_to_db_fields_has_required_keys(self, session) -> None:
        auditor = SyncHealthAuditor()
        report = auditor.audit_account(
            session, account_id=1, broker_account_id="2135909232"
        )
        fields = report.to_db_fields()
        for k in (
            "account_id",
            "broker_account_id",
            "sync_id",
            "checked_at",
            "status",
            "total_trades_checked",
            "trades_with_issues",
            "issues_json",
        ):
            assert k in fields

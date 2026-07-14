"""
Unit-тесты для PR 22 — portfolio snapshot + compute_balance_at.

Заменяет PR 21 `test_initial_balance_autoset.py`. Старая логика
(`_autoset_initial_balance_if_needed`) имела системный баг: не учитывала
INPUT/OUTPUT операции и поэтому стартовый капитал получался завышенным
на сумму всех депозитов за период sync.

Новая модель:
- `Account.last_portfolio_value` обновляется при каждом sync
  (`pipeline._save_portfolio_snapshot`).
- `capital_service.compute_balance_at(date)` реконструирует баланс на
  любую дату назад как `last_portfolio_value − Σ payments(date > as_of)`.
- `routers/stats.py` использует это для broker-юзеров вместо
  `account.initial_balance`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.sync.pipeline import SyncPipeline
from capital_service import compute_balance_at
from models import Account, Base, OperationORM, User


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def user_account(session_factory):
    s = session_factory()
    u = User(email="u@u.u", hashed_password="x", is_active=True)
    s.add(u)
    s.flush()
    a = Account(user_id=u.id, name="Main", initial_balance=None)
    s.add(a)
    s.flush()
    s.commit()
    aid = a.id
    s.close()
    return aid


def _add_op(
    session,
    account_id: int,
    op_type: str,
    payment_units: int,
    *,
    payment_nano: int = 0,
    when: datetime | None = None,
):
    session.add(
        OperationORM(
            account_id=account_id,
            broker_account_id="2135909232",
            operation_id=f"op-{op_type}-{payment_units}-{when}",
            operation_type=op_type,
            state="executed",
            quantity=0,
            payment_units=payment_units,
            payment_nano=payment_nano,
            executed_at=when or datetime(2026, 5, 13, 10, 0),
        )
    )


def _make_pipeline(session_factory, account_id: int) -> SyncPipeline:
    return SyncPipeline(
        account_id=account_id,
        broker_account_id="2135909232",
        token_plaintext="dummy",
        session_factory=session_factory,
    )


class TestSavePortfolioSnapshot:
    """`_save_portfolio_snapshot` — записывает текущий portfolio.total_amount."""

    def test_saves_value_and_timestamp(self, session_factory, user_account) -> None:
        p = _make_pipeline(session_factory, user_account)
        p._last_portfolio_total_rub = Decimal("250000")

        before = datetime.utcnow()
        p._save_portfolio_snapshot()
        after = datetime.utcnow()

        s = session_factory()
        a = s.query(Account).filter(Account.id == user_account).first()
        assert a.last_portfolio_value == Decimal("250000")
        assert before <= a.last_portfolio_at <= after
        s.close()

    def test_does_nothing_without_portfolio(self, session_factory, user_account) -> None:
        p = _make_pipeline(session_factory, user_account)
        p._last_portfolio_total_rub = None
        p._save_portfolio_snapshot()

        s = session_factory()
        a = s.query(Account).filter(Account.id == user_account).first()
        assert a.last_portfolio_value is None
        assert a.last_portfolio_at is None
        s.close()

    def test_overwrites_existing(self, session_factory, user_account) -> None:
        """Каждый sync обновляет значение (это snapshot, не immutable)."""
        s = session_factory()
        a = s.query(Account).filter(Account.id == user_account).first()
        a.last_portfolio_value = Decimal("100000")
        a.last_portfolio_at = datetime(2020, 1, 1)
        s.commit()
        s.close()

        p = _make_pipeline(session_factory, user_account)
        p._last_portfolio_total_rub = Decimal("500000")
        p._save_portfolio_snapshot()

        s = session_factory()
        a = s.query(Account).filter(Account.id == user_account).first()
        assert a.last_portfolio_value == Decimal("500000")
        assert a.last_portfolio_at > datetime(2025, 1, 1)
        s.close()


class TestComputeBalanceAt:
    """`compute_balance_at(date)` — реконструирует баланс на любую дату."""

    def _set_snapshot(self, session_factory, account_id: int, value: Decimal) -> None:
        s = session_factory()
        a = s.query(Account).filter(Account.id == account_id).first()
        a.last_portfolio_value = value
        a.last_portfolio_at = datetime(2026, 5, 13)
        s.commit()
        s.close()

    def test_returns_none_without_snapshot(self, session_factory, user_account) -> None:
        s = session_factory()
        assert compute_balance_at(s, user_account, datetime(2026, 1, 1)) is None
        s.close()

    def test_returns_none_for_none_date(self, session_factory, user_account) -> None:
        self._set_snapshot(session_factory, user_account, Decimal("100000"))
        s = session_factory()
        assert compute_balance_at(s, user_account, None) is None
        s.close()

    def test_returns_current_when_date_in_future(self, session_factory, user_account) -> None:
        """Дата >= всех операций → ничего вычитать → balance = snapshot."""
        self._set_snapshot(session_factory, user_account, Decimal("250000"))
        s = session_factory()
        _add_op(s, user_account, "buy", -50_000, when=datetime(2025, 1, 1))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2099, 1, 1))
        assert result == 250_000.0
        s.close()

    def test_subtracts_pnl_after_date(self, session_factory, user_account) -> None:
        """Если после D было +30k прибыли, то до D было меньше."""
        self._set_snapshot(session_factory, user_account, Decimal("150000"))
        s = session_factory()
        # После D=2025-06-01: продали с прибылью 30k.
        _add_op(s, user_account, "buy", -100_000, when=datetime(2025, 6, 15))
        _add_op(s, user_account, "sell", 130_000, when=datetime(2025, 6, 20))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 6, 1))
        # balance_at(D) = 150_000 - (-100_000 + 130_000) = 150_000 - 30_000 = 120_000
        assert result == 120_000.0
        s.close()

    def test_subtracts_deposits_after_date(self, session_factory, user_account) -> None:
        """CRITICAL: depositы должны вычитаться — это был баг PR 21."""
        self._set_snapshot(session_factory, user_account, Decimal("500000"))
        s = session_factory()
        # После D=2025-01-01 юзер внёс 300k.
        _add_op(s, user_account, "input", 300_000, when=datetime(2025, 6, 1))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 1, 1))
        # balance_at(D) = 500_000 - 300_000 = 200_000 (до депозита было 200k)
        assert result == 200_000.0
        s.close()

    def test_subtracts_withdrawals_after_date(self, session_factory, user_account) -> None:
        """Выводы — отрицательный payment, вычитание делает balance выше."""
        self._set_snapshot(session_factory, user_account, Decimal("80000"))
        s = session_factory()
        _add_op(s, user_account, "output", -50_000, when=datetime(2025, 6, 1))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 1, 1))
        # balance_at(D) = 80_000 - (-50_000) = 130_000
        assert result == 130_000.0
        s.close()

    def test_handles_varmargin(self, session_factory, user_account) -> None:
        """Фьючерсные varmargin payments тоже учитываются."""
        self._set_snapshot(session_factory, user_account, Decimal("100000"))
        s = session_factory()
        _add_op(s, user_account, "accruing_varmargin", 5_000, when=datetime(2025, 6, 1))
        _add_op(s, user_account, "writing_off_varmargin", -8_000, when=datetime(2025, 6, 2))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 1, 1))
        # balance_at(D) = 100_000 - (5_000 + (-8_000)) = 100_000 - (-3_000) = 103_000
        assert result == 103_000.0
        s.close()

    def test_handles_fees(self, session_factory, user_account) -> None:
        """Комиссии тоже cash-операции — учитываем."""
        self._set_snapshot(session_factory, user_account, Decimal("50000"))
        s = session_factory()
        _add_op(s, user_account, "broker_fee", -500, when=datetime(2025, 6, 1))
        # PR 24: EXCHANGE_FEE убран — его нет в SDK; биржевая комиссия идёт
        # как BROKER_FEE или SERVICE_FEE.
        _add_op(s, user_account, "service_fee", -100, when=datetime(2025, 6, 1))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 1, 1))
        # balance_at(D) = 50_000 - (-600) = 50_600
        assert result == 50_600.0
        s.close()

    def test_complex_scenario_matches_real_data(self, session_factory, user_account) -> None:
        """
        Регрессия на реального юзера 4 — упрощённая версия.

        Сценарий: portfolio_now = 74K. После sync_from_date было:
        - Депозитов +308K
        - Реализованного PnL (фактически) -870K (через varmargin/trades)
        Σ payments(all) = 308K + (-870K) = -562K (упрощённо).
        balance_at(D) = 74K - (-562K) = 636K.

        Это grossly approximation реальной арифметики (без splits payment_nano),
        но проверяет что формула не теряет операции.
        """
        self._set_snapshot(session_factory, user_account, Decimal("74000"))
        s = session_factory()
        D = datetime(2025, 1, 1)
        # Депозиты после D
        _add_op(s, user_account, "input", 308_000, when=datetime(2025, 6, 1))
        # Чистая просадка после D
        _add_op(s, user_account, "writing_off_varmargin", -870_000, when=datetime(2025, 8, 1))
        s.commit()

        result = compute_balance_at(s, user_account, D)
        # 74000 - (308000 - 870000) = 74000 - (-562000) = 636000
        assert result == 636_000.0
        s.close()

    def test_only_executed_operations_counted(self, session_factory, user_account) -> None:
        """Canceled-операции не должны влиять на расчёт."""
        self._set_snapshot(session_factory, user_account, Decimal("100000"))
        s = session_factory()
        s.add(OperationORM(
            account_id=user_account,
            broker_account_id="2135909232",
            operation_id="op-canceled",
            operation_type="buy",
            state="canceled",
            quantity=0,
            payment_units=-50_000,
            payment_nano=0,
            executed_at=datetime(2025, 6, 1),
        ))
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 1, 1))
        # Canceled не учитывается → balance не изменился.
        assert result == 100_000.0
        s.close()

    def test_nano_precision(self, session_factory, user_account) -> None:
        """Payments с nano-частью — формула корректно конвертирует."""
        self._set_snapshot(session_factory, user_account, Decimal("100000.50"))
        s = session_factory()
        # 500.123456789 RUB прибыли (500 units + 123456789 nano)
        _add_op(
            s, user_account, "sell", 500,
            payment_nano=123_456_789, when=datetime(2025, 6, 1),
        )
        s.commit()

        result = compute_balance_at(s, user_account, datetime(2025, 1, 1))
        # 100000.50 - 500.123456789 ≈ 99500.376543211
        assert abs(result - 99_500.376543211) < 0.000001
        s.close()

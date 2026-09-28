"""MATH-03 (Sprint 4, Task 5.1): MAE/MFE coverage pipeline.

Проверяем что:
1. import-hook (`import_service.schedule_mae_mfe_backfill`) корректно
   запускает background-task и backfill'ит свежеимпортированные трейды;
2. nightly scheduler (`SyncScheduler._check_mae_mfe_backfill`) вызывает
   `jobs.mae_mfe_backfill.backfill_missing_mae_mfe` под флагом
   is_scheduler_worker и сдвигает _last_mae_mfe_backfill_run.

Не дёргаем реальный MOEX — `market_data_service.calculate_mae_mfe`
мокируется на уровне импорт-модуля.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from sqlalchemy.orm import sessionmaker

import models
import import_service
from utils.datetime_utils import utc_now_naive


def _factory_for(db_session):
    """SessionLocal-like фабрика, возвращающая тот же `db_session` (с подавлением
    `close()` — hook вызывает `db.close()` в finally, а в тестах это закроет
    fixture-сессию). SQLite in-memory + sessionmaker открывает per-session
    connection из пула — две разные сессии НЕ увидят коммитов друг друга
    (нет shared cache), поэтому нельзя создать «новую» сессию на том же
    engine — она будет видеть пустую БД."""
    class _NoCloseSession:
        def __init__(self, sess):
            self._sess = sess
        def __call__(self):
            return self
        def __getattr__(self, name):
            if name == "close":
                return lambda: None  # no-op
            return getattr(self._sess, name)
    return _NoCloseSession(db_session)


def _mk_user(db):
    u = models.User(email="imp@x.io", is_active=1)
    db.add(u)
    db.commit()
    return u


def _mk_account(db, user):
    a = models.Account(user_id=user.id, name="A", balance=0, initial_balance=0)
    db.add(a)
    db.commit()
    return a


def _mk_trade(db, account, *, exit_at, symbol="SBER"):
    now = utc_now_naive()
    t = models.Trade(
        account_id=account.id,
        symbol=symbol,
        direction=models.TradeDirection.LONG,
        entry_price=Decimal("100"),
        exit_price=Decimal("110") if exit_at else None,
        quantity=Decimal("10"),
        entry_at=now - timedelta(hours=5),
        exit_at=exit_at,
    )
    db.add(t)
    db.commit()
    return t


# ─────────────────────────────────────────────────────────────────
# 1. import-hook (_backfill_mae_mfe_for_imported_async)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_hook_backfills_closed_trades(db_session):
    """После import-hook closed-трейды получают MAE/MFE из market_service."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    t_closed = _mk_trade(db_session, acc, exit_at=now - timedelta(hours=1), symbol="SBER")
    t_open = _mk_trade(db_session, acc, exit_at=None, symbol="GAZP")

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95"), Decimal("105")))

    # Прокидываем DI session_factory чтобы coroutine использовал ту же in-memory DB.
    await import_service._backfill_mae_mfe_for_imported_async(
        [t_closed.id, t_open.id],
        market_service=fake,
        session_factory=_factory_for(db_session),
    )

    db_session.expire_all()
    t_closed = db_session.query(models.Trade).filter_by(id=t_closed.id).one()
    t_open = db_session.query(models.Trade).filter_by(id=t_open.id).one()
    assert t_closed.mae_price == Decimal("95")
    assert t_closed.mfe_price == Decimal("105")
    # Open трейд НЕ трогается hook'ом.
    assert t_open.mae_price is None
    assert t_open.mfe_price is None
    # market_service дёрнули ровно один раз (для закрытого).
    fake.calculate_mae_mfe.assert_called_once()


@pytest.mark.asyncio
async def test_import_hook_skips_already_filled(db_session):
    """Hook не пере-затирает уже посчитанные MAE/MFE."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    t = _mk_trade(db_session, acc, exit_at=now - timedelta(hours=1))
    t.mae_price = Decimal("88")
    t.mfe_price = Decimal("112")
    db_session.commit()

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95"), Decimal("105")))

    trade_id = t.id

    await import_service._backfill_mae_mfe_for_imported_async(
        [trade_id], market_service=fake, session_factory=_factory_for(db_session),
    )

    fake.calculate_mae_mfe.assert_not_called()
    fresh = db_session.query(models.Trade).filter_by(id=trade_id).one()
    assert fresh.mae_price == Decimal("88")
    assert fresh.mfe_price == Decimal("112")


@pytest.mark.asyncio
async def test_import_hook_swallows_per_trade_errors(db_session):
    """Exception от market_service для одного трейда не валит весь батч."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    t1 = _mk_trade(db_session, acc, exit_at=now - timedelta(hours=1), symbol="SBER")
    t2 = _mk_trade(db_session, acc, exit_at=now - timedelta(hours=2), symbol="GAZP")
    t1_id, t2_id = t1.id, t2.id

    call_count = {"n": 0}

    async def flaky(**kwargs):
        call_count["n"] += 1
        if kwargs["ticker"] == "SBER":
            raise RuntimeError("MOEX timeout")
        return (Decimal("95"), Decimal("105"))

    fake = AsyncMock()
    fake.calculate_mae_mfe = flaky

    await import_service._backfill_mae_mfe_for_imported_async(
        [t1_id, t2_id], market_service=fake, session_factory=_factory_for(db_session),
    )

    fresh1 = db_session.query(models.Trade).filter_by(id=t1_id).one()
    fresh2 = db_session.query(models.Trade).filter_by(id=t2_id).one()
    assert fresh1.mae_price is None  # failed — остался NULL
    assert fresh2.mae_price == Decimal("95")  # succeeded
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_schedule_mae_mfe_backfill_returns_task_in_loop():
    """В running event-loop schedule возвращает Task и регистрирует strong-ref."""
    # Подменяем MarketService — иначе hook вызовет реальный MOEX через MarketService().
    # Пустой trade_ids → None без любых импортов БД.
    assert import_service.schedule_mae_mfe_backfill([]) is None

    fake_svc = AsyncMock()
    fake_svc.calculate_mae_mfe = AsyncMock(return_value=(None, None))

    # Патчим SessionLocal и MarketService — без них hook тащит реальную БД и MOEX.
    with patch("import_service.MarketService" if False else "market_service.MarketService",
               return_value=fake_svc), \
         patch("database.SessionLocal") as mock_session_local:
        mock_db = AsyncMock()
        # query().filter().all() возвращает [] чтобы coroutine быстро завершилась.
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_session_local.return_value = mock_db

        task = import_service.schedule_mae_mfe_backfill([99999999])
        assert task is not None
        # Strong-ref должен держать task до завершения.
        assert task in import_service._BG_TASKS
        await task
        # После завершения discard-callback убирает из set'а.
        assert task not in import_service._BG_TASKS


def test_schedule_mae_mfe_backfill_no_loop_returns_none():
    """В sync-контексте без running loop — no-op, без exception."""
    # Эта функция не async — running loop отсутствует.
    result = import_service.schedule_mae_mfe_backfill([1, 2, 3])
    assert result is None


# ─────────────────────────────────────────────────────────────────
# 2. nightly scheduler hook
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scheduler_skips_when_not_scheduler_worker(monkeypatch):
    """Если is_scheduler_worker()=False — _check_mae_mfe_backfill no-op."""
    monkeypatch.setenv("IS_SCHEDULER_WORKER", "false")
    from sync_scheduler import SyncScheduler

    sched = SyncScheduler()
    called = {"n": 0}

    async def fake_backfill(*args, **kwargs):
        called["n"] += 1
        return {"processed": 0, "succeeded": 0, "failed": 0}

    with patch("jobs.mae_mfe_backfill.backfill_missing_mae_mfe", side_effect=fake_backfill):
        await sched._check_mae_mfe_backfill()

    assert called["n"] == 0
    assert sched._last_mae_mfe_backfill_run is None


@pytest.mark.asyncio
async def test_scheduler_runs_backfill_and_advances_cursor(monkeypatch):
    """Когда is_scheduler_worker()=True и интервал не задан — backfill вызывается."""
    monkeypatch.setenv("IS_SCHEDULER_WORKER", "true")
    from sync_scheduler import SyncScheduler

    sched = SyncScheduler()
    called = {"n": 0, "kwargs": None}

    async def fake_backfill(session, *, limit, max_age_days):
        called["n"] += 1
        called["kwargs"] = (limit, max_age_days)
        return {"processed": 0, "succeeded": 0, "failed": 0}

    with patch("jobs.mae_mfe_backfill.backfill_missing_mae_mfe", side_effect=fake_backfill):
        await sched._check_mae_mfe_backfill()

    assert called["n"] == 1
    # Cursor advanced — следующий вызов не должен вызвать backfill.
    assert sched._last_mae_mfe_backfill_run is not None

    with patch("jobs.mae_mfe_backfill.backfill_missing_mae_mfe", side_effect=fake_backfill):
        await sched._check_mae_mfe_backfill()

    assert called["n"] == 1  # не вырос — interval'а не прошло


@pytest.mark.asyncio
async def test_scheduler_advances_cursor_even_on_exception(monkeypatch):
    """Backfill кинул — cursor всё равно сдвигается чтобы не было hot-loop'а."""
    monkeypatch.setenv("IS_SCHEDULER_WORKER", "true")
    from sync_scheduler import SyncScheduler

    sched = SyncScheduler()

    async def boom(*args, **kwargs):
        raise RuntimeError("DB down")

    with patch("jobs.mae_mfe_backfill.backfill_missing_mae_mfe", side_effect=boom):
        await sched._check_mae_mfe_backfill()

    assert sched._last_mae_mfe_backfill_run is not None

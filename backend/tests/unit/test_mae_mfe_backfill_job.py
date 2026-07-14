"""MATH-03 (Sprint 4, Task 5.1): backfill job unit-tests.

Проверяем что nightly backfill:
- пропускает open-трейды (exit_at IS NULL);
- пропускает старые трейды (entry_at < cutoff);
- успешно обновляет mae/mfe когда market_service отдал значения;
- логирует и считает failed при exception market_service;
- не считает «нет данных» (None, None) как failed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import models
from jobs.mae_mfe_backfill import backfill_missing_mae_mfe
from utils.datetime_utils import utc_now_naive


def _mk_user(db_session):
    u = models.User(email="t@x.io", is_active=1)
    db_session.add(u)
    db_session.commit()
    return u


def _mk_account(db_session, user):
    a = models.Account(user_id=user.id, name="A", balance=0, initial_balance=0)
    db_session.add(a)
    db_session.commit()
    return a


def _mk_trade(
    db_session,
    account,
    *,
    entry_at: datetime,
    exit_at: datetime | None,
    symbol: str = "SBER",
    mae: Decimal | None = None,
):
    t = models.Trade(
        account_id=account.id,
        symbol=symbol,
        direction=models.TradeDirection.LONG,
        entry_price=Decimal("100"),
        exit_price=Decimal("110") if exit_at else None,
        quantity=Decimal("10"),
        entry_at=entry_at,
        exit_at=exit_at,
        mae_price=mae,
    )
    db_session.add(t)
    db_session.commit()
    return t


@pytest.mark.asyncio
async def test_backfill_skips_trades_without_exit_at(db_session):
    """Open трейды (без exit_at) НЕ должны попадать в backfill."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(days=1),
        exit_at=None,  # open
    )
    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95"), Decimal("105")))

    result = await backfill_missing_mae_mfe(db_session, market_service=fake)

    assert result["processed"] == 0
    assert result["succeeded"] == 0
    assert result["failed"] == 0
    fake.calculate_mae_mfe.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_respects_max_age_days(db_session):
    """Старые трейды (entry_at < cutoff) пропускаются."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(days=60),  # старше дефолтного cutoff=30
        exit_at=now - timedelta(days=59),
    )
    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95"), Decimal("105")))

    result = await backfill_missing_mae_mfe(
        db_session, market_service=fake, max_age_days=30
    )

    assert result["processed"] == 0
    fake.calculate_mae_mfe.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_updates_mae_mfe_on_success(db_session):
    """Свежий closed-трейд без MAE → market_service вызвался → значения проставились."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    t = _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(hours=5),
        exit_at=now - timedelta(hours=1),
    )

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95.0"), Decimal("105.0")))

    result = await backfill_missing_mae_mfe(db_session, market_service=fake)

    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    fake.calculate_mae_mfe.assert_called_once()

    db_session.refresh(t)
    assert t.mae_price == Decimal("95.0")
    assert t.mfe_price == Decimal("105.0")


@pytest.mark.asyncio
async def test_backfill_logs_failure_but_continues(db_session):
    """Если market_service кидает — считаем failed, не падаем, commit идёт."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(hours=5),
        exit_at=now - timedelta(hours=1),
        symbol="SBER",
    )
    _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(hours=4),
        exit_at=now - timedelta(hours=2),
        symbol="GAZP",
    )

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(side_effect=RuntimeError("MOEX timeout"))

    result = await backfill_missing_mae_mfe(db_session, market_service=fake)

    assert result["processed"] == 2
    assert result["failed"] == 2
    assert result["succeeded"] == 0


@pytest.mark.asyncio
async def test_backfill_treats_none_as_no_data_not_failure(db_session):
    """(None, None) от market_service — это «нет данных», не failure."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    t = _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(hours=5),
        exit_at=now - timedelta(hours=1),
    )

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(None, None))

    result = await backfill_missing_mae_mfe(db_session, market_service=fake)

    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 0

    db_session.refresh(t)
    assert t.mae_price is None
    assert t.mfe_price is None


@pytest.mark.asyncio
async def test_backfill_skips_trades_with_existing_mae(db_session):
    """Трейды у которых уже есть mae_price — пропускаются (фильтр mae_price IS NULL)."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    _mk_trade(
        db_session,
        acc,
        entry_at=now - timedelta(hours=5),
        exit_at=now - timedelta(hours=1),
        mae=Decimal("99"),  # уже заполнено
    )

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95"), Decimal("105")))

    result = await backfill_missing_mae_mfe(db_session, market_service=fake)

    assert result["processed"] == 0
    fake.calculate_mae_mfe.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_respects_limit(db_session):
    """limit=N не даёт обработать больше N трейдов."""
    user = _mk_user(db_session)
    acc = _mk_account(db_session, user)
    now = utc_now_naive()
    for i in range(5):
        _mk_trade(
            db_session,
            acc,
            entry_at=now - timedelta(hours=5 + i),
            exit_at=now - timedelta(hours=1 + i),
            symbol=f"S{i}",
        )

    fake = AsyncMock()
    fake.calculate_mae_mfe = AsyncMock(return_value=(Decimal("95"), Decimal("105")))

    result = await backfill_missing_mae_mfe(db_session, market_service=fake, limit=2)

    assert result["processed"] == 2
    assert result["succeeded"] == 2

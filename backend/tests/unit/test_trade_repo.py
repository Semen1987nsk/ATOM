"""
Unit-тесты для TradeRepository._trade_to_orm — гарантия что Trade-журнал
заполняется правильными метаданными для UI и аналитики.

PR 19 регрессии:
- asset_name берётся из Instrument.name (не остаётся NULL у sync-сделок).
- holding_time_minutes считается из (exit_at − entry_at) если оба заданы.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from adapters.persistence.trade_repo import TradeRepository
from domain.entities import Instrument, Trade
from domain.enums import InstrumentType, TradeDataSource, TradeDirection


def _make_instrument(**overrides) -> Instrument:
    base = dict(
        uid="uid-sber",
        figi="BBG004730N88",
        ticker="SBER",
        name="Сбер Банк",
        instrument_type=InstrumentType.SHARE,
        lot=10,
    )
    base.update(overrides)
    return Instrument(**base)


def _make_trade(**overrides) -> Trade:
    base = dict(
        account_id="42",
        instrument_uid="uid-sber",
        instrument_figi="BBG004730N88",
        instrument_type=InstrumentType.SHARE,
        direction=TradeDirection.LONG,
        quantity=100,
        entry_price=Decimal("270"),
        exit_price=Decimal("275"),
        entry_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        exit_at=datetime(2026, 5, 9, 13, 30, tzinfo=timezone.utc),
        pnl=Decimal("500"),
        net_pnl=Decimal("500"),
        commission_total=Decimal("0"),
        entry_value=Decimal("27000"),
        exit_value=Decimal("27500"),
        currency="rub",
    )
    base.update(overrides)
    return Trade(**base)


class TestTradeToOrmMetadata:
    def test_asset_name_from_instrument(self) -> None:
        """asset_name берётся из Instrument.name."""
        trade = _make_trade()
        instr = _make_instrument(name="Сбер Банк")
        orm = TradeRepository._trade_to_orm(
            trade=trade,
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=instr,
        )
        assert orm.asset_name == "Сбер Банк"
        assert orm.symbol == "SBER"

    def test_asset_name_none_when_no_instrument(self) -> None:
        """Без Instrument asset_name = None (legacy / manual путь)."""
        orm = TradeRepository._trade_to_orm(
            trade=_make_trade(),
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=None,
        )
        assert orm.asset_name is None

    def test_holding_time_computed_from_dates(self) -> None:
        """holding_time_minutes = (exit - entry) / 60."""
        trade = _make_trade(
            entry_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
            exit_at=datetime(2026, 5, 9, 12, 30, tzinfo=timezone.utc),
        )
        orm = TradeRepository._trade_to_orm(
            trade=trade,
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=_make_instrument(),
        )
        # 2 часа 30 минут = 150 минут.
        assert orm.holding_time_minutes == 150

    def test_holding_time_for_multi_day_trade(self) -> None:
        trade = _make_trade(
            entry_at=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            exit_at=datetime(2026, 5, 3, 13, 0, tzinfo=timezone.utc),
        )
        orm = TradeRepository._trade_to_orm(
            trade=trade,
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=_make_instrument(),
        )
        # 2 дня 3 часа = (48 + 3) * 60 = 3060 минут.
        assert orm.holding_time_minutes == 3060

    def test_holding_time_none_for_open_trade(self) -> None:
        """Если exit_at = None (открытая позиция, FIFO не должен такое создавать,
        но защищаемся), holding_time = None."""
        trade = _make_trade(exit_at=None, exit_price=None, pnl=None)
        orm = TradeRepository._trade_to_orm(
            trade=trade,
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=_make_instrument(),
        )
        assert orm.holding_time_minutes is None
        assert orm.exit_at is None

    def test_holding_time_handles_naive_and_aware_dates(self) -> None:
        """entry_at с tzinfo, exit_at без — обоих переводим в naive UTC."""
        # ORM хранит naive UTC, _trade_to_orm нормализует.
        trade = _make_trade(
            entry_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
            exit_at=datetime(2026, 5, 9, 11, 0, tzinfo=timezone.utc),
        )
        orm = TradeRepository._trade_to_orm(
            trade=trade,
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=_make_instrument(),
        )
        assert orm.holding_time_minutes == 60

    def test_instrument_type_v2_filled(self) -> None:
        """Регрессия PR 19 schema: instrument_type_v2 заполняется из enum."""
        trade = _make_trade(instrument_type=InstrumentType.FUTURES)
        orm = TradeRepository._trade_to_orm(
            trade=trade,
            account_id=1,
            data_source=TradeDataSource.TINKOFF_V2.value,
            synced_at=datetime.utcnow(),
            instrument=_make_instrument(instrument_type=InstrumentType.FUTURES),
        )
        assert orm.instrument_type_v2 == "futures"

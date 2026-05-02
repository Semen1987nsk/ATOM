from datetime import datetime
from typing import cast

import models
from tinkoff_service import TinkoffService


def _money(value: int) -> dict:
    return {"units": value, "nano": 0}


def _trade_op(op_id: str, operation_type: str, figi: str, qty: int, price: int, payment: int, dt: datetime) -> dict:
    return {
        "id": op_id,
        "operationType": operation_type,
        "figi": figi,
        "quantityDone": qty,
        "price": _money(price),
        "payment": _money(payment),
        "date": dt.isoformat() + "Z",
        "childOperations": [],
    }


def _create_account(db_session):
    user = models.User(
        email="sync@example.com",
        name="Sync User",
        hashed_password="hashed",
        is_active=1,
        is_admin=0,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    account = models.Account(
        user_id=user.id,
        name="Sync Account",
        balance=0,
        currency="RUB",
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


class TestTinkoffSyncRegression:
    def test_sync_backfills_truncated_history_for_ghost_open_position(self, db_session, monkeypatch):
        account = _create_account(db_session)
        buy_at = datetime(2025, 9, 1, 10, 0)
        sell_at = datetime(2025, 10, 20, 11, 0)
        sync_now = datetime(2025, 10, 21, 12, 0)

        connection = models.BrokerConnection(
            account_id=account.id,
            broker=models.BrokerType.TINKOFF,
            api_token="test-token",
            broker_account_id="broker-account",
            sync_from_date=datetime(2025, 10, 20, 0, 0),
            is_active=True,
            auto_sync_enabled=True,
        )
        db_session.add(connection)
        db_session.commit()

        service = TinkoffService("test-token")
        captured_calls = []

        buy_op = _trade_op("buy-1", "OPERATION_TYPE_BUY", "FIGI-FIXR", 400, 10, -4000, buy_at)
        sell_op = _trade_op("sell-1", "OPERATION_TYPE_SELL", "FIGI-FIXR", 400, 12, 4800, sell_at)

        def fake_get_operations(broker_account_id, from_date, to_date):
            captured_calls.append((from_date, to_date))
            if from_date >= datetime(2025, 10, 20, 0, 0):
                return [sell_op]
            return [buy_op, sell_op]

        monkeypatch.setattr("tinkoff_service.utc_now_naive", lambda: sync_now)
        monkeypatch.setattr(service, "get_operations", fake_get_operations)
        monkeypatch.setattr(
            service,
            "get_instrument_info",
            lambda figi: {
                "figi": figi,
                "ticker": "FIXR",
                "name": "Fix Price",
                "lot": 1,
                "currency": "RUB",
                "instrument_type": "INSTRUMENT_TYPE_SHARE",
            },
        )
        monkeypatch.setattr(
            service,
            "get_portfolio",
            lambda broker_account_id: {
                "total_balance": 0,
                "cash": 0,
                "unrealized_pnl": 0,
                "stocks_value": 0,
                "bonds_value": 0,
                "etf_value": 0,
                "futures_value": 0,
                "positions": [],
                "raw": {},
            },
        )

        result = service.sync_trades(db_session, connection)

        assert result["success"] is True
        assert len(captured_calls) >= 2

        trades = db_session.query(models.Trade).filter(models.Trade.account_id == account.id).all()
        assert len(trades) == 1
        trade = trades[0]
        assert trade.symbol == "FIXR"
        assert trade.direction == models.TradeDirection.LONG
        assert trade.entry_at == buy_at
        assert trade.exit_at == sell_at
        assert float(trade.quantity) == 400.0
        assert {op["op_id"] for op in trade.operations} == {"buy-1", "sell-1"}

    def test_sync_removes_stale_closed_autosync_trade(self, db_session, monkeypatch):
        account = _create_account(db_session)
        buy_at = datetime(2025, 1, 2, 10, 0)
        add_at = datetime(2025, 1, 2, 11, 0)
        sell_at = datetime(2025, 1, 2, 12, 0)
        sync_now = datetime(2025, 1, 3, 12, 0)

        connection = models.BrokerConnection(
            account_id=account.id,
            broker=models.BrokerType.TINKOFF,
            api_token="test-token",
            broker_account_id="broker-account",
            sync_from_date=datetime(2025, 1, 1, 0, 0),
            is_active=True,
            auto_sync_enabled=True,
        )
        db_session.add(connection)

        canonical_trade = models.Trade(
            account_id=account.id,
            symbol="CCH6",
            asset_name="Cocoa Futures",
            asset_type="Stock",
            direction=models.TradeDirection.LONG,
            entry_price=103.33333333,
            exit_price=120,
            quantity=15,
            entry_at=buy_at,
            exit_at=sell_at,
            pnl=250,
            net_pnl=250,
            commission=0,
            currency="RUB",
            operations=[
                {"type": "entry", "op_id": "buy-1", "qty": 10, "price": 100.0, "time": buy_at.isoformat()},
                {"type": "entry", "op_id": "buy-2", "qty": 5, "price": 110.0, "time": add_at.isoformat()},
                {"type": "exit", "op_id": "sell-1", "qty": 10, "price": 120.0, "time": sell_at.isoformat()},
                {"type": "exit", "op_id": "sell-1", "qty": 5, "price": 120.0, "time": sell_at.isoformat()},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        stale_subset_trade = models.Trade(
            account_id=account.id,
            symbol="CCH6",
            asset_name="Cocoa Futures",
            asset_type="Stock",
            direction=models.TradeDirection.LONG,
            entry_price=110,
            exit_price=120,
            quantity=5,
            entry_at=add_at,
            exit_at=sell_at,
            pnl=50,
            net_pnl=50,
            commission=0,
            currency="RUB",
            operations=[
                {"type": "entry", "op_id": "buy-2", "qty": 5, "price": 110.0, "time": add_at.isoformat()},
                {"type": "exit", "op_id": "sell-1", "qty": 5, "price": 120.0, "time": sell_at.isoformat()},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add_all([canonical_trade, stale_subset_trade])
        db_session.commit()

        service = TinkoffService("test-token")

        buy_op = _trade_op("buy-1", "OPERATION_TYPE_BUY", "FIGI-CCH6", 10, 100, -1000, buy_at)
        add_op = _trade_op("buy-2", "OPERATION_TYPE_BUY", "FIGI-CCH6", 5, 110, -550, add_at)
        sell_op = _trade_op("sell-1", "OPERATION_TYPE_SELL", "FIGI-CCH6", 15, 120, 1800, sell_at)

        monkeypatch.setattr("tinkoff_service.utc_now_naive", lambda: sync_now)
        monkeypatch.setattr(service, "get_operations", lambda broker_account_id, from_date, to_date: [buy_op, add_op, sell_op])
        monkeypatch.setattr(
            service,
            "get_instrument_info",
            lambda figi: {
                "figi": figi,
                "ticker": "CCH6",
                "name": "Cocoa Futures",
                "lot": 1,
                "currency": "RUB",
                "instrument_type": "INSTRUMENT_TYPE_SHARE",
            },
        )
        monkeypatch.setattr(
            service,
            "get_portfolio",
            lambda broker_account_id: {
                "total_balance": 0,
                "cash": 0,
                "unrealized_pnl": 0,
                "stocks_value": 0,
                "bonds_value": 0,
                "etf_value": 0,
                "futures_value": 0,
                "positions": [],
                "raw": {},
            },
        )

        result = service.sync_trades(db_session, connection)

        assert result["success"] is True
        assert result["cleanup_deleted"] == 1

        trades = db_session.query(models.Trade).filter(models.Trade.account_id == account.id).all()
        assert len(trades) == 1
        trade = trades[0]
        assert {op["op_id"] for op in trade.operations} == {"buy-1", "buy-2", "sell-1"}
        assert float(trade.quantity) == 15.0

    def test_incremental_sync_closes_existing_open_position(self, db_session, monkeypatch):
        account = _create_account(db_session)
        open_entry_at = datetime(2025, 1, 1, 10, 0)
        sync_now = datetime(2025, 1, 4, 12, 0)
        exit_at = datetime(2025, 1, 4, 10, 0)

        connection = models.BrokerConnection(
            account_id=account.id,
            broker=models.BrokerType.TINKOFF,
            api_token="test-token",
            broker_account_id="broker-account",
            last_sync_at=datetime(2025, 1, 3, 12, 0),
            is_active=True,
            auto_sync_enabled=True,
        )
        db_session.add(connection)

        existing_open_trade = models.Trade(
            account_id=account.id,
            symbol="SBER",
            asset_name="Sberbank",
            asset_type="Stock",
            direction=models.TradeDirection.LONG,
            entry_price=100,
            quantity=1,
            entry_at=open_entry_at,
            exit_at=None,
            commission=0,
            currency="RUB",
            operations=[
                {
                    "type": "entry",
                    "op_id": "buy-1",
                    "qty": 1,
                    "price": 100.0,
                }
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add(existing_open_trade)
        db_session.commit()

        service = TinkoffService("test-token")
        captured = {}

        buy_op = _trade_op("buy-1", "OPERATION_TYPE_BUY", "FIGI1", 1, 100, -100, open_entry_at)
        sell_op = _trade_op("sell-1", "OPERATION_TYPE_SELL", "FIGI1", 1, 110, 110, exit_at)

        def fake_get_operations(broker_account_id, from_date, to_date):
            captured["from_date"] = from_date
            if from_date <= open_entry_at:
                return [buy_op, sell_op]
            return [sell_op]

        monkeypatch.setattr("tinkoff_service.utc_now_naive", lambda: sync_now)
        monkeypatch.setattr(service, "get_operations", fake_get_operations)
        monkeypatch.setattr(
            service,
            "get_instrument_info",
            lambda figi: {
                "figi": figi,
                "ticker": "SBER",
                "name": "Sberbank",
                "lot": 1,
                "currency": "RUB",
                "instrument_type": "INSTRUMENT_TYPE_SHARE",
            },
        )
        monkeypatch.setattr(
            service,
            "get_portfolio",
            lambda broker_account_id: {
                "total_balance": 0,
                "cash": 0,
                "unrealized_pnl": 0,
                "stocks_value": 0,
                "bonds_value": 0,
                "etf_value": 0,
                "futures_value": 0,
                "positions": [],
                "raw": {},
            },
        )

        result = service.sync_trades(db_session, connection)

        assert result["success"] is True
        assert captured["from_date"] <= open_entry_at

        trades = db_session.query(models.Trade).filter(models.Trade.account_id == account.id).all()
        assert len(trades) == 1

        trade = trades[0]
        assert trade.exit_at == exit_at
        assert trade.direction == models.TradeDirection.LONG
        assert float(trade.pnl) == 10.0
        assert float(trade.net_pnl) == 10.0
        assert {op["op_id"] for op in trade.operations} == {"buy-1", "sell-1"}

    def test_find_existing_trade_by_ops_rejects_half_overlap(self, db_session):
        account = _create_account(db_session)
        trade = models.Trade(
            account_id=account.id,
            symbol="SBER",
            asset_name="Sberbank",
            asset_type="Stock",
            direction=models.TradeDirection.LONG,
            entry_price=100,
            quantity=1,
            entry_at=datetime(2025, 1, 1, 10, 0),
            exit_at=datetime(2025, 1, 1, 11, 0),
            pnl=10,
            net_pnl=10,
            operations=[
                {"type": "entry", "op_id": "buy-1"},
                {"type": "exit", "op_id": "sell-1"},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add(trade)
        db_session.commit()

        service = TinkoffService("test-token")

        account_id = cast(int, account.id)

        assert service._find_existing_trade_by_ops(
            db=db_session,
            account_id=account_id,
            op_ids=["buy-1", "sell-2"],
            symbol="SBER",
        ) is None

    def test_find_existing_trade_by_ops_accepts_subset_match_for_open_trade(self, db_session):
        account = _create_account(db_session)
        trade = models.Trade(
            account_id=account.id,
            symbol="SBER",
            asset_name="Sberbank",
            asset_type="Stock",
            direction=models.TradeDirection.LONG,
            entry_price=100,
            quantity=1,
            entry_at=datetime(2025, 1, 1, 10, 0),
            exit_at=None,
            operations=[
                {"type": "entry", "op_id": "buy-1"},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add(trade)
        db_session.commit()

        service = TinkoffService("test-token")
        account_id = cast(int, account.id)
        match = service._find_existing_trade_by_ops(
            db=db_session,
            account_id=account_id,
            op_ids=["buy-1", "sell-1"],
            symbol="SBER",
        )

        assert match is not None
        assert cast(int, match.id) == cast(int, trade.id)

    def test_incremental_sync_backfills_corrupted_open_trade_context(self, db_session, monkeypatch):
        account = _create_account(db_session)
        buy_at = datetime(2025, 1, 2, 10, 0)
        sell_at = datetime(2025, 1, 4, 16, 30)
        sync_now = datetime(2025, 1, 5, 12, 0)

        connection = models.BrokerConnection(
            account_id=account.id,
            broker=models.BrokerType.TINKOFF,
            api_token="test-token",
            broker_account_id="broker-account",
            last_sync_at=datetime(2025, 1, 5, 9, 0),
            is_active=True,
            auto_sync_enabled=True,
        )
        db_session.add(connection)

        corrupted_open_trade = models.Trade(
            account_id=account.id,
            symbol="CCH6",
            asset_name="Cocoa Futures",
            asset_type="Futures",
            direction=models.TradeDirection.SHORT,
            entry_price=110,
            quantity=10,
            entry_at=sell_at,
            exit_at=None,
            commission=0,
            currency="RUB",
            operations=[
                {
                    "type": "entry",
                    "op_id": "sell-1",
                    "qty": 10,
                    "price": 110.0,
                    "time": sell_at.isoformat(),
                }
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add(corrupted_open_trade)
        db_session.commit()

        service = TinkoffService("test-token")
        captured = {}

        buy_op = _trade_op("buy-1", "OPERATION_TYPE_BUY", "FIGI-CCH6", 10, 100, -100, buy_at)
        sell_op = _trade_op("sell-1", "OPERATION_TYPE_SELL", "FIGI-CCH6", 10, 110, 110, sell_at)

        def fake_get_operations(broker_account_id, from_date, to_date):
            captured["from_date"] = from_date
            if from_date <= buy_at:
                return [buy_op, sell_op]
            return [sell_op]

        monkeypatch.setattr("tinkoff_service.utc_now_naive", lambda: sync_now)
        monkeypatch.setattr(service, "get_operations", fake_get_operations)
        monkeypatch.setattr(
            service,
            "get_instrument_info",
            lambda figi: {
                "figi": figi,
                "ticker": "CCH6",
                "name": "Cocoa Futures",
                "lot": 1,
                "currency": "RUB",
                "instrument_type": "INSTRUMENT_TYPE_SHARE",
            },
        )
        monkeypatch.setattr(
            service,
            "get_portfolio",
            lambda broker_account_id: {
                "total_balance": 0,
                "cash": 0,
                "unrealized_pnl": 0,
                "stocks_value": 0,
                "bonds_value": 0,
                "etf_value": 0,
                "futures_value": 0,
                "positions": [],
                "raw": {},
            },
        )

        result = service.sync_trades(db_session, connection)

        assert result["success"] is True
        assert captured["from_date"] <= buy_at

        trades = db_session.query(models.Trade).filter(models.Trade.account_id == account.id).all()
        assert len(trades) == 1
        trade = trades[0]
        assert trade.exit_at == sell_at
        assert trade.direction == models.TradeDirection.LONG
        assert float(trade.pnl) == 10.0
        assert {op["op_id"] for op in trade.operations} == {"buy-1", "sell-1"}

    def test_reconcile_stale_open_trade_deletes_duplicate_ghost(self, db_session):
        account = _create_account(db_session)
        closed_trade = models.Trade(
            account_id=account.id,
            symbol="CCH6",
            asset_name="Cocoa Futures",
            asset_type="Futures",
            direction=models.TradeDirection.LONG,
            entry_price=100,
            exit_price=110,
            quantity=10,
            entry_at=datetime(2025, 1, 2, 10, 0),
            exit_at=datetime(2025, 1, 4, 16, 30),
            pnl=10,
            net_pnl=10,
            operations=[
                {"type": "entry", "op_id": "buy-1", "time": datetime(2025, 1, 2, 10, 0).isoformat()},
                {"type": "exit", "op_id": "sell-1", "time": datetime(2025, 1, 4, 16, 30).isoformat()},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        ghost_open_trade = models.Trade(
            account_id=account.id,
            symbol="CCH6",
            asset_name="Cocoa Futures",
            asset_type="Futures",
            direction=models.TradeDirection.SHORT,
            entry_price=110,
            quantity=10,
            entry_at=datetime(2025, 1, 4, 16, 30),
            exit_at=None,
            operations=[
                {"type": "entry", "op_id": "sell-1", "time": datetime(2025, 1, 4, 16, 30).isoformat()},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add_all([closed_trade, ghost_open_trade])
        db_session.commit()

        service = TinkoffService("test-token")
        stats = service._reconcile_stale_open_trades(
            db=db_session,
            account_id=cast(int, account.id),
            broker_open_symbols=set(),
        )
        db_session.flush()

        remaining = db_session.query(models.Trade).filter(models.Trade.account_id == account.id).all()
        assert stats == {"closed": 0, "deleted": 1}
        assert len(remaining) == 1
        assert remaining[0].exit_at is not None

    def test_reconcile_stale_open_trade_closes_missing_position(self, db_session):
        account = _create_account(db_session)
        missing_open_trade = models.Trade(
            account_id=account.id,
            symbol="XIZ5",
            asset_name="Xi Futures",
            asset_type="Futures",
            direction=models.TradeDirection.SHORT,
            entry_price=50,
            quantity=2,
            entry_at=datetime(2025, 1, 4, 16, 30),
            exit_at=None,
            operations=[
                {"type": "entry", "op_id": "sell-1", "time": datetime(2025, 1, 4, 16, 30).isoformat()},
            ],
            tags=["#tinkoff", "#autosync"],
        )
        db_session.add(missing_open_trade)
        db_session.commit()

        service = TinkoffService("test-token")
        stats = service._reconcile_stale_open_trades(
            db=db_session,
            account_id=cast(int, account.id),
            broker_open_symbols=set(),
        )
        db_session.flush()
        refreshed_trade = db_session.query(models.Trade).filter(models.Trade.id == missing_open_trade.id).first()

        assert stats == {"closed": 1, "deleted": 0}
        assert refreshed_trade is not None
        assert refreshed_trade.exit_at == datetime(2025, 1, 4, 16, 30)
        assert refreshed_trade.exit_reason == "Broker sync reconciliation"
        assert "#reconciled" in (refreshed_trade.tags or [])

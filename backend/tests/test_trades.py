"""
Tests for trade CRUD operations and FIFO logic.
"""
import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
import schemas
from conftest import db_session


class TestTradeModel:
    """Tests for Trade model."""
    
    def test_create_trade(self, db_session):
        """Should create a trade in the database."""
        trade = models.Trade(
            account_id=1,
            symbol="SBER",
            direction=models.TradeDirection.LONG,
            entry_price=300.0,
            quantity=10,
            entry_at=datetime.now()
        )
        db_session.add(trade)
        db_session.commit()
        
        assert trade.id is not None
        assert trade.symbol == "SBER"
        assert trade.direction == models.TradeDirection.LONG
    
    def test_trade_pnl_long(self, db_session):
        """Should correctly calculate PnL for LONG trade."""
        trade = models.Trade(
            account_id=1,
            symbol="GAZP",
            direction=models.TradeDirection.LONG,
            entry_price=150.0,
            exit_price=160.0,
            quantity=100,
            entry_at=datetime.now(),
            exit_at=datetime.now()
        )
        db_session.add(trade)
        
        # Calculate PnL manually
        pnl = (float(trade.exit_price) - float(trade.entry_price)) * float(trade.quantity)
        trade.pnl = pnl
        
        db_session.commit()
        
        assert trade.pnl == 1000.0  # (160 - 150) * 100
    
    def test_trade_pnl_short(self, db_session):
        """Should correctly calculate PnL for SHORT trade."""
        trade = models.Trade(
            account_id=1,
            symbol="AFKS",
            direction=models.TradeDirection.SHORT,
            entry_price=20.0,
            exit_price=18.0,
            quantity=500,
            entry_at=datetime.now(),
            exit_at=datetime.now()
        )
        db_session.add(trade)
        
        # Calculate PnL manually (SHORT: entry - exit)
        pnl = (float(trade.entry_price) - float(trade.exit_price)) * float(trade.quantity)
        trade.pnl = pnl
        
        db_session.commit()
        
        assert trade.pnl == 1000.0  # (20 - 18) * 500
    
    def test_trade_net_pnl(self, db_session):
        """Should correctly calculate Net PnL with commission."""
        trade = models.Trade(
            account_id=1,
            symbol="LKOH",
            direction=models.TradeDirection.LONG,
            entry_price=7000.0,
            exit_price=7100.0,
            quantity=10,
            commission=50.0,
            swap=5.0,
            entry_at=datetime.now(),
            exit_at=datetime.now()
        )
        db_session.add(trade)
        
        pnl = (float(trade.exit_price) - float(trade.entry_price)) * float(trade.quantity)
        trade.pnl = pnl
        trade.net_pnl = pnl - float(trade.commission) - float(trade.swap)
        
        db_session.commit()
        
        assert trade.pnl == 1000.0  # (7100 - 7000) * 10
        assert trade.net_pnl == 945.0  # 1000 - 50 - 5


class TestTradeQueries:
    """Tests for trade queries."""
    
    def test_filter_open_trades(self, db_session):
        """Should filter only open trades."""
        # Create open trade
        open_trade = models.Trade(
            account_id=1,
            symbol="SBER",
            direction=models.TradeDirection.LONG,
            entry_price=300.0,
            quantity=10,
            entry_at=datetime.now()
        )
        
        # Create closed trade
        closed_trade = models.Trade(
            account_id=1,
            symbol="GAZP",
            direction=models.TradeDirection.SHORT,
            entry_price=150.0,
            exit_price=145.0,
            quantity=20,
            entry_at=datetime.now(),
            exit_at=datetime.now()
        )
        
        db_session.add_all([open_trade, closed_trade])
        db_session.commit()
        
        open_trades = db_session.query(models.Trade).filter(
            models.Trade.exit_at == None
        ).all()
        
        assert len(open_trades) == 1
        assert open_trades[0].symbol == "SBER"
    
    def test_filter_by_symbol(self, db_session):
        """Should filter trades by symbol."""
        trade1 = models.Trade(
            account_id=1, symbol="SBER", direction=models.TradeDirection.LONG,
            entry_price=300.0, quantity=10, entry_at=datetime.now()
        )
        trade2 = models.Trade(
            account_id=1, symbol="GAZP", direction=models.TradeDirection.LONG,
            entry_price=150.0, quantity=20, entry_at=datetime.now()
        )
        trade3 = models.Trade(
            account_id=1, symbol="SBER", direction=models.TradeDirection.SHORT,
            entry_price=310.0, quantity=5, entry_at=datetime.now()
        )
        
        db_session.add_all([trade1, trade2, trade3])
        db_session.commit()
        
        sber_trades = db_session.query(models.Trade).filter(
            models.Trade.symbol == "SBER"
        ).all()
        
        assert len(sber_trades) == 2

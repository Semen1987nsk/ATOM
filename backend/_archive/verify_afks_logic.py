import sys
import os
from datetime import datetime
import models

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from import_service import TradeManager

def verify_afks_logic():
    manager = TradeManager()

    # 1. Simulate Entry (Short) - Aggregated from 4 rows at 09:50:45
    # Total Qty: 7000
    # Total Sum: 98814.00
    # Total Comm: 39.52
    entry_trade = {
        "symbol": "AFKS",
        "asset_name": "AFK Sistema",
        "asset_type": "Stock",
        "direction": models.TradeDirection.SHORT,
        "entry_price": 98814.00 / 7000, # ~14.11628
        "quantity": 7000,
        "deal_sum": 98814.00,
        "entry_at": datetime(2025, 12, 11, 9, 50, 45),
        "commission": 39.52,
        "swap": 0,
        "notes": "Imported",
        "tags": ["Imported"]
    }

    print(f"Processing Entry: {entry_trade['direction']} {entry_trade['quantity']} @ {entry_trade['entry_price']:.4f} (Sum: {entry_trade['deal_sum']})")
    manager.process_trade(entry_trade)

    # 2. Simulate Exit (Buy) - Aggregated from 3 rows at 10:42:45
    # Total Qty: 7000
    # Total Sum: 98616.00
    # Total Comm: 39.44
    exit_trade = {
        "symbol": "AFKS",
        "asset_name": "AFK Sistema",
        "asset_type": "Stock",
        "direction": models.TradeDirection.LONG, # Buy to Close Short
        "entry_price": 98616.00 / 7000, # 14.088
        "quantity": 7000,
        "deal_sum": 98616.00,
        "entry_at": datetime(2025, 12, 11, 10, 42, 45),
        "commission": 39.44,
        "swap": 0,
        "notes": "Imported",
        "tags": ["Imported"]
    }

    print(f"Processing Exit:  {exit_trade['direction']} {exit_trade['quantity']} @ {exit_trade['entry_price']:.4f} (Sum: {exit_trade['deal_sum']})")
    manager.process_trade(exit_trade)

    # 3. Verify Results
    print("\n=== FULL TRADE DETAILS (DATABASE RECORD) ===")
    if manager.completed_trades:
        t = manager.completed_trades[0]
        
        # Simulate what would be in the DB (filling defaults)
        display_trade = {
            "id": 1, # Simulated ID
            "symbol": t['symbol'],
            "direction": t['direction'],
            "status": "CLOSED",
            "entry_at": t['entry_at'],
            "entry_price": t['entry_price'],
            "quantity": t['quantity'],
            "deal_sum_entry": t.get('deal_sum', 0) + (t['pnl'] if t['direction'] == models.TradeDirection.SHORT else -t['pnl']), # Reconstruct for display
            "exit_at": t['exit_at'],
            "exit_price": t['exit_price'],
            "exit_reason": t['exit_reason'], # "Manual" by default from import
            "pnl": t['pnl'],
            "commission": t['commission'],
            "swap": t.get('swap', 0),
            "net_pnl": t['net_pnl'],
            "setup_name": t.get('setup_name', None), # Empty on import
            "timeframe": t.get('timeframe', None),   # Empty on import
            "notes": t['notes'],
            "tags": t['tags'],
            "screenshot_url": None
        }

        for key, value in display_trade.items():
            print(f"{key}: {value}")

if __name__ == "__main__":
    verify_afks_logic()

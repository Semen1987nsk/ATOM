import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade

def check_second_trade():
    db = SessionLocal()
    try:
        # Get all trades ordered by time
        trades = db.query(Trade).order_by(Trade.entry_at, Trade.id).all()
        
        if len(trades) < 2:
            print("Not enough trades found.")
            return

        # The first one is AFKS (index 0)
        # The second one is index 1
        t2 = trades[1]
        
        print(f"=== TRADE #2 DETAILS ===")
        print(f"ID: {t2.id}")
        print(f"Symbol: {t2.symbol}")
        print(f"Asset Name: {t2.asset_name}")
        print(f"Direction: {t2.direction}")
        print(f"Entry Time: {t2.entry_at}")
        print(f"Entry Price: {t2.entry_price}")
        print(f"Quantity: {t2.quantity}")
        print(f"Commission: {t2.commission}")
        print(f"Swap: {t2.swap}")
        print(f"PnL: {t2.pnl}")
        print(f"Exit Time: {t2.exit_at}")
        print(f"Exit Price: {t2.exit_price}")
        print(f"Exit Reason: {t2.exit_reason}")
        
        # Let's also peek at the next few to see the context (is it a series of adds?)
        print("\n--- Next Trades Context ---")
        for i in range(2, min(5, len(trades))):
            t = trades[i]
            print(f"#{i+1} {t.symbol} {t.direction} Qty:{t.quantity} Time:{t.entry_at}")

    finally:
        db.close()

if __name__ == "__main__":
    check_second_trade()

import sys
import os
from sqlalchemy import extract

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade

def check_sofl_trade():
    db = SessionLocal()
    try:
        # Find SOFL trade on Dec 11 around 10:44
        trade = db.query(Trade).filter(
            Trade.symbol.like('%SOFL%'),
            extract('year', Trade.entry_at) == 2025,
            extract('month', Trade.entry_at) == 12,
            extract('day', Trade.entry_at) == 11,
            extract('hour', Trade.entry_at) == 10
        ).first()
        
        if not trade:
            print("SOFL trade not found.")
            return

        print(f"=== SOFL TRADE DETAILS ===")
        print(f"ID: {trade.id}")
        print(f"Symbol: {trade.symbol}")
        print(f"Asset Name: {trade.asset_name}")
        print(f"Direction: {trade.direction}")
        print(f"Entry Time: {trade.entry_at}")
        print(f"Entry Price: {trade.entry_price}")
        print(f"Quantity: {trade.quantity}")
        print(f"Commission: {trade.commission}")
        print(f"Swap: {trade.swap}")
        print(f"PnL: {trade.pnl}")
        print(f"Exit Time: {trade.exit_at}")
        print(f"Exit Price: {trade.exit_price}")
        print(f"Exit Reason: {trade.exit_reason}")

    finally:
        db.close()

if __name__ == "__main__":
    check_sofl_trade()

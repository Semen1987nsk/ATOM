import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade
from sqlalchemy import extract

def check_afks_merged():
    db = SessionLocal()
    try:
        # Search for AFKS trade on 2025-12-11
        trade = db.query(Trade).filter(
            Trade.symbol.like('%AFKS%'),
            extract('year', Trade.entry_at) == 2025,
            extract('month', Trade.entry_at) == 12,
            extract('day', Trade.entry_at) == 11
        ).order_by(Trade.entry_at, Trade.id).first()

        if not trade:
            print("No AFKS trade found for 2025-12-11.")
            return

        print("=== TARGET TRADE DETAILS (AFKS 11 Dec) ===")
        print(f"ID: {trade.id}")
        print(f"Symbol: {trade.symbol}")
        print(f"Direction: {trade.direction}")
        print(f"Entry Time: {trade.entry_at}")
        print(f"Exit Time: {trade.exit_at}")
        print(f"Entry Price: {trade.entry_price}")
        print(f"Exit Price: {trade.exit_price}")
        print(f"Quantity: {trade.quantity}")
        print(f"PnL: {trade.pnl}")
        print(f"Exit Reason: {trade.exit_reason}")

    finally:
        db.close()

if __name__ == "__main__":
    check_afks_merged()

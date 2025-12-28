import sys
import os
from sqlalchemy import extract

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade

def get_afks_full():
    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == 9).first()
        if trade:
            print(f"Symbol: {trade.symbol}")
            print(f"Asset Name: {trade.asset_name}")
            print(f"Direction: {trade.direction}")
            print(f"Entry Time: {trade.entry_at}")
            print(f"Exit Time: {trade.exit_at}")
            print(f"Entry Price: {trade.entry_price}")
            print(f"Exit Price: {trade.exit_price}")
            print(f"Quantity: {trade.quantity}")
            print(f"PnL: {trade.pnl}")
            print(f"Commission: {trade.commission}")
            print(f"Swap: {trade.swap}")
            print(f"Exit Reason: {trade.exit_reason}")
            print(f"Tags: {trade.tags}")
            print(f"Notes: {trade.notes}")
    finally:
        db.close()

if __name__ == "__main__":
    get_afks_full()

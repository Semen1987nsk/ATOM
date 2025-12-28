import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade
from sqlalchemy import extract

def get_first_trade_details():
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
        print(f"Asset Name: {trade.asset_name}")
        print(f"Asset Type: {trade.asset_type}")
        print(f"Direction: {trade.direction.value if hasattr(trade.direction, 'value') else trade.direction}")
        print(f"Entry Date: {trade.entry_at}")
        print(f"Quantity: {trade.quantity}")
        print(f"Entry Price: {trade.entry_price}")
        print(f"Commission: {trade.commission}")
        print(f"PnL: {trade.pnl}")
        print("===========================")

    finally:
        db.close()

if __name__ == "__main__":
    get_first_trade_details()

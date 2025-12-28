import sys
import os
from datetime import timedelta

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade
from sqlalchemy import extract

def check_next_trades():
    db = SessionLocal()
    try:
        # 1. Find the AFKS trade we just looked at (reference point)
        afks_trade = db.query(Trade).filter(
            Trade.symbol.like('%AFKS%'),
            extract('year', Trade.entry_at) == 2025,
            extract('month', Trade.entry_at) == 12,
            extract('day', Trade.entry_at) == 11
        ).order_by(Trade.entry_at, Trade.id).first()

        if not afks_trade:
            print("Reference AFKS trade not found.")
            # Fallback: just print the first 5 trades
            trades = db.query(Trade).order_by(Trade.entry_at, Trade.id).limit(5).all()
        else:
            print(f"Reference Trade: ID {afks_trade.id} | {afks_trade.symbol} | {afks_trade.entry_at}")
            
            # 2. Get trades that happened after or at the same time (but higher ID)
            # We want the NEXT trade in the sequence.
            trades = db.query(Trade).filter(
                Trade.entry_at >= afks_trade.entry_at,
                Trade.id != afks_trade.id
            ).order_by(Trade.entry_at, Trade.id).limit(3).all()

        print("\n=== NEXT TRADES IN SEQUENCE ===")
        for i, trade in enumerate(trades):
            print(f"\n--- Trade #{i+1} ---")
            print(f"ID: {trade.id}")
            print(f"Symbol: {trade.symbol}")
            print(f"Asset Name: {trade.asset_name}")
            print(f"Direction: {trade.direction}")
            print(f"Entry Time: {trade.entry_at}")
            print(f"Quantity: {trade.quantity}")
            print(f"Price: {trade.entry_price}")
            print(f"Commission: {trade.commission}")
            print(f"PnL: {trade.pnl}")

    finally:
        db.close()

if __name__ == "__main__":
    check_next_trades()

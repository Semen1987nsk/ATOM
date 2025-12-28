import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade
from sqlalchemy import extract

def get_first_trade():
    db = SessionLocal()
    try:
        # Search for AFKS trade on 2025-12-11
        trades = db.query(Trade).filter(
            Trade.symbol.like('%AFKS%'),
            extract('year', Trade.entry_at) == 2025,
            extract('month', Trade.entry_at) == 12,
            extract('day', Trade.entry_at) == 11
        ).order_by(Trade.entry_at, Trade.id).all()

        if not trades:
            print("No AFKS trade found for 2025-12-11.")
            return

        print(f"Found {len(trades)} trades for AFKS on 11.12.2025:")
        for t in trades:
            print(f"ID: {t.id} | Time: {t.entry_at} | Qty: {t.quantity} | Price: {t.entry_price} | Dir: {t.direction}")

    finally:
        db.close()

if __name__ == "__main__":
    get_first_trade()

import sys
import os
from sqlalchemy import extract

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Trade

def check_afks_net_pnl():
    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == 9).first()
        if trade:
            print(f"Symbol: {trade.symbol}")
            print(f"PnL (Gross): {trade.pnl}")
            print(f"Commission: {trade.commission}")
            print(f"Swap: {trade.swap}")
            print(f"Net PnL: {trade.net_pnl}")
            
            expected_net = float(trade.pnl) - float(trade.commission) - float(trade.swap)
            print(f"Calculated Net: {expected_net}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_afks_net_pnl()

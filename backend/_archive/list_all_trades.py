from database import SessionLocal
from models import Trade
import sys

def list_trades():
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(Trade.entry_at).all()
        print(f"Found {len(trades)} trades.")
        for t in trades:
            print(f"ID: {t.id} | Date: {t.entry_at} | Symbol: {t.symbol} | Side: {t.direction.value} | Qty: {t.quantity} | Price: {t.entry_price} | PnL: {t.pnl}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_trades()

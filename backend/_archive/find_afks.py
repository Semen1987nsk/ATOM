from database import SessionLocal
from models import Trade
from sqlalchemy import or_, text

def list_trades():
    db = SessionLocal()
    try:
        # Search for AFKS or dates around Dec 11
        print("Searching for AFKS trades...")
        trades = db.query(Trade).filter(
            or_(
                Trade.symbol.ilike("%AFKS%"),
                Trade.symbol.ilike("%АФК%"),
                Trade.symbol.ilike("%System%")
            )
        ).order_by(Trade.entry_at).all()
        
        if trades:
            print(f"Found {len(trades)} trades for AFK Sistema.")
            for t in trades:
                print(f"ID: {t.id} | Date: {t.entry_at} | Symbol: {t.symbol} | Side: {t.direction.value} | Qty: {t.quantity} | Price: {t.entry_price} | PnL: {t.pnl}")
        else:
            print("No AFKS trades found.")

        print("-" * 50)
        print("Checking for any trades on Dec 11 (any year):")
        # SQLite specific date filtering might vary, using string matching for simplicity in this script
        # Assuming entry_at is stored as datetime, we might need to cast or filter by range
        
        # Let's just get all trades and filter in python to be safe with sqlite/datetime quirks
        all_trades = db.query(Trade).order_by(Trade.entry_at).all()
        found_dec11 = False
        for t in all_trades:
            if t.entry_at.month == 12 and t.entry_at.day == 11:
                print(f"ID: {t.id} | Date: {t.entry_at} | Symbol: {t.symbol} | Side: {t.direction.value} | Qty: {t.quantity} | Price: {t.entry_price} | PnL: {t.pnl}")
                found_dec11 = True
        
        if not found_dec11:
            print("No trades found on Dec 11.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_trades()
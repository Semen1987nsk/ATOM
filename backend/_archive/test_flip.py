from sqlalchemy.orm import Session
import database
import models
import schemas
import main
from datetime import datetime
import time

# Setup DB
database.init_db()
db = database.SessionLocal()

# 1. Cleanup previous tests
db.query(models.Trade).filter(models.Trade.symbol == "TEST_FLIP").delete()
db.commit()

print("--- STEP 1: Open Short Position (Qty 100) ---")
trade1_data = schemas.TradeCreate(
    account_id=1,
    symbol="TEST_FLIP",
    direction=models.TradeDirection.SHORT,
    entry_price=100.0,
    quantity=100,
    entry_at=datetime.now(),
    setup_name="Initial Short"
)
trade1 = main.create_trade(trade1_data, db)
print(f"Trade 1 Created: ID={trade1.id}, Direction={trade1.direction}, Qty={trade1.quantity}, Status={'OPEN' if not trade1.exit_at else 'CLOSED'}")

time.sleep(1) # Ensure timestamp diff

print("\n--- STEP 2: Open Long Position (Qty 150) ---")
# We buy 150. This should close the 100 Short and open 50 Long.
trade2_data = schemas.TradeCreate(
    account_id=1,
    symbol="TEST_FLIP",
    direction=models.TradeDirection.LONG,
    entry_price=90.0,
    quantity=150, # 100 to close, 50 to open
    entry_at=datetime.now(),
    setup_name="Flip to Long"
)
# This function call handles the logic
result_trade = main.create_trade(trade2_data, db)

print("\n--- STEP 3: Verify Intermediate State ---")
all_trades = db.query(models.Trade).filter(models.Trade.symbol == "TEST_FLIP").order_by(models.Trade.id).all()
for t in all_trades:
    status = "OPEN" if not t.exit_at else "CLOSED"
    print(f"ID: {t.id} | {t.direction.value.upper()} | Qty: {t.quantity} | Entry: {t.entry_price} | Exit: {t.exit_price} | Status: {status}")

time.sleep(1)

print("\n--- STEP 4: Open Short Position (Qty 200) ---")
# We sell 200. This should close the 50 Long and open 150 Short.
trade3_data = schemas.TradeCreate(
    account_id=1,
    symbol="TEST_FLIP",
    direction=models.TradeDirection.SHORT,
    entry_price=80.0,
    quantity=200, # 50 to close, 150 to open
    entry_at=datetime.now(),
    setup_name="Flip back to Short"
)
main.create_trade(trade3_data, db)

print("\n--- STEP 5: Verify Final State ---")
all_trades = db.query(models.Trade).filter(models.Trade.symbol == "TEST_FLIP").order_by(models.Trade.id).all()
for t in all_trades:
    status = "OPEN" if not t.exit_at else "CLOSED"
    print(f"ID: {t.id} | {t.direction.value.upper()} | Qty: {t.quantity} | Entry: {t.entry_price} | Exit: {t.exit_price} | Status: {status}")
    if status == "CLOSED":
        pnl = t.pnl if t.pnl is not None else "N/A"
        print(f"   -> PnL: {pnl}")

db.close()

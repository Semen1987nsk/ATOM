import sqlite3
import os
from datetime import datetime

# Connect to database
db_path = 'atom.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Query for AFKS trades around Dec 11
cursor.execute("""
    SELECT * FROM trades 
    WHERE symbol LIKE '%AFKS%' 
    ORDER BY entry_at
""")

trades = cursor.fetchall()

print(f"Found {len(trades)} AFKS trades.")

for trade in trades:
    entry_date = datetime.fromisoformat(trade['entry_at'])
    if entry_date.month == 12 and entry_date.day == 11:
        print("-" * 50)
        print(f"ID: {trade['id']}")
        print(f"Symbol: {trade['symbol']}")
        print(f"Direction: {trade['direction']}")
        print(f"Entry: {trade['entry_at']} @ {trade['entry_price']}")
        print(f"Exit: {trade['exit_at']} @ {trade['exit_price']}")
        print(f"Qty: {trade['quantity']}")
        print(f"Total Comm: {trade['commission']}")
        print(f"Entry Comm: {trade['entry_commission']}")
        print(f"Exit Comm: {trade['exit_commission']}")
        print(f"PnL: {trade['pnl']}")
        print(f"Net PnL: {trade['net_pnl']}")
        print("-" * 50)

conn.close()

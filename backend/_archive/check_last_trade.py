import sqlite3
from datetime import datetime

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT entry_at, symbol, direction FROM trades ORDER BY entry_at DESC LIMIT 1")
    row = cursor.fetchone()
    
    if row:
        print(f"Last trade found: {row[0]} - {row[1]} ({row[2]})")
    else:
        print("No trades found in database.")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

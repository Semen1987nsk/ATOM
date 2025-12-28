import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT entry_at, symbol, direction, quantity, entry_price FROM trades WHERE symbol='RU000A0DKVS5' ORDER BY entry_at")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} trades for RU000A0DKVS5:")
    for row in rows:
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

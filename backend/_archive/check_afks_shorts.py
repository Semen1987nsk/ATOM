import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM trades WHERE symbol='AFKS' AND direction='short' LIMIT 5")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} SHORT trades for AFKS:")
    for row in rows:
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

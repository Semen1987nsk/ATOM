import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT symbol, COUNT(*) FROM trades WHERE direction='SHORT' GROUP BY symbol")
    rows = cursor.fetchall()
    
    print("Symbols with SHORT trades:")
    for row in rows:
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

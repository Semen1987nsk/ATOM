import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT direction, COUNT(*) FROM trades GROUP BY direction")
    rows = cursor.fetchall()
    
    print("Trades by direction:")
    for row in rows:
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

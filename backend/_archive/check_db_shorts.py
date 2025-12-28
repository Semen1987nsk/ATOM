import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM trades WHERE direction='short'")
    count = cursor.fetchone()[0]
    
    print(f"Short trades in DB: {count}")
    
    if count > 0:
        cursor.execute("SELECT * FROM trades WHERE direction='short' LIMIT 5")
        rows = cursor.fetchall()
        print("Sample Short trades:")
        for row in rows:
            print(row)
            
    conn.close()
except Exception as e:
    print(f"Error: {e}")

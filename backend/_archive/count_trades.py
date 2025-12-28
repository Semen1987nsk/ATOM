import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM trades")
    count = cursor.fetchone()[0]
    
    print(f"Total trades in DB: {count}")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

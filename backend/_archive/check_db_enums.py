import sqlite3

try:
    conn = sqlite3.connect('backend/atom.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT direction FROM trades")
    rows = cursor.fetchall()
    print("Distinct directions in DB:")
    for row in rows:
        print(f"'{row[0]}'")
            
    conn.close()
except Exception as e:
    print(f"Error: {e}")

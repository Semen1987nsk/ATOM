import sqlite3

def add_confidence_column():
    db_path = "atom.db" # Relative to current dir
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN confidence INTEGER")
        conn.commit()
        print("Successfully added 'confidence' column to trades table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column 'confidence' already exists.")
        else:
            print(f"Error adding column: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_confidence_column()

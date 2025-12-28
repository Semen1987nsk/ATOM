import sqlite3

def add_comm_columns():
    db_path = "atom.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    columns = [
        ("entry_commission", "NUMERIC"),
        ("exit_commission", "NUMERIC")
    ]
    
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
            print(f"Successfully added '{col_name}' column.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"Column '{col_name}' already exists.")
            else:
                print(f"Error adding column {col_name}: {e}")
                
    conn.commit()
    conn.close()

if __name__ == "__main__":
    add_comm_columns()

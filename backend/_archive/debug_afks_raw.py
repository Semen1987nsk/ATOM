import pandas as pd
import io
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

def inspect_afks_rows():
    file_path = "../broker-report-2025-12-01-2025-12-23.xlsx"
    print(f"Reading {file_path}...")
    
    with open(file_path, "rb") as f:
        contents = f.read()
        
    df = pd.read_excel(io.BytesIO(contents), header=None)
    
    start_row = -1
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "Номер сделки" in row_str and "Вид сделки" in row_str:
            start_row = i
            break
            
    if start_row == -1:
        print("Could not find header row")
        return

    df = pd.read_excel(io.BytesIO(contents), header=start_row)
    
    # Find columns
    cols = {c.replace('\n', ' ').strip(): c for c in df.columns}
    print("Columns found:", cols.keys())
    
    symbol_col = cols.get('Код актива')
    date_col = cols.get('Дата заключения')
    time_col = cols.get('Время')
    price_col = cols.get('Цена за единицу')
    qty_col = cols.get('Количество')
    sum_col = cols.get('Сумма сделки')
    side_col = cols.get('Вид сделки')
    comm_col = cols.get('Комиссия  брокера')
    
    print(f"Using columns: Symbol='{symbol_col}', Date='{date_col}', Time='{time_col}', Price='{price_col}', Sum='{sum_col}', Side='{side_col}', Comm='{comm_col}'")

    # Filter for AFKS on 11.12.2025
    print("\n--- RAW ROWS FOR AFKS 11.12.2025 ---")
    for i, row in df.iterrows():
        s = str(row[symbol_col]).strip()
        d = str(row[date_col])
        
        if 'AFKS' in s and '11.12.2025' in d:
            t = str(row[time_col])
            p = row[price_col]
            q = row[qty_col]
            sm = row[sum_col]
            side = row[side_col]
            comm = row[comm_col]
            print(f"Row {i}: Time={t}, Side={side}, Price={p}, Qty={q}, Sum={sm}, Comm={comm}")

if __name__ == "__main__":
    inspect_afks_rows()

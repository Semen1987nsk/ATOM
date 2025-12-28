import pandas as pd
import sys

file_path = "/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.xlsx"

try:
    # Find Header
    df_raw = pd.read_excel(file_path, header=None)
    start_row = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "Номер сделки" in row_str and "Вид сделки" in row_str:
            start_row = i
            break
            
    if start_row == -1:
        print("Could not find headers.")
        sys.exit(1)

    # Load Data
    df = pd.read_excel(file_path, header=start_row)
    cols = {c.replace('\n', ' ').strip(): c for c in df.columns}
    
    code_col = cols.get('Код актива')
    side_col = cols.get('Вид сделки')
    
    target_code = "RU000A0DKVS5"
    
    # Filter for Novatek
    df_novatek = df[df[code_col] == target_code]
    
    print(f"=== ALL TRADES FOR {target_code} ===")
    for i, row in df_novatek.iterrows():
        side = str(row[side_col])
        date = row[cols.get('Дата заключения')]
        time = row[cols.get('Время')]
        qty = row[cols.get('Количество')]
        price = row[cols.get('Цена за единицу')]
        
        print(f"{date} {time} | {side} | Qty: {qty} | Price: {price}")

except Exception as e:
    print(f"Error: {e}")

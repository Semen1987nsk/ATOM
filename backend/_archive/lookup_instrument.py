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
    
    # Normalize columns
    cols = {c.replace('\n', ' ').strip(): c for c in df.columns}
    
    code_col = cols.get('Код актива')
    name_col = cols.get('Наименование актива', cols.get('Наименование  актива')) # Note double space in previous output
    
    if not code_col or not name_col:
        print(f"Columns not found. Available: {list(cols.keys())}")
        sys.exit(1)
        
    # Filter
    target_code = "RU000A0DKVS5"
    match = df[df[code_col] == target_code]
    
    if not match.empty:
        name = match.iloc[0][name_col]
        print(f"Code: {target_code}")
        print(f"Name: {name}")
    else:
        print(f"Code {target_code} not found in file.")

except Exception as e:
    print(f"Error: {e}")

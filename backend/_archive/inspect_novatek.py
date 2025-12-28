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
    
    # Filter for the ISIN
    target_code = "RU000A0DKVS5"
    rows = df[df[code_col] == target_code]
    
    if not rows.empty:
        print(f"Found {len(rows)} rows for {target_code}:")
        for i, row in rows.iterrows():
            print(f"\nRow {i}:")
            for col_name, col_key in cols.items():
                val = row[col_key]
                if pd.notna(val):
                    print(f"  {col_name}: {val}")
    else:
        print(f"No rows found for {target_code}")

except Exception as e:
    print(f"Error: {e}")

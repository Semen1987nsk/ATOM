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
    
    side_col = cols.get('Вид сделки')
    
    # Filter for Sells that are NOT REPO
    # Convert to string, lower case
    sides = df[side_col].astype(str)
    
    # Find rows where side contains "продажа" but NOT "репо"
    sells = df[
        sides.str.contains('продажа', case=False, na=False) & 
        ~sides.str.contains('репо', case=False, na=False)
    ]
    
    print(f"Total Non-REPO Sells found: {len(sells)}")
    
    if not sells.empty:
        print("\nSample Sells:")
        print(sells[[cols.get('Дата заключения'), cols.get('Код актива'), side_col, cols.get('Количество')]].head(10).to_string())
    else:
        print("No real Sell trades found in the file.")

except Exception as e:
    print(f"Error: {e}")

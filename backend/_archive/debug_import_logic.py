import pandas as pd
import sys
import enum

class TradeDirection(enum.Enum):
    LONG = "long"
    SHORT = "short"

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
    
    print("Debugging Side Parsing:")
    
    count_long = 0
    count_short = 0
    count_skipped = 0
    
    for i, row in df.iterrows():
        side_val = row[side_col]
        side_str = str(side_val).lower()
        
        if 'репо' in side_str or 'рпс' in side_str:
            continue
            
        if 'покупка' in side_str:
            count_long += 1
        elif 'продажа' in side_str:
            count_short += 1
            if count_short <= 5:
                print(f"Row {i}: '{side_val}' -> SHORT")
        else:
            count_skipped += 1
            
    print(f"Total Long: {count_long}")
    print(f"Total Short: {count_short}")
    print(f"Total Skipped: {count_skipped}")

except Exception as e:
    print(f"Error: {e}")

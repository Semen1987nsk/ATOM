import pandas as pd
import io
from datetime import datetime
# import models # We don't need actual models for this test

def test_parse():
    file_path = "/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.xlsx"
    
    # Read Excel
    df_raw = pd.read_excel(file_path, header=None)
    start_row = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "Номер сделки" in row_str and "Вид сделки" in row_str:
            start_row = i
            break
            
    df = pd.read_excel(file_path, header=start_row)
    
    print(f"Loaded {len(df)} rows")
    
    cols = {c.replace('\n', ' ').strip(): c for c in df.columns}
    print(f"Side column: {cols.get('Вид сделки')}")
    
    count_long = 0
    count_short = 0
    
    for i, row in df.iterrows():
        side_val = row[cols.get('Вид сделки')]
        side_str = str(side_val).lower()
        
        if 'репо' in side_str: continue
        
        if 'покупка' in side_str:
            count_long += 1
        elif 'продажа' in side_str:
            count_short += 1
            if count_short <= 5:
                print(f"Found SHORT: {side_val} -> {side_str}")
        else:
            pass
            
    print(f"Total Long: {count_long}")
    print(f"Total Short: {count_short}")

if __name__ == "__main__":
    test_parse()

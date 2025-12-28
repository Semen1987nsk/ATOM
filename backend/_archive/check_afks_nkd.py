import sys
import os
import pandas as pd
import io

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_afks_nkd():
    file_path = "../broker-report-2025-12-01-2025-12-23.xlsx"
    with open(file_path, "rb") as f:
        content = f.read()
        
    df = pd.read_excel(io.BytesIO(content), header=None)
    
    start_row = -1
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "Номер сделки" in row_str and "Вид сделки" in row_str:
            start_row = i
            break
            
    df = pd.read_excel(io.BytesIO(content), header=start_row)
    
    print("=== AFKS NKD CHECK ===")
    
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "AFKS" in row_str and "11.12.2025" in row_str:
            cols = { " ".join(str(c).replace('\n', ' ').split()): c for c in df.columns }
            
            nkd = row[cols.get('НКД')]
            deal_sum = row[cols.get('Сумма сделки')]
            sum_no_nkd = row[cols.get('Сумма (без НКД)')]
            
            print(f"NKD: {nkd} | Deal Sum: {deal_sum} | Sum No NKD: {sum_no_nkd}")

if __name__ == "__main__":
    check_afks_nkd()

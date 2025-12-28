import sys
import os
import pandas as pd
import io

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_afks_entry_components():
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
    
    print("=== RAW AFKS ENTRY ROWS (09:50:45) ===")
    total_qty = 0
    total_deal_sum = 0
    
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "AFKS" in row_str and "11.12.2025" in row_str and "09:50:45" in row_str:
            cols = { " ".join(str(c).replace('\n', ' ').split()): c for c in df.columns }
            
            qty = float(row[cols.get('Количество')])
            price = float(row[cols.get('Цена за единицу')])
            deal_sum = float(row[cols.get('Сумма сделки')])
            
            print(f"Qty: {qty} | Price: {price} | Deal Sum: {deal_sum}")
            
            total_qty += qty
            total_deal_sum += deal_sum

    if total_qty > 0:
        avg_price = total_deal_sum / total_qty
        print(f"\nTotal Qty: {total_qty}")
        print(f"Total Deal Sum: {total_deal_sum}")
        print(f"Weighted Avg Price: {avg_price}")
        
        # Check Exit
        exit_price = 14.088
        pnl = (avg_price - exit_price) * total_qty
        print(f"Calculated PnL (Short): ({avg_price} - {exit_price}) * {total_qty} = {pnl}")

if __name__ == "__main__":
    check_afks_entry_components()

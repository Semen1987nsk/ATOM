import pandas as pd

try:
    # Read the excel file without header to inspect all rows
    df = pd.read_excel("/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.xlsx", header=None)
    
    # Find the row index where "Номер сделки" and "Вид сделки" appear
    start_row = -1
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "Номер сделки" in row_str and "Вид сделки" in row_str:
            start_row = i
            print(f"Found headers at row {i}")
            # Print the header row to identify column indices
            print(row.tolist())
            break
            
    if start_row != -1:
        print("\nFirst 10 data rows:")
        print(df.iloc[start_row+1:start_row+11].to_string())
    else:
        print("Could not find trade table headers.")

except Exception as e:
    print(f"Error reading Excel: {e}")

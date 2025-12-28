import pandas as pd
import sys

file_path = "/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.xlsx"

try:
    # 1. Find Header
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

    # 2. Load Data with Header
    df = pd.read_excel(file_path, header=start_row)
    
    # Normalize columns (remove newlines)
    df.columns = [c.replace('\n', ' ').strip() for c in df.columns]
    
    print("=== COLUMNS ===")
    for i, col in enumerate(df.columns):
        print(f"{i}: {col}")
        
    print("\n=== UNIQUE 'Вид сделки' ===")
    if 'Вид сделки' in df.columns:
        print(df['Вид сделки'].unique())
        
    print("\n=== UNIQUE 'Режим торгов' ===")
    if 'Режим торгов' in df.columns:
        print(df['Режим торгов'].unique())

    print("\n=== UNIQUE 'Код актива' ===")
    if 'Код актива' in df.columns:
        print(df['Код актива'].unique())

    print("\n=== SAMPLE ROW (First valid trade) ===")
    # Find a row that looks like a real trade (has date and symbol)
    sample = df[df['Код актива'].notna() & df['Дата заключения'].notna()].head(1)
    if not sample.empty:
        for col in df.columns:
            print(f"{col}: {sample.iloc[0][col]}")

    print("\n=== CHECKING FOR REPO/SWAP PATTERNS ===")
    # Show rows that might be REPO
    repo_rows = df[df['Вид сделки'].astype(str).str.contains('РЕПО', case=False, na=False)]
    if not repo_rows.empty:
        print(f"Found {len(repo_rows)} REPO rows. First one:")
        print(repo_rows.iloc[0].to_string())

except Exception as e:
    print(f"Error: {e}")

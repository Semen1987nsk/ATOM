import pandas as pd

try:
    df = pd.read_excel("/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.xlsx")
    print("Columns:", df.columns.tolist())
    print("First 5 rows:")
    print(df.head().to_string())
except Exception as e:
    print(f"Error reading Excel: {e}")

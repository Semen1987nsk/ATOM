import pandas as pd

try:
    df = pd.read_excel("TRADE J.xlsx", nrows=5)
    print("Columns in TRADE J.xlsx:")
    for col in df.columns:
        print(f"- {col}")
except Exception as e:
    print(f"Error reading TRADE J.xlsx: {e}")

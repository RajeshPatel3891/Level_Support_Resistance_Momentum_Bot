import os
import pandas as pd

# Search common paths for the CSV file
possible_paths = [
    'Harmonized_Trades_2026-07-21.csv',
    os.path.expanduser('~/Downloads/Harmonized_Trades_2026-07-21.csv'),
    os.path.expanduser('~/Downloads/Harmonized_Trades_2026-07-21 (1).csv'),
    '../Harmonized_Trades_2026-07-21.csv'
]

file_path = None
for path in possible_paths:
    if os.path.exists(path):
        file_path = path
        break

if not file_path:
    print("❌ Could not locate Harmonized_Trades_2026-07-21.csv in current directory or ~/Downloads/")
    exit(1)

print(f"✅ Found data file at: {file_path}")
df = pd.read_csv(file_path)

print("\n--- DATASET OVERVIEW ---")
print(f"Total Logged Rows: {len(df)}")
print(f"Unique Tickers: {df['ticker'].nunique()} ({', '.join(df['ticker'].unique())})")

print("\n--- EXIT STATUS BREAKDOWN ---")
print(df['exit_status'].value_counts().to_string())

print("\n--- REALIZED PNL SUM BY STATUS ---")
print(df.groupby('exit_status')['net_pnl'].sum().apply(lambda x: f"${x:,.2f}").to_string())

# Check for near-duplicate trade loops (same ticker, spot price, exit price, and pnl)
dup_subset = ['ticker', 'spot_price', 'exit_price', 'net_pnl']
duplicates_count = df.duplicated(subset=dup_subset, keep=False).sum()

print("\n--- DEDUPLICATION ANALYSIS ---")
print(f"Identical/Repeated Trade Logs: {duplicates_count} out of {len(df)} total rows")

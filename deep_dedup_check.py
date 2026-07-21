import pandas as pd

df = pd.read_csv('Harmonized_Trades_2026-07-21.csv')
df['ts'] = pd.to_datetime(df['timestamp'])
df = df.sort_values('ts')

print("=" * 70)
print("🔍 DEEP DEDUPLICATION PROBE (EXAMINE SOFI & AAPL RE-LOGS)")
print("=" * 70)

# Group by Ticker, Spot Price, Exit Status, Exit Price to see repeated DB entries
grouped = df.groupby(['ticker', 'spot_price', 'exit_status', 'exit_price', 'net_pnl'])

dup_clusters = 0
for name, group in grouped:
    if len(group) > 1:
        dup_clusters += 1
        ticker, spot, status, exit_p, pnl = name
        print(f"\n[CLUSTER #{dup_clusters}] {ticker} | Status: {status} | Spot: {spot} | Exit: {exit_p} | PnL: ${pnl:.2f}")
        print(f"Logged Count: {len(group)} times")
        
        # Calculate time diff between logged rows in seconds
        group = group.copy()
        group['sec_since_prev'] = group['ts'].diff().dt.total_seconds()
        
        print(group[['id', 'timestamp', 'sec_since_prev']].head(6).to_string(index=False))

print("\n" + "=" * 70)
print("📊 SUMMARY & VERDICT:")
print(f"Total Duplicate Clusters Found: {dup_clusters}")
print("=" * 70)

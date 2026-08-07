import pandas as pd
import os

TICKERS = ["SPY", "QQQ", "IWM"]

def extract_production_levels():
    print(f"{'Ticker':<8} | {'Price':<10} | {'SL':<10} | {'TP1':<10} | {'TP2':<10} | {'Note'}")
    print("-" * 80)
    
    for ticker in TICKERS:
        file = f"{ticker}_audit.csv"
        if os.path.exists(file):
            df = pd.read_csv(file)
            # Filter for High Conviction Execution Events
            execs = df[(df['Action'] == 'EXECUTE') & (df['Conviction'] == 'HIGH')]
            
            for _, row in execs.head(5).iterrows():
                print(f"{ticker:<8} | {row['Price']:<10.2f} | {float(row['SL']):<10.2f} | {float(row['TP1']):<10.2f} | {float(row['TP2']):<10.2f} | {row['Notes'][:30]}")

if __name__ == "__main__":
    extract_production_levels()

import pandas as pd
import os

TICKERS = ["SPY", "IWM", "QQQ", "GOOGL", "AMZN", "AAPL", "NVDA", "TSLA"]

def debug_conviction():
    for ticker in TICKERS:
        file = f"{ticker}_audit.csv"
        if os.path.exists(file):
            df = pd.read_csv(file)
            # Show the top 3 reasons why the bot is passing
            print(f"--- {ticker} Failure Modes ---")
            print(df[df['Conviction'] != 'HIGH']['Notes'].value_counts().head(3))
            print("\n")

if __name__ == "__main__":
    debug_conviction()

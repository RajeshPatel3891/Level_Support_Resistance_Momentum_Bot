import csv
import os

TICKERS = ["SPY", "IWM", "QQQ", "GOOGL", "AMZN", "AAPL", "NVDA", "TSLA"]

def analyze_audit():
    print("DEBUG: Starting Native Python Audit...")
    for ticker in TICKERS:
        file_path = f'{ticker}_audit.csv'
        if not os.path.exists(file_path):
            print(f"DEBUG: {file_path} MISSING.")
            continue
        
        high_conv_count = 0
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Conviction') == 'HIGH':
                    high_conv_count += 1
        
        print(f"Ticker: {ticker} | HIGH Conviction found: {high_conv_count}")

if __name__ == "__main__":
    analyze_audit()

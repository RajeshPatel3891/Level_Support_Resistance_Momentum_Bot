import os
import csv
import sys

TICKERS = ["SPY", "QQQ", "NVDA", "IWM", "AMZN", "AAPL", "MSFT", "TSLA"]

def display_ledger(ticker):
    # Cross-compatible lookup to find audits in root or /src paths
    possible_paths = [
        f"{ticker}_audit.csv",
        os.path.join("src", f"{ticker}_audit.csv")
    ]
    
    filename = None
    for path in possible_paths:
        if os.path.exists(path):
            filename = path
            break
            
    if not filename:
        print(f"[─] No ledger file found for {ticker}. Expected to find {ticker}_audit.csv")
        return

    print(f"\n=====================================================================")
    print(f" HARM.AI // RAW TRANSACTION LEDGER FOR: {ticker} ")
    print(f"=====================================================================")
    
    with open(filename, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        
        row_format = "{:<20} | {:<10} | {:<8} | {:<10} | {:<12}"
        print(row_format.format("Timestamp", "Price", "Action", "Conviction", "Outcome"))
        print("-" * 69)
        
        trade_count = 0
        for row in reader:
            if not row: continue
            timestamp, price, action, conviction, outcome, notes = row
            # Format raw datetime strings into clean timestamps
            clean_time = timestamp.split(".")[0].replace("T", " ") if "T" in timestamp else timestamp
            print(row_format.format(clean_time[:19], f"${float(price):.2f}", action, conviction, outcome))
            trade_count += 1
            
        if trade_count == 0:
            print("  No transactions recorded in this file.")
            
    print("=====================================================================\n")

if __name__ == "__main__":
    target = sys.argv[1].upper() if len(sys.argv) > 1 else "SPY"
    if target in TICKERS:
        display_ledger(target)
    else:
        print(f"[!] Invalid ticker. Choose from: {', '.join(TICKERS)}")

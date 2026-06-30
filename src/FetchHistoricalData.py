import json, os, sys
from massive import RESTClient

# Scalable Portfolio List
TICKERS = ["IWM", "QQQ", "GOOGL", "AMZN", "AAPL", "NVDA", "TSLA", "SPY"]
TARGET_DATE = "2026-06-26"

api_key = os.getenv("MASSIVE_API_KEY")
client = RESTClient(api_key=api_key)

def fetch_ticker_data(ticker):
    filename = f"{ticker}_{TARGET_DATE}.json"
    print(f"DEBUG: Streaming trades for {ticker} to: {filename}")

    try:
        with open(filename, "w") as f:
            f.write("[") # Start JSON array
            first = True
            count = 0
            
            # Generator for trades - streams page-by-page
            for trade in client.list_trades(ticker=ticker, timestamp=TARGET_DATE, limit=50000, sort="asc"):
                if not first:
                    f.write(",")
                
                # Ensure we handle the trade object correctly
                trade_data = trade.__dict__ if hasattr(trade, "__dict__") else trade
                json.dump(trade_data, f)
                first = False
                count += 1
                
                if count % 50000 == 0:
                    print(f"  {ticker}: Streamed {count} trades...")
                    sys.stdout.flush()
            
            f.write("]") # End JSON array
        print(f"SUCCESS: Finished streaming {count} trades for {ticker}.")
        
    except Exception as e:
        print(f"CRITICAL ERROR for {ticker}: {e}")

if __name__ == "__main__":
    for ticker in TICKERS:
        fetch_ticker_data(ticker)

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

def download_todays_action():
    print("[*] Contacting Alpaca Historical Archive...")
    if not API_KEY or not SECRET_KEY:
        print("[!] Aborting: Missing credentials.")
        return

    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    # Define targets from your architecture list
    tickers = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AMZN", "MSFT"]
    
    # Capture today's full session range (Eastern time baseline mapped to UTC)
    # Market Date: July 1, 2026
    start_time = datetime(2026, 7, 1, 13, 30) # 9:30 AM EDT in UTC
    end_time = datetime(2026, 7, 1, 21, 00)   # 5:00 PM EDT in UTC
    
    request_params = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Minute,
        start=start_time,
        end=end_time
    )
    
    try:
        print(f"[*] Extracting 1-minute OHLCV candles for: {tickers}")
        bars = client.get_stock_bars(request_params)
        
        # Convert into a simple JSON array structure for auditing
        output_data = {}
        for symbol, bar_list in bars.data.items():
            output_data[symbol] = [
                {
                    "time": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                }
                for bar in bar_list
            ]
            
        with open("todays_market_history.json", "w") as f:
            json.dump(output_data, f, indent=4)
            
        print("[+] Success! Historical session saved to 'todays_market_history.json'")
        
    except Exception as e:
        print(f"[!] Error pulling data archive: {e}")

if __name__ == "__main__":
    download_todays_action()

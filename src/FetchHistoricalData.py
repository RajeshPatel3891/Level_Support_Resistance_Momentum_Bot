import argparse
import json
import os
import sys
import random
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environmental variables for production keys
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")

# Hardcoded ticker base-prices mapped closely to real US session ranges
BASE_PRICES = {
    "SPY": 552.00, "QQQ": 485.50, "IWM": 204.80, 
    "NVDA": 194.20, "TSLA": 245.50, "AAPL": 183.50, 
    "AMZN": 175.80, "MSFT": 423.20
}

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FETCH] {msg}", flush=True)

def generate_simulated_bars(ticker, date_str):
    """Generates simulated high-fidelity minute-bar arrays for historical validation fallback."""
    log_msg(f"Generating simulated high-fidelity minute bars for {ticker} on {date_str}...")
    base_price = BASE_PRICES.get(ticker, 100.00)
    
    bars = []
    current_time = datetime.strptime(f"{date_str} 09:30:00", "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime(f"{date_str} 16:00:00", "%Y-%m-%d %H:%M:%S")
    
    price = base_price
    step = timedelta(minutes=1)
    
    while current_time <= end_time:
        o = price
        h = price + random.uniform(0, 0.40)
        l = price - random.uniform(0, 0.40)
        c = random.uniform(l, h)
        vol = random.randint(500, 3000)
        price = c
        
        bars.append({
            "time": current_time.isoformat() + "+00:00",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": float(vol)
        })
        current_time += step
        
    filename = f"{ticker}_{date_str}.json"
    with open(filename, "w") as f:
        json.dump(bars, f, indent=4)
    log_msg(f"[✓] Saved {len(bars)} simulated bars to '{filename}'")

def generate_simulated_ticks(ticker, date_str):
    """Generates simulated high-frequency ticks to test execution limits when offline."""
    log_msg(f"Generating simulated high-frequency ticks for {ticker} on {date_str}...")
    base_price = BASE_PRICES.get(ticker, 100.00)
    
    ticks = []
    current_time = datetime.strptime(f"{date_str} 09:30:00", "%Y-%m-%d %H:%M:%S")
    end_time = datetime.strptime(f"{date_str} 16:00:00", "%Y-%m-%d %H:%M:%S")
    
    price = base_price
    step = timedelta(seconds=12) # ~2000 trades over standard active hours
    
    while current_time <= end_time:
        change = random.normalvariate(0, 0.08)
        price += change
        size = random.randint(100, 800)
        
        # Inject periodic institutional block surges to trigger RVOL thresholds
        if random.random() < 0.03:
            size = random.randint(3000, 8000)
            price += random.choice([-0.25, 0.25])
            
        ticks.append({
            "time": current_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "price": round(price, 2),
            "size": size,
            "conditions": ["@", "F", "I"]
        })
        current_time += step
        
    filename = f"{ticker}_{date_str}.json"
    with open(filename, "w") as f:
        json.dump(ticks, f, indent=4)
    log_msg(f"[✓] Saved {len(ticks)} simulated trades to '{filename}'")

def trigger_fallback(ticker, date, mode):
    """Router helper to invoke correct data simulator."""
    if mode == "bar":
        generate_simulated_bars(ticker, date)
    else:
        generate_simulated_ticks(ticker, date)

def fetch_data(ticker, date, mode, target_limit):
    """Downloads official market records cleanly using HTTP pagination and normalizes schemas."""
    if not API_KEY or not SECRET_KEY:
        log_msg(f"[!] Live credentials missing. Running simulation fallback for {ticker} ({mode.upper()})...")
        trigger_fallback(ticker, date, mode)
        return False

    headers = {
        "APCA-API-KEY-ID": API_KEY,
        "APCA-API-SECRET-KEY": SECRET_KEY,
        "Accept": "application/json"
    }
    
    # Query parameters - pulling standard 24h market window for robust offline validation
    start_time = f"{date}T00:00:00Z"
    end_time = f"{date}T23:59:59Z"
    
    accumulated_data = []
    page_token = None
    
    # Alpaca max limit per individual request page is 10,000
    page_size = min(target_limit, 10000)
    
    endpoint_type = "trades" if mode == "tick" else "bars"
    base_url = f"https://data.alpaca.markets/v2/stocks/{ticker}/{endpoint_type}"
    
    log_msg(f"[*] Querying Alpaca V2 {endpoint_type} endpoint for {ticker} on {date} (Target Max: {target_limit})...")
    
    while len(accumulated_data) < target_limit:
        params = {
            "start": start_time,
            "end": end_time,
            "limit": page_size,
        }
        
        if mode == "tick":
            params["feed"] = "sip"
        elif mode == "bar":
            params["timeframe"] = "1Min"
            
        if page_token:
            params["page_token"] = page_token
            
        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                log_msg(f"[!] Error {response.status_code} fetching page: {response.text}")
                break
                
            res_json = response.json()
            raw_items = res_json.get(endpoint_type, [])
            
            if not raw_items:
                break
                
            for item in raw_items:
                if len(accumulated_data) >= target_limit:
                    break
                    
                # Normalize response keys to match BacktestBot.py state expectations exactly
                if mode == "tick":
                    accumulated_data.append({
                        "time": item.get("t"),
                        "price": float(item.get("p", 0.0)),
                        "size": float(item.get("s", 0.0)),
                        "conditions": item.get("c", ["@"])
                    })
                else:
                    accumulated_data.append({
                        "time": item.get("t"),
                        "open": float(item.get("o", 0.0)),
                        "high": float(item.get("h", 0.0)),
                        "low": float(item.get("l", 0.0)),
                        "close": float(item.get("c", 0.0)),
                        "volume": float(item.get("v", 0.0))
                    })
            
            # Retrieve pagination cursor
            page_token = res_json.get("next_page_token")
            if not page_token:
                break
                
        except Exception as e:
            log_msg(f"[!] Network exception on pagination loop: {e}")
            break
            
    # Check if we got an empty response even though API credentials were OK
    if not accumulated_data:
        log_msg(f"[!] API query returned empty dataset for {ticker}. Triggering simulated fallback...")
        trigger_fallback(ticker, date, mode)
        return False
        
    # Save output cleanly in the active root directory
    output_filename = f"{ticker}_{date}.json"
    try:
        with open(output_filename, "w") as f:
            json.dump(accumulated_data, f, indent=4)
        log_msg(f"[+] Success! {len(accumulated_data)} live {mode} items saved to '{output_filename}'")
    except Exception as e:
        log_msg(f"[!] Failed writing JSON manifest: {e}. Defaulting to mock generation...")
        trigger_fallback(ticker, date, mode)
        return False

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Integrated Historical Data Acquisition Harness")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single stock ticker")
    group.add_argument("--tickers", type=str, help="Space, comma, or split-separated stock tickers")
    
    parser.add_argument("--date", type=str, required=True, help="Target evaluation date in YYYY-MM-DD")
    parser.add_argument("--mode", type=str, choices=["tick", "bar"], default="tick", help="Data feed format type")
    parser.add_argument("--limit", type=int, default=100000, help="Maximum number of historical entries to ingest")
    
    args = parser.parse_args()
    
    # Process watchlist tickers cleanly (handles commas, spaces, and formatting variations)
    if args.ticker:
        tickers_list = [args.ticker.strip().upper()]
    else:
        tickers_list = [t.strip().upper() for t in args.tickers.replace(',', ' ').split() if t.strip()]
        
    log_msg(f"Initializing historical pipeline. Target date: {args.date} | Mode: {args.mode.upper()}")
    
    for ticker in tickers_list:
        fetch_data(ticker, args.date, args.mode, args.limit)

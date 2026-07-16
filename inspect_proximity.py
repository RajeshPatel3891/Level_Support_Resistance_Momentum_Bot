import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environmental variables (.env)
load_dotenv()

# Path configuration - Using 100% markdown-safe pathing (no double underscores)
CURRENT_DIR = os.getcwd()
LEVELS_FILE = os.path.join(CURRENT_DIR, 'trading_levels.json')

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_trading_levels():
    if not os.path.exists(LEVELS_FILE):
        log_msg(f"[!] Error: Unable to locate levels manifest at {LEVELS_FILE}")
        sys.exit(1)
    with open(LEVELS_FILE, 'r') as f:
        return json.load(f)

def get_live_snapshots(tickers, api_key, secret_key):
    """
    Fetches real-time price snapshots directly from Alpaca V2 market data API.
    Cascades through three distinct data feeds to bypass free/paper account blocks.
    """
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key
    }
    
    feeds = [
        {"url": f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={','.join(tickers)}", "name": "Standard SIP Feed (Premium)"},
        {"url": f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={','.join(tickers)}&feed=iex", "name": "Free Real-Time IEX Feed (Paper)"},
        {"url": f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={','.join(tickers)}&feed=delayed_sip", "name": "Delayed SIP Feed (Free)"}
    ]
    
    for feed in feeds:
        try:
            response = requests.get(feed["url"], headers=headers, timeout=10)
            if response.status_code == 200:
                payload = response.json()
                if payload and isinstance(payload, dict):
                    # Verify if any of our tickers exist as top-level keys in the response
                    if any(t in payload for t in tickers):
                        log_msg(f"[✓] Success: Retrieved live market ticks using {feed['name']}.")
                        return payload
                    else:
                        log_msg(f"[─] Feed '{feed['name']}' returned HTTP 200 but snapshots dictionary was empty.")
            else:
                log_msg(f"[─] Feed '{feed['name']}' rejected (HTTP {response.status_code}): {response.text.strip()}")
        except Exception as e:
            log_msg(f"[─] Connection exception on '{feed['name']}': {e}")
            
    return None

def inspect_system_proximity():
    print("\n" + "="*80)
    print(" HARM.AI // REAL-TIME HIGH-CONVICTION PROXIMITY AUDIT ")
    print("="*80)
    
    # Load keys
    api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    
    # Credential Check
    has_api_key = f"PRESENT (Starts with: '{api_key[:4]}...')" if api_key else "MISSING / EMPTY"
    has_secret_key = f"PRESENT (Starts with: '{secret_key[:4]}...')" if secret_key else "MISSING / EMPTY"
    
    log_msg(f"[*] Environmental Diagnostics:")
    log_msg(f"    • API Key Status   : {has_api_key}")
    log_msg(f"    • Secret Key Status: {has_secret_key}")
    print("-" * 80)
    
    if not api_key or not secret_key:
        print("[!] ERROR: Alpaca API credentials not found in your environment.")
        print("    Please ensure ALPACA_API_KEY and ALPACA_SECRET_KEY are set inside your .env file.")
        print("="*80 + "\n")
        sys.exit(1)
        
    manifest = load_trading_levels()
    levels_data = manifest.get("levels", {})
    tickers = [t for t in levels_data.keys() if t != "source"]
    
    # Query live prices
    log_msg(f"[*] Interrogating Alpaca live markets for: {', '.join(tickers)}...")
    snapshots = get_live_snapshots(tickers, api_key, secret_key)
    
    if not snapshots:
        print("-" * 80)
        print("[!] Warning: All Alpaca data feeds failed to authorize. Reverting to base frames.")
        print("[*] Please review the HTTP rejection messages above for resolution instructions.")
        print("="*80 + "\n")
        return

    print("-" * 80)
    row_format = "{:<8} | {:<13} | {:<11} | {:<11} | {:<14} | {:<12}"
    print(row_format.format("Ticker", "Support Floor", "Spot Price", "Distance", "Allowed Threshold", "Trigger Probability"))
    print("-" * 80)

    for ticker in tickers:
        config = levels_data[ticker]
        macro = config.get("algo_macro", {})
        support_list = macro.get("support", [])
        avg_vol = config.get("avg_volume", 1000)
        
        if not support_list:
            print(row_format.format(ticker, "No Support", "-", "-", "-", "0% (No Level)"))
            continue
            
        support_floor = float(support_list[0])
        
        # Extract live snapshot data with extreme safety checks for None values
        ticker_data = snapshots.get(ticker, {}) or {}
        latest_trade = ticker_data.get("latestTrade", {}) or {}
        latest_bar = ticker_data.get("latestBar", {}) or {}
        minute_bar = ticker_data.get("minuteBar", {}) or {}
        daily_bar = ticker_data.get("dailyBar", {}) or {}
        prev_daily_bar = ticker_data.get("prevDailyBar", {}) or {}
        
        # Determine spot price using a cascade of available pricing fields
        spot_price = 0.0
        if latest_trade and latest_trade.get("p"):
            spot_price = float(latest_trade.get("p"))
        elif minute_bar and minute_bar.get("c"):
            spot_price = float(minute_bar.get("c"))
        elif daily_bar and daily_bar.get("c"):
            spot_price = float(daily_bar.get("c"))
        elif prev_daily_bar and prev_daily_bar.get("c"):
            spot_price = float(prev_daily_bar.get("c"))
            
        # Extract volume
        curr_vol = 0.0
        if latest_bar and latest_bar.get("v"):
            curr_vol = float(latest_bar.get("v"))
        elif minute_bar and minute_bar.get("v"):
            curr_vol = float(minute_bar.get("v"))
            
        if spot_price == 0.0:
            print(row_format.format(ticker, f"${support_floor:.2f}", "Stale Price", "-", "-", "0.0% (STALE)"))
            continue
        
        # Calculate dynamicallowed threshold
        vol_surge = min(max(curr_vol / avg_vol, 1.0), 2.0) if avg_vol > 0 else 1.0
        allowed_dist = 2.50 * vol_surge
        
        dist = abs(spot_price - support_floor)
        
        # Calculate dynamic trigger probability percentage
        if dist <= allowed_dist:
            prob_pct = min(100.0, (1.0 - (dist / allowed_dist)) * 100.0)
        else:
            prob_pct = max(0.0, (1.0 - ((dist - allowed_dist) / support_floor)) * 100.0)
            
        # Color code status strings for high-impact human visualization
        if dist <= 2.50:
            status_str = f"✅ IN ZONE ({prob_pct:.1f}%)"
        elif dist <= allowed_dist:
            status_str = f"⚡ NEED VOL ({prob_pct:.1f}%)"
        else:
            status_str = f"❌ OUTSIDE ({prob_pct:.1f}%)"

        print(row_format.format(
            ticker, 
            f"${support_floor:.2f}", 
            f"${spot_price:.2f}", 
            f"${dist:.2f}", 
            f"${allowed_dist:.2f}", 
            status_str
        ))
        
    print("="*80)
    print("[*] Proximity scan complete. Execute at high probability targets.")
    print("="*80 + "\n")

# Run directly without standard python main double underscore blocks to avoid bold formatting traps
inspect_system_proximity()

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

import requests
import json
import sqlite3
from datetime import datetime
from src.GexReader import get_latest_gex_context

LOG_FILE = "src/gex_ab_test_results.log"

def run_ab_comparison(symbol):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    local_data = get_latest_gex_context(symbol)
    
    flash_alpha_label = "UNKNOWN"
    flash_alpha_val = 0.0
    latency_ms = None
    
    # Exact routing extracted from GexGateway.py
    flashalpha_url = f"https://lab.flashalpha.com/v1/exposure/gex/{symbol.upper()}"
    token = os.getenv('FLASHALPHA_TOKEN', 'mock_token')
    headers = {'X-Api-Key': token}
    
    # Targeting the next front-week options chain context
    params = {'expiration': '2026-07-24'} 
    
    start_time = datetime.now()
    try:
        r = requests.get(flashalpha_url, headers=headers, params=params, timeout=4.0)
        latency_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        if r.status_code == 200:
            res_data = r.json()
            
            # FlashAlpha payloads can structurally nest values. 
            # We try standard extraction; adjust keys if your payload uses 'net_gex' or 'total_gamma'
            flash_alpha_val = float(res_data.get("net_gex", res_data.get("total_gex", 0.0)))
            flash_alpha_label = "POSITIVE" if flash_alpha_val >= 0 else "NEGATIVE"
        else:
            flash_alpha_label = f"ERROR_HTTP_{r.status_code}"
            print(f"[-] FlashAlpha API response failed [{r.status_code}] for {symbol}: {r.text[:120]}")
    except Exception as e:
        flash_alpha_label = f"EXC_{type(e).__name__}"
        print(f"[-] Network Exception connection mapping for {symbol}: {e}")

    if not local_data:
        return

    local_val = local_data['net_gex']
    local_label = local_data['gex_label']
    
    magnitude_delta = abs(local_val - flash_alpha_val) if isinstance(flash_alpha_val, float) else 0.0
    sentiment_match = (local_label == flash_alpha_label)

    log_entry = (
        f"[{timestamp}] Ticker: {symbol} | Sentiment Match: {sentiment_match}\n"
        f"  -> Local Bridge: {local_label} (${local_val:,.2f}) | Cache Age: {local_data['timestamp']}\n"
        f"  -> FlashAlpha:   {flash_alpha_label} (${flash_alpha_val:,.2f}) | Network Latency: {f'{latency_ms:.1f}ms' if latency_ms else 'N/A'}\n"
        f"  -> Magnitude Variance: ${magnitude_delta:,.2f}\n"
        f"{'-'*70}\n"
    )

    with open(LOG_FILE, "a") as f:
        f.write(log_entry)
        
    print(f"[A/B TEST LOGGED] Done with {symbol}. Match Status: {sentiment_match}")

if __name__ == "__main__":
    print("[*] Launching Fixed-Route A/B Telemetry Sync...")
    for test_ticker in ["PLTR", "AAL"]:
        run_ab_comparison(test_ticker)

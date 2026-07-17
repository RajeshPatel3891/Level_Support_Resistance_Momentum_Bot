import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.active_risk_daemon import get_live_quote, execute_fast_exit

def simulate_tp():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print("=" * 95)
    print(f"🧪  HARM.AI // TAKE PROFIT END-TO-END EMULATOR")
    print("=" * 95)

    # 1. Fetch current quote to get actual live price
    quote = get_live_quote("NVDA", headers)
    if not quote:
        print("[-] Couldn't fetch quote. Is the market open?")
        return
        
    last_price = float(quote.get('last', 0.0))
    
    # 2. Spoof our cost basis to be 2% LOWER than current market price to force immediate TP status
    spoofed_basis = round(last_price * 0.98, 2)
    tp_pct = 0.01  # 1% target
    tp_price = round(spoofed_basis * (1 + tp_pct), 2)

    print(f"[*] Actual Live Price:   ${last_price:.2f}")
    print(f"[*] Spoofed Cost Basis:  ${spoofed_basis:.2f} (Simulated Entry)")
    print(f"[*] Take Profit Target:  ${tp_price:.2f} (+{tp_pct*100}%)")
    print("-" * 95)

    # 3. Evaluate matching logic
    if last_price >= tp_price:
        print(f"[🎯] MATCH! Live Price (${last_price:.2f}) is above Take Profit Target (${tp_price:.2f})!")
        print("[🚀] Testing exit routing payload...")
        execute_fast_exit(base_url, account_id, "NVDA", 1, headers)
    else:
        print("[-] Failed to force simulated trigger. Adjust parameters.")

if __name__ == "__main__":
    simulate_tp()

#!/usr/bin/env python3
"""
HARM.AI // LIVE CSO MOMENTUM EXIT INTEGRATION TEST
===============================================================================
Fetches live stock spot prices, option marks, and manifest support levels 
to evaluate real-time CSO momentum exits against active market data.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.extend([".", "src", "/app", "/app/src"])

MANIFEST_PATH = "trading_levels.json"
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_ACCESS_TOKEN")

def fetch_live_quote(symbol: str):
    if not TRADIER_TOKEN:
        print("[-] Error: Tradier API Token is missing from environment/env file.")
        return {}

    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    urls = [TRADIER_BASE_URL, "https://api.tradier.com/v1", "https://sandbox.tradier.com/v1"]
    
    for base_url in list(dict.fromkeys(urls)):
        try:
            r = requests.get(f"{base_url}/markets/quotes", params={"symbols": symbol}, headers=headers, timeout=4)
            if r.status_code == 200:
                data = r.json().get("quotes", {}).get("quote", {})
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict) and data.get("symbol"):
                    return data
        except Exception:
            pass
    return {}

def get_manifest_support(ticker: str) -> float:
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
                levels = data.get("levels", data)
                info = levels.get(ticker.upper(), {})
                sup = info.get("support_zone", [])
                if sup and isinstance(sup, list) and len(sup) >= 1:
                    return float(sup[0])
                return float(info.get("support", info.get("spot", 0.0)))
        except Exception:
            pass
    return 0.0

def evaluate_cso_momentum_exit(ticker, spot_price, support_level, option_pnl_pct, entry_price):
    """Reflects full CSO exit matrix: Profit Cap, GSG Trailing, Soft Band, and Low-Dollar Floor."""
    # 1. Tranche Scale-Out / Target Cap (+35% to +50%)
    if option_pnl_pct >= 35.0:
        trail_floor = round(entry_price * (1.0 + (option_pnl_pct - 10.0) / 100.0), 2)
        return "GSG_RATCHET_HIGH_WATER", f"Peak PnL +{option_pnl_pct:.1f}%! Trailing stop ratcheted to ${trail_floor:.2f}."

    # 2. GSG Arming Band (+12% to +34.9%)
    if option_pnl_pct >= 12.0:
        trail_floor = round(entry_price * 1.03, 2)
        return "GSG_TRAILING_ARMED", f"Option up +{option_pnl_pct:.1f}%. GSG active with breakeven+ floor at ${trail_floor:.2f}."

    # 3. Normal Variance Buffer (-7.9% to +11.9%)
    if -8.0 < option_pnl_pct < 12.0:
        return "HOLD", f"Option PnL ({option_pnl_pct:+.1f}%) within normal trade progression."

    # 4. CSO Soft-Stop Band (-8.0% to -19.9%)
    if -20.0 < option_pnl_pct <= -8.0:
        if support_level > 0 and spot_price < support_level:
            return "CSO_EARLY_MOMENTUM_CUT", f"Stock (${spot_price:.2f}) broke support (${support_level:.2f}). Cutting early at {option_pnl_pct:.1f}%!"
        else:
            return "HOLD", f"Option down {option_pnl_pct:.1f}%, but stock (${spot_price:.2f}) holding support (${support_level:.2f}). Filtering spread noise."

    # 5. Hard Safety Ceiling (<= -20.0%)
    return "HARD_STOP_20PCT", f"Hard safety floor breached ({option_pnl_pct:.1f}%)."

def run_live_cso_eval(ticker="SOFI"):
    ticker_u = ticker.upper()
    print("=" * 70)
    print(f"🧠 [LIVE CSO INTEGRATION TEST] Evaluating {ticker_u} Market Feeds")
    print("=" * 70)

    stock_q = fetch_live_quote(ticker_u)
    spot = float(stock_q.get("last") or stock_q.get("close") or 0.0)
    if spot <= 0:
        print(f"[-] Could not fetch live spot quote for {ticker_u}. Check API token permissions.")
        return

    support = get_manifest_support(ticker_u)
    if support <= 0:
        support = round(spot * 0.985, 2)

    entry_price = 0.24
    occ_symbol = f"{ticker_u}260828P00018000"
    
    opt_q = fetch_live_quote(occ_symbol)
    bid = float(opt_q.get("bid") or 0.0)
    ask = float(opt_q.get("ask") or 0.0)
    live_mark = round((bid + ask) / 2.0, 2) if (bid and ask) else float(opt_q.get("last") or entry_price)

    pnl_pct = ((live_mark - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

    verdict, reason = evaluate_cso_momentum_exit(ticker_u, spot, support, pnl_pct, entry_price)

    print(f"  ├─ Live Stock Spot   : ${spot:.2f}")
    print(f"  ├─ Support Target    : ${support:.2f}")
    print(f"  ├─ Contract Target   : {occ_symbol}")
    print(f"  ├─ Entry vs Live Mark: ${entry_price:.2f} ──► ${live_mark:.2f} ({pnl_pct:+.1f}%)")
    print(f"  ├─ CSO Decision      : {verdict}")
    print(f"  └─ Reasoning         : {reason}")
    print("=" * 70)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "SOFI"
    run_live_cso_eval(target)

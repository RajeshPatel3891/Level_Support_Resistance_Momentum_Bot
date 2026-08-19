#!/usr/bin/env python3
"""
HARM.AI // LIVE CSO & RISK ENGINE INTEGRATION TEST
===============================================================================
1. Evaluates real-time market feeds against SOFI for live GSG/CSO status.
2. Runs unit assertions verifying Low-Dollar Option Cushioning (<= $0.50),
   Downward Stop-Loss Ratchet Protection, and CSO Soft-Stop Momentum Cuts.
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

def calculate_dynamic_stop(entry_price, peak_price, stored_stop_loss=0.0, is_runner=False):
    """Mirror exact dynamic stop calculation from gex_exit_monitor.py."""
    peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

    if is_runner:
        cushion = 12.0 if peak_pnl_pct >= 100.0 else 10.0
        dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
        calculated_stop = round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
    elif peak_pnl_pct >= 35.0:
        calculated_stop = round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
    elif peak_pnl_pct >= 20.0:
        calculated_stop = round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
    elif peak_pnl_pct >= 12.0:
        calculated_stop = round(entry_price * 1.03, 2)
    else:
        if entry_price <= 0.50:
            calculated_stop = round(max(0.02, entry_price - 0.10), 2)
        else:
            calculated_stop = round(entry_price * 0.80, 2)

    return max(stored_stop_loss, calculated_stop)

def evaluate_cso_momentum_exit(ticker, spot_price, support_level, option_pnl_pct, entry_price):
    """Mirror exact exit decision tree from gex_exit_monitor.py."""
    if option_pnl_pct >= 35.0:
        trail_floor = round(entry_price * (1.0 + (option_pnl_pct - 10.0) / 100.0), 2)
        return "GSG_RATCHET_HIGH_WATER", f"Peak PnL +{option_pnl_pct:.1f}%! Trailing stop ratcheted to ${trail_floor:.2f}."

    if option_pnl_pct >= 12.0:
        trail_floor = round(entry_price * 1.03, 2)
        return "GSG_TRAILING_ARMED", f"Option up +{option_pnl_pct:.1f}%. GSG active with breakeven+ floor at ${trail_floor:.2f}."

    if -8.0 < option_pnl_pct < 12.0:
        return "HOLD", f"Option PnL ({option_pnl_pct:+.1f}%) within normal trade progression."

    if -20.0 < option_pnl_pct <= -8.0:
        if support_level > 0 and spot_price < support_level:
            return "CSO_EARLY_MOMENTUM_CUT", f"Stock (${spot_price:.2f}) broke support (${support_level:.2f}). Cutting early at {option_pnl_pct:.1f}%!"
        else:
            return "HOLD", f"Option down {option_pnl_pct:.1f}%, but stock (${spot_price:.2f}) holding support (${support_level:.2f}). Filtering spread noise."

    return "HARD_STOP_20PCT", f"Hard safety floor breached ({option_pnl_pct:.1f}%)."

def run_synthetic_feature_assertions():
    """Validates Low-Dollar Protection, Non-Decreasing Ratchet, and CSO Soft-Stop Cut."""
    print("\n" + "=" * 70)
    print("🧪 [FEATURE ASSERTION 1: LOW-DOLLAR OPTION PROTECTION]")
    print("=" * 70)
    entry = 0.24
    stop = calculate_dynamic_stop(entry_price=entry, peak_price=entry)
    print(f"  ├─ Entry Price : ${entry:.2f} (<= $0.50 Tier)")
    print(f"  ├─ Legacy Stop : ${entry * 0.80:.2f} (-20% / Stop-out on 5¢ spread wiggle)")
    print(f"  ├─ New Cushion : ${stop:.2f} ($0.10 Cushion / Absorbs spread noise)")
    assert stop == 0.14, f"Expected $0.14 stop floor, got ${stop}"
    print("  └─ [✓] ASSERTION PASSED")

    print("\n" + "=" * 70)
    print("🧪 [FEATURE ASSERTION 2: DOWNWARD RATCHET PROTECTION]")
    print("=" * 70)
    stored_stop = 0.31
    pulled_back_peak = 0.24  # Price drops back to entry
    new_stop = calculate_dynamic_stop(entry_price=entry, peak_price=pulled_back_peak, stored_stop_loss=stored_stop)
    print(f"  ├─ Stored Stop in DynamoDB : ${stored_stop:.2f}")
    print(f"  ├─ Pulled Back Peak Mark   : ${pulled_back_peak:.2f}")
    print(f"  ├─ Recalculated Floor      : ${new_stop:.2f}")
    assert new_stop == 0.31, f"Expected stop floor to remain $0.31, got ${new_stop}"
    print("  └─ [✓] ASSERTION PASSED: Dynamic stop did NOT ratchet downward!")

    print("\n" + "=" * 70)
    print("🧪 [FEATURE ASSERTION 3: CSO SOFT-STOP MOMENTUM CUT (-8% to -19.9%)]")
    print("=" * 70)
    ticker, spot, support, pnl = "SOFI", 18.00, 18.10, -12.5
    verdict, reason = evaluate_cso_momentum_exit(ticker, spot, support, pnl, entry_price=entry)
    print(f"  ├─ Stock Spot vs Support   : ${spot:.2f} < ${support:.2f} (Support Broken)")
    print(f"  ├─ Option PnL              : {pnl}% (Inside Soft Band -8% to -19.9%)")
    print(f"  ├─ CSO Decision            : {verdict}")
    print(f"  ├─ Reasoning               : {reason}")
    assert verdict == "CSO_EARLY_MOMENTUM_CUT", f"Expected CSO_EARLY_MOMENTUM_CUT, got {verdict}"
    print("  └─ [✓] ASSERTION PASSED: Cut trade early to prevent full -20% drawdown!")

def run_live_cso_eval(ticker="SOFI"):
    ticker_u = ticker.upper()
    print("\n" + "=" * 70)
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
    run_synthetic_feature_assertions()
    target = sys.argv[1] if len(sys.argv) > 1 else "SOFI"
    run_live_cso_eval(target)

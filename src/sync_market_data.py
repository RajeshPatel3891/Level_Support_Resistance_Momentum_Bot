#!/usr/bin/env python3
"""
HARM.AI // LIVE MARKET DATA & DYNAMIC ARMING STATE SYNC (24-TICKER S3 ALIGNED)
===============================================================================
1. Fetches live spot & VWAP quotes from Tradier API across all 24 matrix tickers.
2. Extracts active OCC option symbols from local SQLite telemetry DB.
3. Evaluates dynamic price-tiered proximity thresholds to calculate arming states.
4. Synchronizes updated levels atomically to disk, in-memory cache, and S3.
"""

import os
import sys
import json
import re
import requests
from dotenv import load_dotenv

# Pathing setup
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    from src.level_loader import save_trading_levels, load_trading_levels
except ImportError:
    from level_loader import save_trading_levels, load_trading_levels

if os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

# Complete 24-Ticker Live Price Fallback Matrix
LIVE_PRICES_FALLBACK = {
    "SPY": 550.00,  "QQQ": 480.00,  "IWM": 210.00,  "NVDA": 226.43,
    "TSLA": 341.66, "AAPL": 306.79, "AMZN": 180.00, "GOOGL": 165.00,
    "AMD": 140.00,  "META": 500.00, "NFLX": 620.00, "PLTR": 179.91,
    "SOFI": 18.33,  "F": 14.14,     "AAL": 15.48,   "INTC": 105.08,
    "RIVN": 15.59,  "HOOD": 22.00,  "BAC": 38.00,   "SNAP": 12.00,
    "MARA": 18.00,  "CCL": 16.00,   "UBER": 70.00,  "NKE": 80.00
}

TRADIER_TOKEN = (
    os.getenv("TRADIER_TOKEN") or 
    os.getenv("TRADIER_PROD_TOKEN") or 
    os.getenv("TRADIER_SANDBOX_TOKEN")
)
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
if "sandbox" in TRADIER_BASE_URL.lower():
    TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"

def get_dynamic_proximity_threshold(price: float) -> float:
    """Returns dynamic arming threshold based on asset price tier."""
    if price >= 100.0:
        return 0.0075  # 0.75% (, , )
    elif price >= 30.0:
        return 0.0085  # 0.85% (, )
    else:
        return 0.0120  # 1.20% (, , )

def is_armed(price: float, target: float, threshold: float, support: list = None, resistance: list = None) -> bool:
    """Dynamically arms execution route if spot is within dynamic proximity threshold of target or zone."""
    if price <= 0:
        return False
    
    if target and target > 0:
        gap_pct = abs(price - target) / price
        if gap_pct <= threshold:
            return True
            
    if support and len(support) >= 2 and (support[0] <= price <= support[1]):
        return True
    if resistance and len(resistance) >= 2 and (resistance[0] <= price <= resistance[1]):
        return True
        
    return False

def sync():
    data = load_trading_levels(force_refresh=True)
    if not data:
        print("[!] Failed to load trading levels from disk/S3.")
        return

    # Extract Active OCC Option Symbols from SQLite Telemetry DB
    active_occ_symbols = []
    try:
        import sqlite3
        db_path = 'harm_telemetry.db'
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('SELECT occ_symbol, cso_notes FROM trades WHERE exit_status="ACTIVE"')
            rows = c.fetchall()
            conn.close()
            for occ, notes in rows:
                if occ and len(str(occ).strip()) >= 15:
                    active_occ_symbols.append(str(occ).strip())
                elif notes and 'OCC:' in str(notes):
                    match = re.search(r'OCC:\s*([A-Z0-9]+)', str(notes))
                    if match:
                        active_occ_symbols.append(match.group(1))
    except Exception as e:
        print(f"[!] Error reading active OCC symbols: {e}")

    all_symbols = list(data.keys()) + active_occ_symbols
    symbols_str = ",".join(all_symbols)

    quotes = {}
    if TRADIER_TOKEN:
        headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
        try:
            r = requests.get(f"{TRADIER_BASE_URL}/markets/quotes", params={"symbols": symbols_str}, headers=headers, timeout=5)
            if r.status_code == 200:
                res_quotes = r.json().get('quotes', {}).get('quote', [])
                if isinstance(res_quotes, dict):
                    res_quotes = [res_quotes]
                for q in res_quotes:
                    quotes[q.get('symbol')] = q
        except Exception as e:
            print(f"[!] Tradier quote fetch exception: {e}")

    for ticker, val in data.items():
        if not isinstance(val, dict):
            continue

        q = quotes.get(ticker, {})
        default_fallback = LIVE_PRICES_FALLBACK.get(ticker, 0.0)
        
        spot = float(q.get('last') or q.get('close') or val.get('last_price') or default_fallback)
        vwap = float(q.get('vwap') or q.get('average_price') or 0.0)
        
        if vwap == 0.0 and spot > 0:
            vwap = spot
            
        val["last_price"] = spot
        val["spot"] = spot
        val["spot_price"] = spot
        val["vwap"] = vwap

        target = float(val.get('call_target') or val.get('spot_target_call') or (spot * 1.005))
        threshold = get_dynamic_proximity_threshold(spot)
        gap_pct = abs(spot - target) / spot if spot > 0 else 1.0

        sup = val.get("support_zone", val.get("support", [val.get("support_a", 0.0), val.get("support_b", 0.0)]))
        res = val.get("resistance_zone", val.get("resistance", [val.get("resistance_a", 0.0), val.get("resistance_b", 0.0)]))

        stale = False
        if sup and len(sup) > 0 and sup[0] > 0 and spot > 0:
            if abs(spot - sup[0]) / spot > 0.02:
                stale = True

        if (not sup or sup == [0.0, 0.0] or stale) and spot > 0:
            call_target = round(spot * 1.005, 2)
            put_target = round(spot * 0.995, 2)
            
            sup = [round(put_target * 0.99, 2), put_target]
            res = [call_target, round(call_target * 1.01, 2)]
            
            val["call_target"] = call_target
            val["put_target"] = put_target
            val["spot_target_call"] = call_target
            val["spot_target_put"] = put_target
            val["support_zone"] = sup
            val["resistance_zone"] = res

        if sup and isinstance(sup, list) and len(sup) > 0:
            val["support_a"] = sup[0]
            val["support_b"] = sup[1] if len(sup) > 1 else sup[0]
        if res and isinstance(res, list) and len(res) > 0:
            val["resistance_a"] = res[0]
            val["resistance_b"] = res[1] if len(res) > 1 else res[0]

        if spot > 0:
            armed = is_armed(spot, target, threshold, sup, res)
            val["proximity_threshold"] = threshold
            val["gap_pct"] = round(gap_pct * 100.0, 2)
            val["execution_armed"] = armed
            val["status"] = "ARMED" if armed else "WAITING"

    # Cloud-First Atomic Write: Disk + Memory Cache + S3
    save_trading_levels(data)
    print("[✓] Live Tradier market prices, VWAP, dynamic arming thresholds, and S3 levels synced!")

if __name__ == "__main__":
    sync()

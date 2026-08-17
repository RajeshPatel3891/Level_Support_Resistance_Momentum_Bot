#!/usr/bin/env python3
"""
HARM.AI // DYNAMIC GUARDRAIL LEVEL HARVESTER (24-TICKER MATRIX)
===============================================================================
1. Pulls live prices/targets from Proximity API or Tradier API.
2. Integrates GEX walls and dynamic price-tiered proximity thresholds.
3. Falls back to static baselines for off-hours testing across all 24 tickers.
4. Writes updated levels atomically to local disk, memory cache, and S3.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

# Pathing setup
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    from src.level_loader import save_trading_levels
except ImportError:
    from level_loader import save_trading_levels

try:
    from src.GexReader import get_latest_gex_context
except ImportError:
    try:
        from GexReader import get_latest_gex_context
    except ImportError:
        get_latest_gex_context = None

if os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

TARGET_TICKERS = [
    "SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMZN", "GOOGL", "AMD", 
    "META", "NFLX", "PLTR", "SOFI", "F", "AAL", "INTC", "RIVN", "HOOD", 
    "BAC", "SNAP", "MARA", "CCL", "UBER", "NKE"
]

PROXIMITY_ENDPOINT = os.getenv("GUARDRAIL_API_URL", "http://localhost:8000/api/proximity")
TRADIER_TOKEN = (
    os.getenv("TRADIER_TOKEN") or 
    os.getenv("TRADIER_PROD_TOKEN") or 
    os.getenv("TRADIER_SANDBOX_TOKEN")
)
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
if "sandbox" in TRADIER_BASE_URL.lower():
    TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"

STATIC_BASELINE_LEVELS = {
  'SPY':   {'spot': 550.00, 'call_target': 552.75, 'put_target': 547.25},
  'QQQ':   {'spot': 480.00, 'call_target': 482.40, 'put_target': 477.60},
  'IWM':   {'spot': 210.00, 'call_target': 211.05, 'put_target': 208.95},
  'NVDA':  {'spot': 226.43, 'call_target': 226.43, 'put_target': 224.90},
  'TSLA':  {'spot': 341.66, 'call_target': 341.66, 'put_target': 338.50},
  'AAPL':  {'spot': 306.79, 'call_target': 306.79, 'put_target': 304.80},
  'AMZN':  {'spot': 180.00, 'call_target': 180.90, 'put_target': 179.10},
  'GOOGL': {'spot': 165.00, 'call_target': 165.80, 'put_target': 164.20},
  'AMD':   {'spot': 140.00, 'call_target': 140.70, 'put_target': 139.30},
  'META':  {'spot': 500.00, 'call_target': 502.50, 'put_target': 497.50},
  'NFLX':  {'spot': 620.00, 'call_target': 623.10, 'put_target': 616.90},
  'PLTR':  {'spot': 179.91, 'call_target': 179.91, 'put_target': 176.20},
  'SOFI':  {'spot': 18.33,  'call_target': 18.33,  'put_target': 18.28},
  'F':     {'spot': 14.14,  'call_target': 14.14,  'put_target': 13.88},
  'AAL':   {'spot': 15.48,  'call_target': 15.48,  'put_target': 14.95},
  'INTC':  {'spot': 105.08, 'call_target': 105.08, 'put_target': 104.20},
  'RIVN':  {'spot': 15.59,  'call_target': 15.59,  'put_target': 15.40},
  'HOOD':  {'spot': 22.00,  'call_target': 22.11,  'put_target': 21.89},
  'BAC':   {'spot': 38.00,  'call_target': 38.19,  'put_target': 37.81},
  'SNAP':  {'spot': 12.00,  'call_target': 12.06,  'put_target': 11.94},
  'MARA':  {'spot': 18.00,  'call_target': 18.09,  'put_target': 17.91},
  'CCL':   {'spot': 16.00,  'call_target': 16.08,  'put_target': 15.92},
  'UBER':  {'spot': 70.00,  'call_target': 70.35,  'put_target': 69.65},
  'NKE':   {'spot': 80.00,  'call_target': 80.40,  'put_target': 79.60}
}

def get_dynamic_proximity_threshold(price: float) -> float:
    """Returns dynamic arming threshold based on asset price tier."""
    if price >= 100.0:
        return 0.0025  # 0.25% (, , )
    elif price >= 30.0:
        return 0.0035  # 0.35% (, )
    else:
        return 0.0060  # 0.60% (, , )

def format_ticker_payload(symbol: str, spot_px: float, vwap_px: float = None, call_tgt: float = None, put_tgt: float = None, gex_label: str = "NEUTRAL") -> dict:
    vwap_px = vwap_px or spot_px
    call_tgt = call_tgt or round(spot_px * 1.005, 2)
    put_tgt = put_tgt or round(spot_px * 0.995, 2)
    
    threshold = get_dynamic_proximity_threshold(spot_px)
    gap_pct = abs(spot_px - call_tgt) / spot_px if spot_px > 0 else 1.0
    is_armed = gap_pct <= threshold
    
    return {
        "spot": spot_px,
        "price": spot_px,
        "last_price": spot_px,
        "spot_price": spot_px,
        "vwap": vwap_px,
        "call_target": call_tgt,
        "put_target": put_tgt,
        "spot_target_call": call_tgt,
        "spot_target_put": put_tgt,
        "gex_label": gex_label,
        "proximity_threshold": threshold,
        "gap_pct": round(gap_pct * 100.0, 2),
        "execution_armed": is_armed,
        "support_a": round(spot_px * 0.993, 2),
        "support_b": round(spot_px * 0.997, 2),
        "resistance_a": round(spot_px * 1.003, 2),
        "resistance_b": round(spot_px * 1.007, 2),
        "support_zone": [round(spot_px * 0.993, 2), round(spot_px * 0.997, 2)],
        "resistance_zone": [round(spot_px * 1.003, 2), round(spot_px * 1.007, 2)]
    }

def fetch_live_guardrails_from_api() -> dict:
    try:
        res = requests.get(PROXIMITY_ENDPOINT, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and all(t in data for t in TARGET_TICKERS):
                return data
    except Exception:
        pass
    return {}

def derive_guardrails_from_tradier() -> dict:
    if not TRADIER_TOKEN:
        return {}
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    symbols_str = ",".join(TARGET_TICKERS)
    try:
        resp = requests.get(f"{TRADIER_BASE_URL}/markets/quotes", params={"symbols": symbols_str}, headers=headers, timeout=5)
        if resp.status_code == 200:
            quotes = resp.json().get("quotes", {}).get("quote", [])
            if isinstance(quotes, dict):
                quotes = [quotes]
            derived = {}
            for q in quotes:
                symbol = q.get("symbol")
                last_px = float(q.get("last") or q.get("close") or 0.0)
                vwap_px = float(q.get("vwap") or last_px)
                if symbol in TARGET_TICKERS and last_px > 0:
                    gex_ctx = get_latest_gex_context(symbol) if callable(get_latest_gex_context) else {}
                    gex_ctx = gex_ctx or {}
                    call_wall = gex_ctx.get('call_wall') or round(last_px * 1.005, 2)
                    put_wall = gex_ctx.get('put_wall') or round(last_px * 0.995, 2)
                    gex_lbl = gex_ctx.get('gex_label', 'NEUTRAL')
                    derived[symbol] = format_ticker_payload(symbol, last_px, vwap_px, call_wall, put_wall, gex_lbl)
            if len(derived) == len(TARGET_TICKERS):
                return derived
    except Exception:
        pass
    return {}

def build_offhours_baseline_levels() -> dict:
    derived = {}
    for ticker in TARGET_TICKERS:
        info = STATIC_BASELINE_LEVELS.get(ticker, {'spot': 100.0, 'call_target': 100.5, 'put_target': 99.5})
        gex_ctx = get_latest_gex_context(ticker) if callable(get_latest_gex_context) else {}
        gex_ctx = gex_ctx or {}
        spot_px = float(gex_ctx.get('spot_price') or info["spot"])
        call_tgt = gex_ctx.get('call_wall') or info["call_target"]
        put_tgt = gex_ctx.get('put_wall') or info["put_target"]
        gex_lbl = gex_ctx.get('gex_label', 'NEUTRAL')
        derived[ticker] = format_ticker_payload(
            ticker, spot_px=spot_px, call_tgt=call_tgt, put_tgt=put_tgt, gex_label=gex_lbl
        )
    return derived

def run_guardrail_sync():
    print(f"[*] Initiating dynamic Guardrail level derivation for {len(TARGET_TICKERS)} assets...")
    guardrail_levels = fetch_live_guardrails_from_api()
    if not guardrail_levels:
        guardrail_levels = derive_guardrails_from_tradier()
    if not guardrail_levels or len(guardrail_levels) < len(TARGET_TICKERS):
        guardrail_levels = build_offhours_baseline_levels()

    save_trading_levels(guardrail_levels)
    print(f"[🚀 SUCCESS] Derived and published {len(guardrail_levels)} active Guardrail levels to S3 & Local Disk.")

if __name__ == "__main__":
    run_guardrail_sync()

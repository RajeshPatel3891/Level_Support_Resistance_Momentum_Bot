import os

import json

def _get_dynamic_target(ticker, key, fallback):
    manifest = "trading_levels.json"
    if os.path.exists(manifest):
        try:
            with open(manifest, "r") as f:
                data = json.load(f)
            val = data.get(ticker, {}).get(key)
            if val is not None and float(val) > 0:
                return float(val)
        except Exception as e:
            print(f"[!] Manifest read exception for {ticker}: {e}")
    return float(fallback)

PLAYBOOK_CONFIG = {
    "ticker": "NVDA",
    "spot_target_call": 195.50,
    "spot_target_put": 192.50,
    "min_momentum_score": 0.70,
    "velocity_check_active": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= _get_dynamic_target("NVDA", "spot_target_call", PLAYBOOK_CONFIG["spot_target_call"]):
        return True, "NVDA_RESISTANCE_BREAKOUT"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= _get_dynamic_target("NVDA", "spot_target_put", PLAYBOOK_CONFIG["spot_target_put"]):
        return True, "NVDA_SUPPORT_BREACH"
    return False, "OUT_OF_BOUNDS"


def calculate_risk_parameters(spot_price, direction, multiplier=1.0):
    """Fallback Risk Parameter Generator returning dictionary context."""
    spot_price = float(spot_price)
    if direction.upper() in ['CALL', 'BULLISH']:
        tp = round(spot_price * (1 + 0.015 * multiplier), 2)
        sl = round(spot_price * (1 - 0.008 * multiplier), 2)
    else:
        tp = round(spot_price * (1 - 0.015 * multiplier), 2)
        sl = round(spot_price * (1 + 0.008 * multiplier), 2)
    
    return {
        "stop_loss": sl,
        "tp1": tp,
        "take_profit": tp,
        "distance": round(abs(spot_price - sl), 2)
    }
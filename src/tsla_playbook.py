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
    "ticker": "TSLA",
    "spot_target_call": 305.62,
    "spot_target_put": 302.58,
    "min_momentum_score": 0.85,
    "velocity_check_active": True,
    "freefall_lockout": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    return False, "FREEFALL_VELOCITY_FILTER_ENGAGED"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= _get_dynamic_target("TSLA", "spot_target_put", PLAYBOOK_CONFIG["spot_target_put"]) and velocity < -0.5:
        return True, "PUT_CAPITULATION_CONTINUATION"
    return False, "FREEFALL_LOCKOUT_WAIT_FOR_BASE"

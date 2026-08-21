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
    "ticker": "F",
    "spot_target_call": 14.92,
    "spot_target_put": 14.78,
    "low_nominal_mode": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= _get_dynamic_target("F", "spot_target_call", PLAYBOOK_CONFIG["spot_target_call"]):
        return True, "F_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= _get_dynamic_target("F", "spot_target_put", PLAYBOOK_CONFIG["spot_target_put"]):
        return True, "F_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

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
    "ticker": "CCL",
    "spot_target_call": 25.81,
    "spot_target_put": 25.55,
    "min_momentum_score": 0.65,
    "velocity_check_active": True,
    "low_nominal_mode": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= _get_dynamic_target("CCL", "spot_target_call", PLAYBOOK_CONFIG["spot_target_call"]):
        return True, "CCL_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= _get_dynamic_target("CCL", "spot_target_put", PLAYBOOK_CONFIG["spot_target_put"]):
        return True, "CCL_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

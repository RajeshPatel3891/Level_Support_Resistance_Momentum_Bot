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
    "ticker": "RIVN",
    "spot_target_call": 16.03,
    "spot_target_put": 15.87,
    "low_nominal": True,
    "min_extrinsic_floor": 0.20
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= _get_dynamic_target("RIVN", "spot_target_call", PLAYBOOK_CONFIG["spot_target_call"]):
        return True, "RIVN_LOW_NOMINAL_CALL"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= _get_dynamic_target("RIVN", "spot_target_put", PLAYBOOK_CONFIG["spot_target_put"]):
        return True, "RIVN_LOW_NOMINAL_PUT"
    return False, "OUT_OF_BOUNDS"

PLAYBOOK_CONFIG = {
    "ticker": "RIVN",
    "spot_target_call": 18.51,
    "spot_target_put": 17.11,
    "low_nominal": True,
    "min_extrinsic_floor": 0.20
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "RIVN_LOW_NOMINAL_CALL"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "RIVN_LOW_NOMINAL_PUT"
    return False, "OUT_OF_BOUNDS"

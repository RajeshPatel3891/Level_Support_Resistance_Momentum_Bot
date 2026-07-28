PLAYBOOK_CONFIG = {
    "ticker": "PLTR",
    "spot_target_call": 135.25,
    "spot_target_put": 128.75,
    "min_momentum_score": 0.65
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "PLTR_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "PLTR_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

PLAYBOOK_CONFIG = {
    "ticker": "AAL",
    "spot_target_call": 14.91,
    "spot_target_put": 14.77,
    "low_nominal": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "AAL_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "AAL_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

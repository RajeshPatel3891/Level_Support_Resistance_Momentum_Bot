PLAYBOOK_CONFIG = {
    "ticker": "INTC",
    "spot_target_call": 85.83,
    "spot_target_put": 84.97,
    "low_nominal": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "INTC_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "INTC_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

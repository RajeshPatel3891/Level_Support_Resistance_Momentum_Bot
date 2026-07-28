PLAYBOOK_CONFIG = {
    "ticker": "SOFI",
    "spot_target_call": 16.82,
    "spot_target_put": 16.76,
    "low_nominal": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "SOFI_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "SOFI_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

PLAYBOOK_CONFIG = {
    "ticker": "TSLA",
    "spot_target_call": 384.10,
    "spot_target_put": 310.00,
    "min_momentum_score": 0.85,
    "velocity_check_active": True,
    "freefall_lockout": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    return False, "FREEFALL_VELOCITY_FILTER_ENGAGED"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"] and velocity < -0.5:
        return True, "PUT_CAPITULATION_CONTINUATION"
    return False, "FREEFALL_LOCKOUT_WAIT_FOR_BASE"

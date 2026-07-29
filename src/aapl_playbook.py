PLAYBOOK_CONFIG = {
    "ticker": "AAPL",
    "spot_target_call": 341.80,
    "spot_target_put": 339.50,
    "min_momentum_score": 0.65,
    "velocity_check_active": True,
    "low_nominal_mode": False
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "AAPL_CALL_BREAKOUT"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "AAPL_PUT_BREAKDOWN"
    return False, "OUT_OF_BOUNDS"

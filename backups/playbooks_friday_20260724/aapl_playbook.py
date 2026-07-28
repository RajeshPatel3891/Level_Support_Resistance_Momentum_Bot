PLAYBOOK_CONFIG = {
    "ticker": "AAPL",
    "spot_target_call": 332.10,
    "spot_target_put": 323.10,
    "min_momentum_score": 0.65,
    "velocity_check_active": True,
    "low_nominal_mode": False
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"] and velocity >= 0.0:
        return True, "CALL_BREAKOUT_CONFIRMED"
    return False, "OUT_OF_BOUNDS_BELOW_RESISTANCE"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"] and velocity <= 0.0:
        return True, "PUT_BREAKDOWN_CONFIRMED"
    return False, "OUT_OF_BOUNDS_ABOVE_SUPPORT"

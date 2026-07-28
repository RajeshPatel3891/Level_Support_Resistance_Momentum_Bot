PLAYBOOK_CONFIG = {
    "ticker": "NVDA",
    "spot_target_call": 194.87,
    "spot_target_put": 192.93,
    "min_momentum_score": 0.70,
    "velocity_check_active": True
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= PLAYBOOK_CONFIG["spot_target_call"]:
        return True, "NVDA_RESISTANCE_BREAKOUT"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= PLAYBOOK_CONFIG["spot_target_put"]:
        return True, "NVDA_SUPPORT_BREACH"
    return False, "OUT_OF_BOUNDS"

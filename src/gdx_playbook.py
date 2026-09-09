from src.base_playbook import get_dynamic_target, evaluate_tradealgo_regime

PLAYBOOK_CONFIG = {
    "ticker": "GDX",
    "spot_target_call": 100.00,
    "spot_target_put": 98.50,
    "low_nominal_mode": False,
    "min_momentum_score": 0.65
}

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price >= get_dynamic_target("GDX", "spot_target_call", PLAYBOOK_CONFIG["spot_target_call"]):
        return True, "GDX_CALL_TRIGGER"
    return False, "OUT_OF_BOUNDS"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    if spot_price <= get_dynamic_target("GDX", "spot_target_put", PLAYBOOK_CONFIG["spot_target_put"]):
        return True, "GDX_PUT_TRIGGER"
    return False, "OUT_OF_BOUNDS"

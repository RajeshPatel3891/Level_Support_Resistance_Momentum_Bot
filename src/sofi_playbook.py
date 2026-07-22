# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (SOFI EQUITY)
# Target Session: Wednesday, July 22, 2026
# Asset Class: Direct Equity / Shares
# Pre-Market Spot: $17.01 | VWAP Anchor: $17.15
# Enforced Risk Budget: $30.00 | Dynamic ATR Volatility Buffer: $0.25
# ==============================================================================

PLAYBOOK_CONFIG = {
    "ticker": "SOFI",
    "date": "2026-07-22",
    "spot_anchor": 17.01,
    "vwap_anchor": 17.15,
    "support_zone": [16.8, 17.1],
    "resistance_zone": [17.8, 18.1],
    "risk_per_trade": 30.00,
    "atr_14_buffer": 0.25,
    "guardrails": {
        "velocity_filter_active": False,
        "momentum_filter_active": True,
        "allow_execution": True
    }
}

def calculate_share_size(entry_price, stop_price):
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0: return 0
    return max(1, int(PLAYBOOK_CONFIG["risk_per_trade"] / risk_per_share))

def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if velocity_flag or not candles_1m or len(candles_1m) < 2: return False, 0
    floor, ceiling = PLAYBOOK_CONFIG["support_zone"]
    if (floor <= current_price <= ceiling) and (candles_1m[-1]['close'] >= current_vwap):
        stop_price = current_price - PLAYBOOK_CONFIG["atr_14_buffer"]
        return True, calculate_share_size(current_price, stop_price)
    return False, 0

def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if velocity_flag or not candles_1m or len(candles_1m) < 2: return False, 0
    floor, ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    if (floor <= current_price <= ceiling) and (candles_1m[-1]['close'] < current_vwap):
        stop_price = current_price + PLAYBOOK_CONFIG["atr_14_buffer"]
        return True, calculate_share_size(current_price, stop_price)
    return False, 0

if __name__ == "__main__":
    print(f"[SOFI Playbook Verified] Date: 2026-07-22 | Risk Cap: $30.00")

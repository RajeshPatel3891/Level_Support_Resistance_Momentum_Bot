# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (F ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $13.99 | VWAP Anchor: $14.05
# Support Pool: $13.85 - $14.00 | Resistance Pool: $14.40 - $14.60
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "F260724C00014500"  # July 24, 2026 $14.50 Call
TICKER_PUT  = "F260724P00013500"  # July 24, 2026 $13.50 Put

PLAYBOOK_CONFIG = {
    "ticker": "F",
    "date": "2026-07-21",
    "spot_anchor": 13.99,
    "vwap_anchor": 14.05,
    "support_zone": [13.85, 14.00],
    "resistance_zone": [14.40, 14.60],
    "risk_per_trade": 85.00,
    "guardrails": {
        "velocity_filter_active": False,
        "momentum_filter_active": True,
        "allow_execution": False
    }
}

def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if velocity_flag:
        return False, 0
    if not candles_1m:
        candles_1m = [{"low": 13.90, "close": current_price, "high": current_price + 0.10}]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    vwap_reclaim = (candles_1m[-1]['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        return True, 14  # 14 contracts to hit $85 risk footprint on low-cost premium

    return False, 0

def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if not candles_1m:
        candles_1m = [{"low": 14.30, "close": current_price, "high": 14.65}]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    below_vwap = (candles_1m[-1]['close'] < current_vwap)

    if rejection_zone and below_vwap:
        return True, 14

    return False, 0

def calculate_risk_parameters(entry_fill, option_type):
    return {
        "stop_loss": round(entry_fill * 0.80, 2),
        "tp1": round(entry_fill * 1.40, 2),
        "underlying_invalidation": 13.70 if option_type == "CALL" else 14.80
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 13.99, 14.05, velocity_flag=False)
    put_exec, put_qty = evaluate_put_entry([], 13.99, 14.05, velocity_flag=False)
    print(f"[F Playbook Self-Test] Spot: $13.99 | Call: {call_exec} ({call_qty} contracts) | Put: {put_exec} ({put_qty} contracts)")

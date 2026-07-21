# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (SOFI ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $17.01 | VWAP Anchor: $17.15
# Support Pool: $16.80 - $17.10 | Resistance Pool: $17.80 - $18.10
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "SOFI260724C00018000"  # July 24, 2026 $18.00 Call
TICKER_PUT  = "SOFI260724P00016500"  # July 24, 2026 $16.50 Put

PLAYBOOK_CONFIG = {
    "ticker": "SOFI",
    "date": "2026-07-21",
    "spot_anchor": 17.01,
    "vwap_anchor": 17.15,
    "support_zone": [16.80, 17.10],
    "resistance_zone": [17.80, 18.10],
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
        candles_1m = [{"low": 16.90, "close": current_price, "high": current_price + 0.10}]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    vwap_reclaim = (candles_1m[-1]['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        return True, 10  # 10 contracts to hit $85 risk footprint

    return False, 0

def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if not candles_1m:
        candles_1m = [{"low": 17.70, "close": current_price, "high": 18.15}]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    below_vwap = (candles_1m[-1]['close'] < current_vwap)

    if rejection_zone and below_vwap:
        return True, 10

    return False, 0

def calculate_risk_parameters(entry_fill, option_type):
    return {
        "stop_loss": round(entry_fill * 0.80, 2),
        "tp1": round(entry_fill * 1.40, 2),
        "underlying_invalidation": 16.50 if option_type == "CALL" else 18.50
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 17.01, 17.15, velocity_flag=False)
    put_exec, put_qty = evaluate_put_entry([], 17.01, 17.15, velocity_flag=False)
    print(f"[SOFI Playbook Self-Test] Spot: $17.01 | Call: {call_exec} ({call_qty} contracts) | Put: {put_exec} ({put_qty} contracts)")

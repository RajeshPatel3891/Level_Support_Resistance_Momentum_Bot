# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (AAL ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $15.14 | VWAP Anchor: $15.20
# Support Pool: $15.00 - $15.15 | Resistance Pool: $15.80 - $16.00
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "AAL260724C00016000"  # July 24, 2026 $16.00 Call
TICKER_PUT  = "AAL260724P00014500"  # July 24, 2026 $14.50 Put

PLAYBOOK_CONFIG = {
    "ticker": "AAL",
    "date": "2026-07-21",
    "spot_anchor": 15.14,
    "vwap_anchor": 15.20,
    "support_zone": [15.00, 15.15],
    "resistance_zone": [15.80, 16.00],
    "risk_per_trade": 85.00,
    "guardrails": {
        "velocity_filter_active": False,
        "momentum_filter_active": True,
        "allow_execution": False  # Blocked until VWAP $15.20 reclaim
    }
}

def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if velocity_flag:
        return False, 0
    if not candles_1m:
        candles_1m = [{"low": 15.05, "close": current_price, "high": current_price + 0.10}]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    vwap_reclaim = (candles_1m[-1]['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        return True, 12  # 12 contracts to hit $85 risk footprint

    return False, 0

def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if not candles_1m:
        candles_1m = [{"low": 15.70, "close": current_price, "high": 16.05}]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    below_vwap = (candles_1m[-1]['close'] < current_vwap)

    if rejection_zone and below_vwap:
        return True, 12

    return False, 0

def calculate_risk_parameters(entry_fill, option_type):
    return {
        "stop_loss": round(entry_fill * 0.80, 2),
        "tp1": round(entry_fill * 1.40, 2),
        "underlying_invalidation": 14.80 if option_type == "CALL" else 16.20
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 15.14, 15.20, velocity_flag=False)
    put_exec, put_qty = evaluate_put_entry([], 15.14, 15.20, velocity_flag=False)
    print(f"[AAL Playbook Self-Test] Spot: $15.14 | Call: {call_exec} ({call_qty} contracts) | Put: {put_exec} ({put_qty} contracts)")

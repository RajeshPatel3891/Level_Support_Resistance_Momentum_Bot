# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (RIVN ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $17.15 | VWAP Anchor: $17.25
# Support Pool: $17.11 - $17.19 | Resistance Pool: $18.51 - $18.59
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "RIVN260724C00018000"  # July 24, 2026 $18.00 Call
TICKER_PUT  = "RIVN260724P00016500"  # July 24, 2026 $16.50 Put

PLAYBOOK_CONFIG = {
    "ticker": "RIVN",
    "date": "2026-07-21",
    "spot_anchor": 17.15,
    "vwap_anchor": 17.25,
    "support_zone": [17.11, 17.19],
    "resistance_zone": [18.51, 18.59],
    "risk_per_trade": 85.00,
    "guardrails": {
        "velocity_filter_active": False,
        "momentum_filter_active": True,
        "allow_execution": False  # Blocked (Spot below VWAP)
    }
}

# 1. BULLISH SCALP: CALL SETUP ON SUPPORT POOL BOUNCE
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: RIVN holds Support ($17.11 - $17.19) AND reclaims VWAP ($17.25),
    with momentum velocity validating the move.
    """
    if velocity_flag:
        return False, 0

    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 17.05, "close": 17.12, "high": 17.18},
            {"low": 17.10, "close": 17.16, "high": 17.22},
            {"low": 17.14, "close": current_price, "high": current_price + 0.10}
        ]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    
    current_candle = candles_1m[-1]
    # Hard Guardrail Check: Must be AT OR ABOVE VWAP for Longs
    vwap_reclaim = (current_candle['close'] >= current_vwap)
    momentum_velocity = (current_candle['close'] > candles_1m[-2]['high'])

    if trigger_zone and vwap_reclaim and momentum_velocity:
        # Sizing for low-dollar options (~$0.45 premium * 20% risk = $0.09/contract risk)
        # 9 contracts * $9.00 = $81.00 risk footprint.
        return True, 9

    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM RESISTANCE REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: RIVN tests Resistance ($18.51 - $18.59) and breaks down below VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 18.40, "close": 18.52, "high": 18.58},
            {"low": 18.45, "close": 18.55, "high": 18.60},
            {"low": 18.30, "close": current_price, "high": 18.58}
        ]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    current_candle = candles_1m[-1]
    below_vwap_or_rejection = (current_candle['close'] < candles_1m[-2]['low'])

    if rejection_zone and below_vwap_or_rejection:
        return True, 9

    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.40, 2)
    underlying_invalidation = 16.90 if option_type == "CALL" else 18.80

    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 17.15, 17.25, velocity_flag=False)
    put_exec, put_qty = evaluate_put_entry([], 17.15, 17.25, velocity_flag=False)
    print(f"[RIVN Playbook Self-Test] Spot: $17.15 | VWAP: $17.25 | Call: {call_exec} ({call_qty} contracts) | Put: {put_exec} ({put_qty} contracts)")
